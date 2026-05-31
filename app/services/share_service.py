"""File sharing (MVP5) business logic.

읽기 전용 공유 토큰을 발급·조회·검증한다. 토큰은 특정 디바이스의
특정 물리 경로 하나에만 묶이며 만료 시각을 가진다.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

import aiosqlite

from app.exceptions import (
    DeviceAccessDeniedError,
    DeviceNotFoundError,
    ShareExpiredError,
    ShareNotFoundError,
)

logger = logging.getLogger(__name__)

_TS_FMT = "%Y-%m-%dT%H:%M:%S"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class ShareService:
    """공유 토큰 발급/조회/검증."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def create_share(
        self,
        owner_user_id: str,
        device_id: str,
        physical_path: str,
        expires_in_seconds: int,
    ) -> dict:
        """공유 토큰을 발급한다. device_id가 owner 소유인지 검증한다.

        Returns:
            {"share_token": str, "expires_at": datetime}

        Raises:
            DeviceNotFoundError: device_id 미존재
            DeviceAccessDeniedError: device_id가 owner 소유 아님
        """
        cursor = await self.db.execute(
            "SELECT user_id FROM devices WHERE id = ?", (device_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise DeviceNotFoundError()
        if row["user_id"] != owner_user_id:
            raise DeviceAccessDeniedError()

        token = secrets.token_urlsafe(32)
        expires_at = _now() + timedelta(seconds=expires_in_seconds)
        expires_at_str = expires_at.strftime(_TS_FMT)

        await self.db.execute(
            "INSERT INTO shares (token, owner_user_id, device_id, "
            "physical_path, expires_at) VALUES (?, ?, ?, ?, ?)",
            (token, owner_user_id, device_id, physical_path, expires_at_str),
        )
        await self.db.commit()
        logger.info(
            "Share created by %s for device %s path %s (expires %s)",
            owner_user_id, device_id, physical_path, expires_at_str,
        )
        return {"share_token": token, "expires_at": expires_at}

    async def _fetch(self, token: str) -> aiosqlite.Row:
        cursor = await self.db.execute(
            "SELECT token, owner_user_id, device_id, physical_path, expires_at "
            "FROM shares WHERE token = ?",
            (token,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ShareNotFoundError()
        return row

    async def get_share(self, token: str) -> dict:
        """토큰을 조회한다. physical_path는 노출하지 않는다.

        Returns:
            {"device_id": str, "expired": False}

        Raises:
            ShareNotFoundError: 토큰 미존재
            ShareExpiredError: 만료됨
        """
        row = await self._fetch(token)
        if _now() >= _parse_ts(row["expires_at"]):
            raise ShareExpiredError()
        return {"device_id": row["device_id"], "expired": False}

    async def verify_share(self, token: str, physical_path: str) -> dict:
        """P2P 서버 위임 검증용. 토큰이 유효하고 경로가 일치하면 valid=true.

        존재하지 않거나 만료됐거나 경로가 불일치하면 valid=false.
        (P2P 서버가 valid 플래그로 판정하므로 예외 대신 플래그로 응답)

        Returns:
            {"valid": bool, "device_id": str | None}
        """
        try:
            row = await self._fetch(token)
        except ShareNotFoundError:
            return {"valid": False, "device_id": None}

        if _now() >= _parse_ts(row["expires_at"]):
            return {"valid": False, "device_id": None}

        if row["physical_path"] != physical_path:
            return {"valid": False, "device_id": row["device_id"]}

        return {"valid": True, "device_id": row["device_id"]}

    async def resolve_device_for_routing(self, token: str) -> str | None:
        """라우팅 우회용: 유효한 토큰이면 묶인 device_id를 반환, 아니면 None."""
        try:
            row = await self._fetch(token)
        except ShareNotFoundError:
            return None
        if _now() >= _parse_ts(row["expires_at"]):
            return None
        return row["device_id"]
