"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# === Auth 관련 ===


class RegisterRequest(BaseModel):
    """회원가입 요청."""

    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    """로그인 요청."""

    email: EmailStr
    password: str


class OAuthRequest(BaseModel):
    """OAuth 인증 코드 요청."""

    code: str


class TokenResponse(BaseModel):
    """토큰 발급 응답."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15분 = 900초


class RefreshRequest(BaseModel):
    """토큰 갱신 요청."""

    refresh_token: str


class VerifyRequest(BaseModel):
    """토큰 검증 요청 (P2P 서버용)."""

    token: str


class VerifyResponse(BaseModel):
    """토큰 검증 응답."""

    valid: bool
    user_id: str | None = None


class UserResponse(BaseModel):
    """사용자 정보 응답."""

    id: str
    email: str
    created_at: datetime


# === Device 관련 ===


class DeviceCreateRequest(BaseModel):
    """디바이스 등록 요청."""

    name: str = Field(min_length=1)
    os: str
    connection_address: str


class DeviceResponse(BaseModel):
    """디바이스 정보 응답."""

    id: str
    name: str
    os: str
    connection_address: str
    is_online: bool
    last_heartbeat: datetime
    created_at: datetime


class HeartbeatRequest(BaseModel):
    """Heartbeat 갱신 요청."""

    connection_address: str | None = None


# === Sync 관련 ===


class MetadataUploadResponse(BaseModel):
    """메타데이터 업로드 응답."""

    version: int


# === Share 관련 (MVP5) ===


class ShareCreateRequest(BaseModel):
    """공유 토큰 발급 요청."""

    device_id: str
    physical_path: str = Field(min_length=1)
    expires_in_seconds: int = Field(ge=1, le=2_592_000)  # 1초 ~ 30일


class ShareCreateResponse(BaseModel):
    """공유 토큰 발급 응답."""

    share_token: str
    expires_at: datetime


class ShareInfoResponse(BaseModel):
    """공유 토큰 조회 응답 (physical_path 비노출)."""

    device_id: str
    expired: bool


class ShareVerifyRequest(BaseModel):
    """P2P 서버의 공유 토큰 위임 검증 요청."""

    physical_path: str


class ShareVerifyResponse(BaseModel):
    """공유 토큰 검증 응답."""

    valid: bool
    device_id: str | None = None


# === Routing 관련 ===


class RoutingResponse(BaseModel):
    """디바이스 라우팅 정보 응답."""

    device_id: str
    connection_address: str
    is_online: bool
    last_heartbeat: datetime


# === Network 관련 ===


class ReflexiveAddressResponse(BaseModel):
    """server-reflexive(공인) 주소 조회 응답 (HTTP STUN 등가)."""

    public_ip: str


# === Relay 관련 (P2P 릴레이 fallback) ===


class RelayRequestBody(BaseModel):
    """릴레이 요청 (요청자 → 서버). payload는 불투명 blob."""

    target_device_id: str
    op: str
    payload: dict
    requester_device_id: str | None = None


class RelayRequestAccepted(BaseModel):
    """릴레이 요청 수락 응답."""

    request_id: str


class RelayPolled(BaseModel):
    """대상이 폴링으로 수신한 요청."""

    request_id: str
    op: str
    payload: dict
    requester_device_id: str | None = None


class RelayResponseBody(BaseModel):
    """릴레이 응답 (대상 → 서버). result는 불투명 blob."""

    status: int
    result: dict


# === 공통 ===


class ErrorResponse(BaseModel):
    """에러 응답."""

    detail: str


# --- 리플리케이션(패리티 백업) ---


class HostingRequest(BaseModel):
    """디바이스가 제공하는 스토리지 용량 신고."""

    device_id: str = Field(min_length=1)
    provided_bytes: int = Field(ge=0)


class PlacementRequest(BaseModel):
    """청크 복제 배치 요청."""

    size: int = Field(ge=1)
    count: int = Field(default=3, ge=1, le=10)
    exclude: list[str] = Field(default_factory=list)  # 제외할 device_id


class HolderInfo(BaseModel):
    """복제 대상 홀더 후보/현황."""

    device_id: str
    connection_address: str | None = None
    is_online: bool = True
    status: str = "active"


class PlacementResponse(BaseModel):
    """배치 결과(홀더 후보 목록)."""

    holders: list[HolderInfo]


class ChunkRegisterRequest(BaseModel):
    """청크 등록(소유자 기준)."""

    chunk_id: str = Field(min_length=1)
    file_ref: str = Field(min_length=1)
    idx: int = Field(ge=0)
    size: int = Field(ge=0)


class ReplicaRequest(BaseModel):
    """복제본 저장 확정(홀더 등록)."""

    chunk_id: str = Field(min_length=1)
    holder_device_id: str = Field(min_length=1)


class HealthResponse(BaseModel):
    """청크 복제 건강성."""

    chunk_id: str
    total: int
    online: int


class ChunkInfo(BaseModel):
    """파일(file_ref)에 속한 청크 메타(복구용)."""

    chunk_id: str
    idx: int
    size: int


class ReplicationPolicy(BaseModel):
    """클라이언트가 내려받는 리플리케이션 정책."""

    reciprocity_fraction: float
    min_replicas: int
