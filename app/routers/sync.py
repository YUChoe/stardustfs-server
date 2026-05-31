"""Metadata and key backup synchronisation router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, Response

import aiosqlite

from app.dependencies import get_current_user, get_db
from app.exceptions import StardustException
from app.schemas import MetadataUploadResponse
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


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
    return {"version": version}


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
    """메타데이터 백업 상태 조회 (version, uploaded_at)."""
    service = SyncService(db)
    status = await service.get_metadata_status(current_user["id"])
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
