"""Network reflexive address router (HTTP STUN equivalent).

진짜 UDP STUN 서버는 UDP hole punching용이지만, StardustFS P2P는 httpx 기반
HTTP(TCP)이므로 UDP 매핑을 재사용할 수 없다. 대신 STUN의 핵심 기능인
"요청자의 공인 IP 확인(server-reflexive address)"을 HTTP 엔드포인트로 제공한다.

이중 NAT 환경에서 UPnP가 보고한 외부 IP가 실제로는 사설/캐리어 대역인 경우,
클라이언트가 이 엔드포인트로 자신의 진짜 공인 IP를 확인하여 connection_address를
보정하는 데 사용한다.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_current_user
from app.schemas import ReflexiveAddressResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["network"])


def _client_public_ip(request: Request) -> str:
    """요청자의 공인 IP를 추출한다.

    리버스 프록시 뒤에 있을 수 있으므로 X-Forwarded-For의 첫 항목(원 클라이언트)을
    우선 사용하고, 없으면 직접 연결의 peer IP를 사용한다.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # "client, proxy1, proxy2" 형식 — 첫 항목이 원 클라이언트
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return ""


@router.get("/reflexive", response_model=ReflexiveAddressResponse)
async def get_reflexive_address(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> ReflexiveAddressResponse:
    """요청자의 server-reflexive(공인) IP를 반환한다.

    STUN Binding 요청의 HTTP 등가물. 클라이언트는 이 IP를 자신의 P2P
    connection_address 후보로 사용한다.
    """
    ip = _client_public_ip(request)
    logger.info(f"Reflexive address requested by user {current_user['id']}: {ip}")
    return ReflexiveAddressResponse(public_ip=ip)
