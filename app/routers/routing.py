"""Device routing information router."""
from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends, Header

from app.dependencies import get_current_user, get_db
from app.exceptions import DeviceAccessDeniedError, DeviceNotFoundError
from app.schemas import RoutingResponse
from app.services.device_service import DeviceService
from app.services.share_service import ShareService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/{device_id}", response_model=RoutingResponse)
async def get_routing_info(
    device_id: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
    x_share_token: str | None = Header(default=None),
):
    """디바이스 라우팅 정보 조회.

    기본은 소유권 검증 후 반환한다. 단, X-Share-Token 헤더가 유효하고 그 토큰이
    요청 device_id에 묶여 있으면(수신자가 공유받은 경우) 소유권 검증을 우회한다.
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

    # 공유 토큰 우회: 유효한 토큰이 이 device_id에 묶여 있으면 소유권 검증 생략
    share_authorised = False
    if x_share_token is not None:
        share_device = await ShareService(db).resolve_device_for_routing(
            x_share_token
        )
        share_authorised = share_device == device_id

    if not share_authorised and row["user_id"] != current_user["id"]:
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
