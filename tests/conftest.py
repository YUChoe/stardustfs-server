"""Pytest fixtures for StardustFS Central Server tests."""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 테스트용 환경변수 설정 (import 전에 설정해야 함)
os.environ.setdefault("STARDUST_JWT_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("STARDUST_DATABASE_URL", ":memory:")

from app.database import SCHEMA_SQL
from app.main import app
from app.dependencies import get_db
from app.security import create_access_token

import aiosqlite


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """테스트용 인메모리 DB 연결."""
    conn = await aiosqlite.connect(":memory:")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.executescript(SCHEMA_SQL)
    await conn.commit()
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def client(db: aiosqlite.Connection) -> AsyncGenerator[AsyncClient, None]:
    """테스트용 AsyncClient. DB 의존성을 오버라이드."""

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(db: aiosqlite.Connection) -> dict:
    """테스트 사용자 생성 + Access Token 발급 → Authorization 헤더 반환."""
    from app.security import hash_password

    password_hash = hash_password("testpassword123")
    cursor = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        ("testuser@example.com", password_hash),
    )
    row = await cursor.fetchone()
    await db.commit()
    user_id = row["id"]

    token = create_access_token({"sub": user_id})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_user_id(db: aiosqlite.Connection, auth_headers: dict) -> str:
    """auth_headers fixture에서 생성된 사용자의 ID 반환."""
    cursor = await db.execute(
        "SELECT id FROM users WHERE email = ?", ("testuser@example.com",)
    )
    row = await cursor.fetchone()
    return row["id"]
