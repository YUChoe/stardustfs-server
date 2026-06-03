"""Authentication endpoint tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """회원가입 성공 시 201 + UserResponse 반환."""
    resp = await client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "securepass123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """동일 이메일 중복 가입 시 409."""
    payload = {"email": "dup@example.com", "password": "securepass123"}
    resp1 = await client.post("/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/auth/register", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    """유효하지 않은 이메일 형식 시 422."""
    resp = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "securepass123"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    """8자 미만 비밀번호 시 422."""
    resp = await client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "short"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """로그인 성공 시 TokenResponse 반환."""
    await client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "securepass123"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "securepass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 900


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """잘못된 비밀번호 시 401."""
    await client.post(
        "/auth/register",
        json={"email": "wrong@example.com", "password": "securepass123"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "wrong@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """미등록 이메일 시 401."""
    resp = await client.post(
        "/auth/login",
        json={"email": "noone@example.com", "password": "securepass123"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_success(client: AsyncClient):
    """토큰 갱신 성공."""
    await client.post(
        "/auth/register",
        json={"email": "refresh@example.com", "password": "securepass123"},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "refresh@example.com", "password": "securepass123"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # 새 refresh token은 이전과 달라야 함
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_reuse_detection(client: AsyncClient):
    """이미 사용된 refresh token 재사용 시 401 + 전체 무효화."""
    await client.post(
        "/auth/register",
        json={"email": "reuse@example.com", "password": "securepass123"},
    )
    login_resp = await client.post(
        "/auth/login",
        json={"email": "reuse@example.com", "password": "securepass123"},
    )
    old_refresh = login_resp.json()["refresh_token"]

    # 첫 번째 갱신 (성공)
    refresh_resp = await client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_resp.status_code == 200
    new_refresh = refresh_resp.json()["refresh_token"]

    # 이전 토큰 재사용 (실패 + 전체 무효화)
    resp = await client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert resp.status_code == 401

    # 새 토큰도 무효화되었는지 확인
    resp2 = await client.post(
        "/auth/refresh",
        json={"refresh_token": new_refresh},
    )
    assert resp2.status_code == 401


async def _register_login(client: AsyncClient, email: str) -> dict:
    """등록 + 로그인 후 토큰 쌍을 반환한다."""
    await client.post(
        "/auth/register", json={"email": email, "password": "securepass123"}
    )
    resp = await client.post(
        "/auth/login", json={"email": email, "password": "securepass123"}
    )
    return resp.json()


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client: AsyncClient):
    """logout 후 해당 refresh 토큰은 무효화되어 갱신이 401."""
    tokens = await _register_login(client, "logout1@example.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert resp.status_code == 200

    # 취소된 토큰으로 갱신 시도 → 401
    refresh_resp = await client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_is_idempotent(client: AsyncClient):
    """이미 취소되었거나 존재하지 않는 토큰도 200(멱등)."""
    tokens = await _register_login(client, "logout2@example.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    first = await client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert first.status_code == 200
    # 두 번째(이미 취소됨)도 200
    second = await client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert second.status_code == 200
    # 존재하지 않는 토큰도 200
    third = await client.post(
        "/auth/logout",
        json={"refresh_token": "nonexistent-token"},
        headers=headers,
    )
    assert third.status_code == 200


@pytest.mark.asyncio
async def test_logout_requires_auth(client: AsyncClient):
    """access_token 없이 logout 시 401."""
    resp = await client.post(
        "/auth/logout", json={"refresh_token": "x"}
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_logout_does_not_revoke_other_users_token(client: AsyncClient):
    """타 사용자의 refresh 토큰은 취소되지 않는다(user-scoped)."""
    a_tokens = await _register_login(client, "logout-a@example.com")
    b_tokens = await _register_login(client, "logout-b@example.com")

    # A가 자기 access로 B의 refresh 토큰 취소 시도 → 200(멱등)이지만 실제로는 미취소
    resp = await client.post(
        "/auth/logout",
        json={"refresh_token": b_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {a_tokens['access_token']}"},
    )
    assert resp.status_code == 200

    # B의 refresh 토큰은 여전히 유효
    b_refresh = await client.post(
        "/auth/refresh", json={"refresh_token": b_tokens["refresh_token"]}
    )
    assert b_refresh.status_code == 200
