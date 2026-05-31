"""Authentication router: register, login, oauth, refresh."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

import aiosqlite

from app.dependencies import get_db
from app.schemas import (
    LoginRequest,
    OAuthRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.services.auth_service import AuthService
from app.services.oauth_service import OAuthService
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(body: RegisterRequest, db: aiosqlite.Connection = Depends(get_db)):
    """이메일/비밀번호 회원가입."""
    auth_service = AuthService(db)
    user = await auth_service.register(body.email, body.password)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    """로그인, JWT 발급."""
    auth_service = AuthService(db)
    user = await auth_service.login(body.email, body.password)

    token_service = TokenService(db)
    tokens = await token_service.create_token_pair(user["id"])
    return tokens


@router.post("/oauth/{provider}", response_model=TokenResponse)
async def oauth_login(
    provider: str,
    body: OAuthRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """OAuth 로그인 (Google/GitHub).

    신규 사용자 자동 생성, 기존 이메일 계정 연결.
    """
    oauth_service = OAuthService()
    user_info = await oauth_service.get_user_info(provider, body.code)

    # DB에서 이메일로 기존 사용자 조회
    cursor = await db.execute(
        "SELECT id, email FROM users WHERE email = ?", (user_info["email"],)
    )
    row = await cursor.fetchone()

    if row is not None:
        # 기존 사용자: OAuth 정보 연결
        user_id = row["id"]
        await db.execute(
            "UPDATE users SET oauth_provider = ?, oauth_id = ? WHERE id = ?",
            (user_info["oauth_provider"], user_info["oauth_id"], user_id),
        )
        await db.commit()
        logger.info(f"OAuth linked to existing user: {user_info['email']}")
    else:
        # 신규 사용자 자동 생성
        cursor = await db.execute(
            "INSERT INTO users (email, oauth_provider, oauth_id) "
            "VALUES (?, ?, ?) RETURNING id",
            (user_info["email"], user_info["oauth_provider"], user_info["oauth_id"]),
        )
        new_row = await cursor.fetchone()
        user_id = new_row["id"]
        await db.commit()
        logger.info(f"OAuth new user created: {user_info['email']}")

    # 토큰 발급
    token_service = TokenService(db)
    tokens = await token_service.create_token_pair(user_id)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Refresh Token으로 토큰 갱신."""
    token_service = TokenService(db)
    tokens = await token_service.refresh_tokens(body.refresh_token)
    return tokens


@router.post("/verify", response_model=VerifyResponse)
async def verify(body: VerifyRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Access Token 검증 (P2P 서버의 토큰 위임 검증용).

    서명·만료·타입을 확인하고, 사용자 존재를 확인하여
    유효 여부와 user_id를 반환한다. 무효 토큰도 200으로 valid=false를 반환한다
    (P2P 서버가 valid 플래그로 판정하므로).
    """
    from app.security import decode_token

    try:
        payload = decode_token(body.token)
    except Exception:
        return VerifyResponse(valid=False)

    if payload.get("type") != "access":
        return VerifyResponse(valid=False)

    user_id = payload.get("sub")
    if user_id is None:
        return VerifyResponse(valid=False)

    cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    if row is None:
        return VerifyResponse(valid=False)

    return VerifyResponse(valid=True, user_id=user_id)
