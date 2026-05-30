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

    async def upload_metadata(self, user_id: str, blob: bytes) -> int:
        """메타데이터 blob 저장, version 증가. 새 version 반환."""
        # 현재 최대 version 조회
        cursor = await self.db.execute(
            "SELECT MAX(version) as max_ver FROM metadata_backups WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        current_version = row["max_ver"] if row["max_ver"] is not None else 0
        new_version = current_version + 1

        await self.db.execute(
            "INSERT INTO metadata_backups (user_id, encrypted_blob, version) "
            "VALUES (?, ?, ?)",
            (user_id, blob, new_version),
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
