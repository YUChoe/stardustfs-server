"""Tests for OAuth login endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

import aiosqlite


@pytest.mark.asyncio
async def test_oauth_unsupported_provider(client: AsyncClient):
    """미지원 provider 요청 시 400."""
    resp = await client.post("/auth/oauth/facebook", json={"code": "some-code"})
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_oauth_google_new_user(client: AsyncClient, db: aiosqlite.Connection):
    """Google OAuth 신규 사용자 자동 생성."""
    mock_user_info = {
        "email": "google-user@gmail.com",
        "name": "Google User",
        "oauth_id": "google-123",
        "oauth_provider": "google",
    }

    with patch(
        "app.routers.auth.OAuthService.get_user_info",
        new_callable=AsyncMock,
        return_value=mock_user_info,
    ):
        resp = await client.post("/auth/oauth/google", json={"code": "valid-code"})

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    # DB에 사용자 생성 확인
    cursor = await db.execute(
        "SELECT email, oauth_provider, oauth_id FROM users WHERE email = ?",
        ("google-user@gmail.com",),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row["oauth_provider"] == "google"
    assert row["oauth_id"] == "google-123"


@pytest.mark.asyncio
async def test_oauth_github_existing_user_link(
    client: AsyncClient, db: aiosqlite.Connection
):
    """GitHub OAuth 기존 이메일 계정 연결."""
    from app.security import hash_password

    # 기존 사용자 생성
    await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?)",
        ("existing@example.com", hash_password("password123")),
    )
    await db.commit()

    mock_user_info = {
        "email": "existing@example.com",
        "name": "Existing User",
        "oauth_id": "github-456",
        "oauth_provider": "github",
    }

    with patch(
        "app.routers.auth.OAuthService.get_user_info",
        new_callable=AsyncMock,
        return_value=mock_user_info,
    ):
        resp = await client.post("/auth/oauth/github", json={"code": "valid-code"})

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data

    # OAuth 정보 연결 확인
    cursor = await db.execute(
        "SELECT oauth_provider, oauth_id FROM users WHERE email = ?",
        ("existing@example.com",),
    )
    row = await cursor.fetchone()
    assert row["oauth_provider"] == "github"
    assert row["oauth_id"] == "github-456"


@pytest.mark.asyncio
async def test_oauth_auth_failure(client: AsyncClient):
    """OAuth provider 인증 실패 시 401."""
    from app.exceptions import InvalidCredentialsError

    with patch(
        "app.routers.auth.OAuthService.get_user_info",
        new_callable=AsyncMock,
        side_effect=InvalidCredentialsError(),
    ):
        resp = await client.post("/auth/oauth/google", json={"code": "bad-code"})

    assert resp.status_code == 401
