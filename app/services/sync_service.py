"""Metadata and key backup synchronisation logic."""
from __future__ import annotations

import logging

import aiosqlite

from app.exceptions import BackupNotFoundError

logger = logging.getLogger(__name__)


class SyncService:
    """메타데이터/키 백업 업로드/다운로드 관리."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def upload_metadata(
        self, user_id: str, blob: bytes, base_version: int | None = None
    ) -> int:
        """메타데이터 blob 저장 (user_id당 1개만 유지). 새 version 반환.

        UNIQUE(user_id, version) 인덱스를 이용한 원자적 낙관적 잠금(CAS)을 적용한다.
        명시적 version으로 INSERT하므로, 동시에 같은 version을 쓰려는 두 요청 중
        하나는 DB 레벨에서 UNIQUE 위반으로 실패한다 (연결 분리와 무관하게 원자적).

        Args:
            user_id: 사용자 ID.
            blob: 암호화된 metadata DB blob.
            base_version: 클라이언트가 기반한 서버 version (CAS).
                None이면 현재 최대 version 기준으로 강제 기록(force, 하위 호환).
                값이 주어지면 new_version = base_version + 1로 기록을 시도하고,
                이미 그 version이 존재하면 MetadataVersionConflictError(409).

        Returns:
            새로 기록된 version.

        Raises:
            MetadataVersionConflictError: base_version 기반 기록이 충돌(다른 디바이스 선점).
        """
        import sqlite3

        from app.exceptions import MetadataVersionConflictError

        # 현재 최대 version 조회
        cursor = await self.db.execute(
            "SELECT MAX(version) as max_ver FROM metadata_backups WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        current_version = row["max_ver"] if row["max_ver"] is not None else 0

        if base_version is not None:
            # 낙관적 잠금: 클라이언트 기반 버전 다음 번호로만 기록 허용
            if base_version != current_version:
                logger.warning(
                    "Metadata CAS conflict for user %s: base=%s, current=%s",
                    user_id, base_version, current_version,
                )
                raise MetadataVersionConflictError(current_version)
            new_version = base_version + 1
        else:
            new_version = current_version + 1

        # 명시적 version으로 INSERT — UNIQUE(user_id, version) 위반 시 동시 충돌
        try:
            await self.db.execute(
                "INSERT INTO metadata_backups (user_id, encrypted_blob, version) "
                "VALUES (?, ?, ?)",
                (user_id, blob, new_version),
            )
        except sqlite3.IntegrityError:
            # 다른 요청이 동일 version을 선점함 → CAS 충돌
            await self.db.rollback()
            cursor = await self.db.execute(
                "SELECT MAX(version) as max_ver FROM metadata_backups "
                "WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            latest = row["max_ver"] if row["max_ver"] is not None else 0
            logger.warning(
                "Metadata CAS race for user %s: version %s already taken (latest=%s)",
                user_id, new_version, latest,
            )
            raise MetadataVersionConflictError(latest)

        # user_id당 1개만 유지: 방금 기록한 version보다 낮은 행 정리
        await self.db.execute(
            "DELETE FROM metadata_backups WHERE user_id = ? AND version < ?",
            (user_id, new_version),
        )
        await self.db.commit()

        logger.info(f"Metadata uploaded for user {user_id}, version={new_version}")
        return new_version

    async def download_metadata(self, user_id: str) -> tuple:
        """최신 메타데이터 blob + version 반환.

        Returns:
            tuple of (blob: bytes, version: int)

        Raises:
            BackupNotFoundError: 백업 미존재
        """
        cursor = await self.db.execute(
            "SELECT encrypted_blob, version FROM metadata_backups "
            "WHERE user_id = ? ORDER BY version DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise BackupNotFoundError("Metadata")

        return (bytes(row["encrypted_blob"]), row["version"])

    async def get_metadata_status(self, user_id: str) -> dict:
        """메타데이터 백업 상태 조회 (version, uploaded_at).

        Returns:
            dict with version, uploaded_at. 백업 없으면 None 값.
        """
        cursor = await self.db.execute(
            "SELECT version, uploaded_at FROM metadata_backups "
            "WHERE user_id = ? ORDER BY version DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            return {"version": None, "uploaded_at": None}

        return {"version": row["version"], "uploaded_at": row["uploaded_at"]}

    async def get_current_version(self, user_id: str) -> int:
        """현재 메타데이터 version을 반환한다. 백업이 없으면 0."""
        cursor = await self.db.execute(
            "SELECT MAX(version) as max_ver FROM metadata_backups "
            "WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row is None or row["max_ver"] is None:
            return 0
        return int(row["max_ver"])

    async def upload_key(self, user_id: str, blob: bytes) -> None:
        """암호화 키 blob 저장 (upsert)."""
        # SQLite upsert: INSERT OR REPLACE
        await self.db.execute(
            "INSERT INTO key_backups (user_id, encrypted_blob) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "encrypted_blob = excluded.encrypted_blob, "
            "uploaded_at = datetime('now')",
            (user_id, blob),
        )
        await self.db.commit()
        logger.info(f"Key backup uploaded for user {user_id}")

    async def download_key(self, user_id: str) -> bytes:
        """암호화 키 blob 반환.

        Raises:
            BackupNotFoundError: 백업 미존재
        """
        cursor = await self.db.execute(
            "SELECT encrypted_blob FROM key_backups WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise BackupNotFoundError("Key")

        return bytes(row["encrypted_blob"])
