"""Metadata and key backup synchronisation router."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, Response

import aiosqlite

from app.dependencies import get_current_user, get_db
from app.exceptions import StardustException
from app.schemas import MetadataUploadResponse
from app.services.sync_service import SyncService
from app.services.version_notifier import VersionNotifier

router = APIRouter(prefix="/sync", tags=["sync"])

# 롱폴링 설정
_WAIT_TIMEOUT = 25.0  # 전체 대기 한계 (리버스 프록시 60초 이내)
_WAIT_TICK = 5.0      # 내부 재확인 주기 (알림 누락 보정)


def get_version_notifier(request: Request) -> VersionNotifier:
    """app.state의 단일 VersionNotifier 인스턴스를 반환한다."""
    notifier = getattr(request.app.state, "version_notifier", None)
    if notifier is None:
        notifier = VersionNotifier()
        request.app.state.version_notifier = notifier
    return notifier


@router.put("/metadata", response_model=MetadataUploadResponse)
async def upload_metadata(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """메타데이터 백업 업로드 (application/octet-stream).

    X-Base-Version 헤더가 있으면 낙관적 잠금(CAS)을 적용한다.
    헤더 값이 서버의 현재 version과 일치하지 않으면 409를 반환한다.
    헤더가 없으면 강제 덮어쓰기(force)로 동작한다(하위 호환).
    """
    blob = await request.body()
    if not blob:
        raise StardustException(422, "Request body must not be empty")

    base_version: int | None = None
    base_version_header = request.headers.get("X-Base-Version")
    if base_version_header is not None:
        try:
            base_version = int(base_version_header)
        except ValueError:
            raise StardustException(
                422, "X-Base-Version header must be an integer"
            )

    service = SyncService(db)
    version = await service.upload_metadata(
        current_user["id"], blob, base_version=base_version
    )
    # version 증가 성공 → 대기 중인 롱폴러를 깨운다 (CAS 충돌이면 위에서 409로 반환됨)
    get_version_notifier(request).notify(current_user["id"])
    return {"version": version}


@router.get("/metadata/wait")
async def wait_metadata_version(
    request: Request,
    known_version: int = 0,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """메타데이터 version 변경 롱폴링.

    서버 version이 known_version보다 크면 즉시 반환한다. 같으면 version이
    증가할 때까지(타임아웃 내) 대기한다. 타임아웃 시 changed=false로 현재
    version을 반환한다(클라이언트는 즉시 재대기).
    """
    service = SyncService(db)
    notifier = get_version_notifier(request)
    user_id = current_user["id"]

    deadline = time.monotonic() + _WAIT_TIMEOUT
    current = await service.get_current_version(user_id)
    if current > known_version:
        return {"version": current, "changed": True}

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        await notifier.wait(user_id, timeout=min(remaining, _WAIT_TICK))
        current = await service.get_current_version(user_id)
        if current > known_version:
            return {"version": current, "changed": True}

    return {"version": current, "changed": False}


@router.get("/metadata")
async def download_metadata(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """메타데이터 백업 다운로드 (application/octet-stream + X-Metadata-Version 헤더)."""
    service = SyncService(db)
    blob, version = await service.download_metadata(current_user["id"])
    return Response(
        content=blob,
        media_type="application/octet-stream",
        headers={"X-Metadata-Version": str(version)},
    )


@router.get("/metadata/status")
async def metadata_status(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """메타데이터 백업 상태 조회 (version, uploaded_at, tombstone 정책)."""
    from app.config import get_settings

    service = SyncService(db)
    status = await service.get_metadata_status(current_user["id"])
    # tombstone GC 정책값을 클라이언트에 전달 (서버는 GC를 직접 수행하지 않음)
    status["tombstone_retention_days"] = get_settings().tombstone_retention_days
    return status


@router.put("/key", status_code=status.HTTP_200_OK)
async def upload_key(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """암호화 키 백업 업로드 (application/octet-stream)."""
    blob = await request.body()
    if not blob:
        raise StardustException(422, "Request body must not be empty")

    service = SyncService(db)
    await service.upload_key(current_user["id"], blob)
    return {"status": "ok"}


@router.get("/key")
async def download_key(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """암호화 키 백업 다운로드 (application/octet-stream)."""
    service = SyncService(db)
    blob = await service.download_key(current_user["id"])
    return Response(
        content=blob,
        media_type="application/octet-stream",
    )
