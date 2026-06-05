"""Device management router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

import aiosqlite

from app.dependencies import get_current_user, get_db
from app.schemas import (
    DeviceCreateRequest,
    DeviceResponse,
    DeviceSourceEntry,
    DeviceSourcesReport,
    HeartbeatRequest,
)
from app.services.device_service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """내 디바이스 목록 조회."""
    service = DeviceService(db)
    devices = await service.list_devices(current_user["id"])
    return devices


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    body: DeviceCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """디바이스 등록."""
    service = DeviceService(db)
    device = await service.register_device(
        user_id=current_user["id"],
        name=body.name,
        os=body.os,
        connection_address=body.connection_address,
    )
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """디바이스 제거."""
    service = DeviceService(db)
    await service.delete_device(current_user["id"], device_id)
    return None


@router.get("/sources", response_model=list[DeviceSourceEntry])
async def list_device_sources(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """내 모든 디바이스의 소스 인벤토리 조회(리모트 스토리지 목록용)."""
    service = DeviceService(db)
    return await service.list_all_sources(current_user["id"])


@router.put("/{device_id}/sources")
async def report_device_sources(
    device_id: str,
    body: DeviceSourcesReport,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """디바이스 소스 인벤토리 신고(전량 교체)."""
    service = DeviceService(db)
    await service.replace_sources(
        current_user["id"], device_id, [s.model_dump() for s in body.sources]
    )
    return {"status": "ok"}


@router.put("/{device_id}/heartbeat")
async def heartbeat(
    device_id: str,
    body: HeartbeatRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Heartbeat 갱신."""
    service = DeviceService(db)
    await service.heartbeat(current_user["id"], device_id, body.connection_address)
    return {"status": "ok"}
