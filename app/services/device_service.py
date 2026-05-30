"""Device management business logic."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

from app.config import get_settings
from app.exceptions import DeviceAccessDeniedError, DeviceNotFoundError

logger = logging.getLogger(__name__)


class DeviceService:
    """디바이스 등록, 조회, 삭제, heartbeat 관리."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def register_device(
        self, user_id: str, name: str, os: str, connection_address: str
    ) -> dict:
        """디바이스 등록 (upsert). 같은 user_id+name+os면 기존 디바이스 갱신.

        Returns:
            dict with id, name, os, connection_address, is_online, last_heartbeat, created_at
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 같은 user_id + name + os 조합이 이미 존재하는지 확인
        cursor = await self.db.execute(
            "SELECT id FROM devices WHERE user_id = ? AND name = ? AND os = ?",
            (user_id, name, os),
        )
        existing = await cursor.fetchone()

        if existing is not None:
            # 기존 디바이스 갱신
            device_id = existing["id"]
            await self.db.execute(
                "UPDATE devices SET connection_address = ?, last_heartbeat = ?, "
                "is_online = 1 WHERE id = ?",
                (connection_address, now, device_id),
            )
            await self.db.commit()
            logger.info(f"Device updated (upsert): {name} for user {user_id}")

            cursor = await self.db.execute(
                "SELECT id, name, os, connection_address, is_online, "
                "last_heartbeat, created_at FROM devices WHERE id = ?",
                (device_id,),
            )
            row = await cursor.fetchone()
        else:
            # 신규 디바이스 등록
            cursor = await self.db.execute(
                "INSERT INTO devices (user_id, name, os, connection_address, "
                "last_heartbeat, is_online) "
                "VALUES (?, ?, ?, ?, ?, 1) "
                "RETURNING id, name, os, connection_address, is_online, "
                "last_heartbeat, created_at",
                (user_id, name, os, connection_address, now),
            )
            row = await cursor.fetchone()
            await self.db.commit()
            logger.info(f"Device registered: {name} for user {user_id}")

        return {
            "id": row["id"],
            "name": row["name"],
            "os": row["os"],
            "connection_address": row["connection_address"],
            "is_online": bool(row["is_online"]),
            "last_heartbeat": row["last_heartbeat"],
            "created_at": row["created_at"],
        }

    async def list_devices(self, user_id: str) -> list:
        """해당 사용자의 모든 디바이스 목록 반환."""
        cursor = await self.db.execute(
            "SELECT id, name, os, connection_address, is_online, "
            "last_heartbeat, created_at "
            "FROM devices WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()

        devices = []
        for row in rows:
            # 실시간 온라인 상태 판정
            online = self.is_device_online(row["last_heartbeat"])
            devices.append({
                "id": row["id"],
                "name": row["name"],
                "os": row["os"],
                "connection_address": row["connection_address"],
                "is_online": online,
                "last_heartbeat": row["last_heartbeat"],
                "created_at": row["created_at"],
            })
        return devices

    async def delete_device(self, user_id: str, device_id: str) -> None:
        """디바이스 삭제. 소유권 검증 포함.

        Raises:
            DeviceNotFoundError: 디바이스 미존재
            DeviceAccessDeniedError: 소유권 불일치
        """
        cursor = await self.db.execute(
            "SELECT id, user_id FROM devices WHERE id = ?", (device_id,)
        )
        row = await cursor.fetchone()

        if row is None:
            raise DeviceNotFoundError()

        if row["user_id"] != user_id:
            raise DeviceAccessDeniedError()

        await self.db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        await self.db.commit()
        logger.info(f"Device deleted: {device_id}")

    async def heartbeat(
        self, user_id: str, device_id: str, connection_address: str | None = None
    ) -> None:
        """last_heartbeat 갱신, 선택적으로 connection_address 갱신.

        Raises:
            DeviceNotFoundError: 디바이스 미존재
            DeviceAccessDeniedError: 소유권 불일치
        """
        cursor = await self.db.execute(
            "SELECT id, user_id FROM devices WHERE id = ?", (device_id,)
        )
        row = await cursor.fetchone()

        if row is None:
            raise DeviceNotFoundError()

        if row["user_id"] != user_id:
            raise DeviceAccessDeniedError()

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        if connection_address is not None:
            await self.db.execute(
                "UPDATE devices SET last_heartbeat = ?, is_online = 1, "
                "connection_address = ? WHERE id = ?",
                (now, connection_address, device_id),
            )
        else:
            await self.db.execute(
                "UPDATE devices SET last_heartbeat = ?, is_online = 1 WHERE id = ?",
                (now, device_id),
            )
        await self.db.commit()

    def is_device_online(self, last_heartbeat: str) -> bool:
        """last_heartbeat가 5분 이내인지 판단."""
        settings = get_settings()
        timeout = timedelta(minutes=settings.heartbeat_timeout_minutes)

        # last_heartbeat 파싱
        try:
            hb_time = datetime.fromisoformat(last_heartbeat).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return False

        now = datetime.now(timezone.utc)
        return (now - hb_time) < timeout
