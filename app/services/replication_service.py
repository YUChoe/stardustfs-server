"""리플리케이션(암호화 패리티 백업) 제어 서비스.

위치 레지스트리(chunks/replicas) + 호혜 회계(hosting) + 배치(placement) + 건강성.
zero-knowledge: 청크 내용/키는 저장하지 않고 위치/크기/회계 메타데이터만 다룬다.
"""

from __future__ import annotations

import logging

import aiosqlite

logger = logging.getLogger(__name__)

# 무료 사용자는 제공 용량의 50%를 타 사용자 보관에 제공한다(호혜 쿼터).
RECIPROCITY_FRACTION = 0.5


class ReplicationService:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    # --- 호혜 회계 ---

    async def set_provided_bytes(
        self, user_id: str, device_id: str, provided_bytes: int
    ) -> bool:
        """디바이스의 제공 용량을 신고한다. 본인 소유 디바이스일 때만 True."""
        cur = await self.db.execute(
            "SELECT id FROM devices WHERE id = ? AND user_id = ?",
            (device_id, user_id),
        )
        if await cur.fetchone() is None:
            return False
        await self.db.execute(
            "INSERT INTO hosting (device_id, provided_bytes, updated_at) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(device_id) DO UPDATE SET "
            "provided_bytes = excluded.provided_bytes, updated_at = datetime('now')",
            (device_id, provided_bytes),
        )
        await self.db.commit()
        return True

    # --- 레지스트리 ---

    async def register_chunk(
        self, owner_user_id: str, chunk_id: str, file_ref: str,
        idx: int, size: int,
    ) -> None:
        """청크를 등록한다(소유자 기준). 이미 있으면 유지."""
        await self.db.execute(
            "INSERT OR IGNORE INTO chunks "
            "(chunk_id, owner_user_id, file_ref, idx, size) "
            "VALUES (?, ?, ?, ?, ?)",
            (chunk_id, owner_user_id, file_ref, idx, size),
        )
        await self.db.commit()

    async def record_replica(
        self, owner_user_id: str, chunk_id: str, holder_device_id: str
    ) -> bool:
        """복제본 저장을 확정한다. 청크가 본인 소유일 때만 기록(True).

        새로 등록될 때만 홀더의 hosted_bytes를 청크 크기만큼 증가시킨다(멱등).
        """
        cur = await self.db.execute(
            "SELECT size FROM chunks WHERE chunk_id = ? AND owner_user_id = ?",
            (chunk_id, owner_user_id),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        size = row["size"]

        # 홀더 디바이스 존재 확인(FK 위반 방지)
        cur = await self.db.execute(
            "SELECT id FROM devices WHERE id = ?", (holder_device_id,)
        )
        if await cur.fetchone() is None:
            return False

        cur = await self.db.execute(
            "INSERT OR IGNORE INTO replicas (chunk_id, holder_device_id) "
            "VALUES (?, ?)",
            (chunk_id, holder_device_id),
        )
        newly_added = cur.rowcount == 1
        if newly_added:
            await self.db.execute(
                "INSERT INTO hosting (device_id, hosted_bytes, updated_at) "
                "VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(device_id) DO UPDATE SET "
                "hosted_bytes = hosted_bytes + ?, updated_at = datetime('now')",
                (holder_device_id, size, size),
            )
        await self.db.commit()
        return True

    async def remove_replica(
        self, owner_user_id: str, chunk_id: str, holder_device_id: str
    ) -> bool:
        """복제본을 제거하고 홀더의 hosted_bytes를 감한다(본인 소유 청크 한정)."""
        cur = await self.db.execute(
            "SELECT size FROM chunks WHERE chunk_id = ? AND owner_user_id = ?",
            (chunk_id, owner_user_id),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        size = row["size"]
        cur = await self.db.execute(
            "DELETE FROM replicas WHERE chunk_id = ? AND holder_device_id = ?",
            (chunk_id, holder_device_id),
        )
        if cur.rowcount and cur.rowcount > 0:
            await self.db.execute(
                "UPDATE hosting SET hosted_bytes = MAX(0, hosted_bytes - ?), "
                "updated_at = datetime('now') WHERE device_id = ?",
                (size, holder_device_id),
            )
        await self.db.commit()
        return True

    async def list_replicas(self, chunk_id: str) -> list[dict]:
        """청크의 홀더 목록(온라인/주소 포함)을 반환한다(복구용)."""
        cur = await self.db.execute(
            "SELECT r.holder_device_id, r.status, d.is_online, "
            "d.connection_address "
            "FROM replicas r JOIN devices d ON d.id = r.holder_device_id "
            "WHERE r.chunk_id = ?",
            (chunk_id,),
        )
        rows = await cur.fetchall()
        return [
            {
                "device_id": row["holder_device_id"],
                "status": row["status"],
                "is_online": bool(row["is_online"]),
                "connection_address": row["connection_address"],
            }
            for row in rows
        ]

    # --- 배치 ---

    async def placement(
        self, user_id: str, size: int, count: int, exclude: list[str]
    ) -> list[dict]:
        """용량·온라인·호혜를 고려해 ≤count개 홀더 후보를 선정한다.

        가용 = provided_bytes*RECIPROCITY_FRACTION - hosted_bytes ≥ size 인 온라인
        디바이스 중 가용량 큰 순. exclude된 device_id는 제외.
        """
        placeholders = ",".join("?" for _ in exclude) if exclude else ""
        exclude_clause = f"AND d.id NOT IN ({placeholders})" if exclude else ""
        sql = (
            "SELECT d.id, d.connection_address, "
            "(COALESCE(h.provided_bytes,0) * ? - COALESCE(h.hosted_bytes,0)) "
            "AS avail "
            "FROM devices d LEFT JOIN hosting h ON h.device_id = d.id "
            "WHERE d.is_online = 1 "
            f"{exclude_clause} "
            "AND (COALESCE(h.provided_bytes,0) * ? - COALESCE(h.hosted_bytes,0)) "
            ">= ? "
            "ORDER BY avail DESC LIMIT ?"
        )
        params: list = [RECIPROCITY_FRACTION, *exclude,
                        RECIPROCITY_FRACTION, size, count]
        cur = await self.db.execute(sql, tuple(params))
        rows = await cur.fetchall()
        return [
            {"device_id": row["id"],
             "connection_address": row["connection_address"]}
            for row in rows
        ]

    # --- 건강성 ---

    async def health(self, chunk_id: str) -> dict:
        """청크의 활성 복제 수와 그중 온라인 수를 반환한다."""
        cur = await self.db.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN d.is_online = 1 THEN 1 ELSE 0 END), 0) "
            "AS online "
            "FROM replicas r JOIN devices d ON d.id = r.holder_device_id "
            "WHERE r.chunk_id = ? AND r.status = 'active'",
            (chunk_id,),
        )
        row = await cur.fetchone()
        return {
            "chunk_id": chunk_id,
            "total": row["total"] if row else 0,
            "online": row["online"] if row else 0,
        }
