"""File sharing (MVP5) router.

읽기 전용 공유 토큰 발급/조회/검증 엔드포인트.
"""
from __future__ import annotations

import logging

import aiosqlite
from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_db
from app.schemas import (
    ShareCreateRequest,
    ShareCreateResponse,
    ShareInfoResponse,
    ShareVerifyRequest,
    ShareVerifyResponse,
)
from app.services.share_service import ShareService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shares", tags=["shares"])


@router.post("", response_model=ShareCreateResponse)
async def create_share(
    body: ShareCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """공유 토큰 발급 (소유자 인증 필요).

    device_id가 요청자의 소유인지 검증한다 (소유 아니면 403).
    """
    service = ShareService(db)
    result = await service.create_share(
        owner_user_id=current_user["id"],
        device_id=body.device_id,
        physical_path=body.physical_path,
        expires_in_seconds=body.expires_in_seconds,
    )
    return ShareCreateResponse(
        share_token=result["share_token"],
        expires_at=result["expires_at"],
    )


@router.get("/{token}", response_model=ShareInfoResponse)
async def get_share(
    token: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """공유 토큰 조회 (수신자 인증 필요). physical_path는 노출하지 않는다.

    토큰 미존재 404, 만료 410.
    """
    service = ShareService(db)
    info = await service.get_share(token)
    return ShareInfoResponse(device_id=info["device_id"], expired=info["expired"])


@router.post("/{token}/verify", response_model=ShareVerifyResponse)
async def verify_share(
    token: str,
    body: ShareVerifyRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """P2P 서버의 공유 토큰 위임 검증.

    토큰이 유효(존재·미만료)하고 physical_path가 일치하면 valid=true.
    인증을 요구하지 않는다 (P2P 서버가 호출하며, 토큰 자체가 자격증명).
    """
    service = ShareService(db)
    result = await service.verify_share(token, body.physical_path)
    return ShareVerifyResponse(
        valid=result["valid"], device_id=result["device_id"]
    )
