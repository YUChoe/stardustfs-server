"""P2P 릴레이 fallback 라우터 (long-polling).

직접 P2P 연결이 불가능한 두 디바이스 간에 서버가 P2P 작업을 중계한다.
양쪽 모두 outbound HTTP만 사용하므로 NAT/CGNAT를 통과한다.

서버는 payload/result를 불투명 blob으로 중계하며 해석/영속화하지 않는다.
같은 user_id의 디바이스 간에만 허용한다.
"""
from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends, Request

from app.dependencies import get_current_user, get_db
from app.exceptions import DeviceAccessDeniedError, DeviceNotFoundError
from app.schemas import (
    RelayPolled,
    RelayRequestAccepted,
    RelayRequestBody,
    RelayResponseBody,
)
from app.services.relay_hub import RelayHub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/relay", tags=["relay"])

# long-poll 타임아웃 (초)
_POLL_TIMEOUT = 25.0
_RESPONSE_TIMEOUT = 30.0


def get_relay_hub(request: Request) -> RelayHub:
    """app.state의 단일 RelayHub 인스턴스를 반환한다."""
    hub = getattr(request.app.state, "relay_hub", None)
    if hub is None:
        hub = RelayHub()
        request.app.state.relay_hub = hub
    return hub


async def _device_owner(db: aiosqlite.Connection, device_id: str) -> str:
    """device_id의 소유자 user_id를 반환한다. 없으면 DeviceNotFoundError."""
    cursor = await db.execute(
        "SELECT user_id FROM devices WHERE id = ?", (device_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise DeviceNotFoundError()
    return row["user_id"]


@router.post("/request", response_model=RelayRequestAccepted)
async def submit_request(
    body: RelayRequestBody,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
) -> RelayRequestAccepted:
    """요청자가 대상 디바이스 앞으로 릴레이 요청을 적재한다.

    대상 디바이스 소유자가 요청자와 같은 user_id여야 한다(403).
    """
    owner = await _device_owner(db, body.target_device_id)
    if owner != current_user["id"]:
        raise DeviceAccessDeniedError()

    hub = get_relay_hub(request)
    request_id = await hub.submit(
        target_device_id=body.target_device_id,
        op=body.op,
        payload=body.payload,
        requester_device_id=body.requester_device_id,
    )
    return RelayRequestAccepted(request_id=request_id)


@router.get("/poll")
async def poll(
    request: Request,
    device_id: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """대상 디바이스가 자신 앞으로 온 요청을 long-poll로 수신한다.

    device_id 소유자가 요청자(토큰)와 같은 user_id여야 한다(403).
    타임아웃 내 요청이 없으면 빈 본문(204)을 반환한다.
    """
    from fastapi.responses import JSONResponse, Response

    owner = await _device_owner(db, device_id)
    if owner != current_user["id"]:
        raise DeviceAccessDeniedError()

    hub = get_relay_hub(request)
    message = await hub.poll(device_id, timeout=_POLL_TIMEOUT)
    if message is None:
        return Response(status_code=204)

    polled = RelayPolled(
        request_id=message.request_id,
        op=message.op,
        payload=message.payload,
        requester_device_id=message.requester_device_id,
    )
    return JSONResponse(content=polled.model_dump())


@router.get("/response/{request_id}")
async def wait_response(
    request_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """요청자가 대상의 처리 결과를 long-poll로 수신한다.

    타임아웃 내 응답이 없으면 504를 반환한다.
    """
    from fastapi.responses import JSONResponse

    hub = get_relay_hub(request)
    result = await hub.wait_response(request_id, timeout=_RESPONSE_TIMEOUT)
    if result is None:
        return JSONResponse(
            content={"detail": "Relay response timeout"}, status_code=504
        )
    return JSONResponse(content=result)


@router.post("/response/{request_id}")
async def submit_response(
    request_id: str,
    body: RelayResponseBody,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """대상이 처리 결과를 올린다. 서버는 대기 중인 요청자에게 전달한다."""
    hub = get_relay_hub(request)
    delivered = await hub.deliver(
        request_id, {"status": body.status, "result": body.result}
    )
    return {"delivered": delivered}
