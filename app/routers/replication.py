"""리플리케이션(패리티 백업) 라우터.

위치 레지스트리/배치/회계/건강성. 모든 엔드포인트는 access_token 인증.
zero-knowledge: 청크 내용/키는 다루지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

import aiosqlite

from app.dependencies import get_current_user, get_db
from app.config import get_settings
from app.schemas import (
    ChunkInfo,
    ChunkRegisterRequest,
    HealthResponse,
    HolderInfo,
    HostingRequest,
    PlacementRequest,
    PlacementResponse,
    ReplicaRequest,
    ReplicationPolicy,
)
from app.services.replication_service import ReplicationService

router = APIRouter(prefix="/replication", tags=["replication"])


@router.get("/policy", response_model=ReplicationPolicy)
async def get_policy(current_user: dict = Depends(get_current_user)):
    """리플리케이션 정책(상호 보관 비율·목표 복제본 수)을 반환한다."""
    settings = get_settings()
    return ReplicationPolicy(
        reciprocity_fraction=settings.replication_reciprocity_fraction,
        min_replicas=settings.replication_min_replicas,
    )


@router.post("/hosting", status_code=status.HTTP_200_OK)
async def set_hosting(
    body: HostingRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """내 디바이스의 제공 용량을 신고한다."""
    service = ReplicationService(db)
    ok = await service.set_provided_bytes(
        current_user["id"], body.device_id, body.provided_bytes
    )
    if not ok:
        raise HTTPException(status_code=404, detail="device not found")
    return {"status": "ok"}


@router.post("/placement", response_model=PlacementResponse)
async def placement(
    body: PlacementRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """청크 복제 배치 후보(≤count)를 반환한다."""
    service = ReplicationService(db)
    holders = await service.placement(
        current_user["id"], body.size, body.count, body.exclude
    )
    return PlacementResponse(holders=[
        HolderInfo(device_id=h["device_id"],
                   connection_address=h["connection_address"])
        for h in holders
    ])


@router.post("/chunks", status_code=status.HTTP_200_OK)
async def register_chunk(
    body: ChunkRegisterRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """청크를 등록한다(소유자 기준)."""
    service = ReplicationService(db)
    await service.register_chunk(
        current_user["id"], body.chunk_id, body.file_ref, body.idx, body.size
    )
    return {"status": "ok"}


@router.get("/chunks/{file_ref}", response_model=list[ChunkInfo])
async def list_chunks(
    file_ref: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """파일(file_ref)에 속한 청크 목록(idx 순)을 반환한다(복구용, 소유자 한정)."""
    service = ReplicationService(db)
    rows = await service.list_chunks(current_user["id"], file_ref)
    return [
        ChunkInfo(chunk_id=r["chunk_id"], idx=r["idx"], size=r["size"])
        for r in rows
    ]


@router.post("/replicas", status_code=status.HTTP_200_OK)
async def record_replica(
    body: ReplicaRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """복제본 저장을 확정한다(홀더 등록)."""
    service = ReplicationService(db)
    ok = await service.record_replica(
        current_user["id"], body.chunk_id, body.holder_device_id
    )
    if not ok:
        raise HTTPException(
            status_code=404, detail="chunk not owned or holder not found"
        )
    return {"status": "ok"}


@router.get("/replicas/{chunk_id}", response_model=list[HolderInfo])
async def list_replicas(
    chunk_id: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """청크의 홀더 목록(온라인/주소)을 반환한다(복구용)."""
    service = ReplicationService(db)
    rows = await service.list_replicas(chunk_id)
    return [
        HolderInfo(
            device_id=r["device_id"], status=r["status"],
            is_online=r["is_online"], connection_address=r["connection_address"],
        )
        for r in rows
    ]


@router.get("/health/{chunk_id}", response_model=HealthResponse)
async def chunk_health(
    chunk_id: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """청크 복제 건강성(전체/온라인 복제 수)."""
    service = ReplicationService(db)
    return HealthResponse(**await service.health(chunk_id))
