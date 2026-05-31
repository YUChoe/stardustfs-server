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


# === 공통 ===


class ErrorResponse(BaseModel):
    """에러 응답."""

    detail: str
