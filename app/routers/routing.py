"""Device routing information router."""
from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_db
from app.exceptions import DeviceAccessDeniedError, DeviceNotFoundError
from app.schemas import RoutingResponse
from app.services.device_service import DeviceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/{device_id}", response_model=RoutingResponse)
async def get_routing_info(
    device_id: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """디바이스 라우팅 정보 조회.

    소유권 검증 후 실시간 온라인 상태를 판정하여 반환한다.
    """
    # 디바이스 조회
    cursor = await db.execute(
        "SELECT id, user_id, connection_address, last_heartbeat "
        "FROM devices WHERE id = ?",
        (device_id,),
    )
    row = await cursor.fetchone()

    if row is None:
        raise DeviceNotFoundError()

    if row["user_id"] != current_user["id"]:
        raise DeviceAccessDeniedError()

    # 실시간 온라인 상태 판정
    service = DeviceService(db)
    online = service.is_device_online(row["last_heartbeat"])

    logger.info(f"Routing info requested for device {device_id}, online={online}")

    return RoutingResponse(
        device_id=row["id"],
        connection_address=row["connection_address"],
        is_online=online,
        last_heartbeat=row["last_heartbeat"],
    )
