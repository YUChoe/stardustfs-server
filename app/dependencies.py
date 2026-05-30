"""FastAPI dependency injection utilities."""
from __future__ import annotations

from collections.abc import AsyncGenerator

import aiosqlite
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.security import decode_token

security_scheme = HTTPBearer()


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """aiosqlite 연결을 yield하는 의존성."""
    settings = get_settings()
    db = await aiosqlite.connect(settings.database_url)
    try:
        await db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = aiosqlite.Row
        yield db
    finally:
        await db.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """Bearer 토큰에서 user_id 추출. 유효하지 않으면 401."""
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # access token 타입 검증
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # DB에서 사용자 존재 확인
    cursor = await db.execute("SELECT id, email FROM users WHERE id = ?", (user_id,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return {"id": row["id"], "email": row["email"]}
