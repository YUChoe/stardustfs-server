"""Tests for file sharing (MVP5) endpoints."""
from __future__ import annotations

import pytest
import aiosqlite
from httpx import AsyncClient

from app.security import create_access_token


async def _make_user(db: aiosqlite.Connection, email: str) -> tuple[str, dict]:
    """사용자를 생성하고 (user_id, auth_headers)를 반환한다."""
    from app.security import hash_password

    cursor = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        (email, hash_password("pw12345678")),
    )
    row = await cursor.fetchone()
    await db.commit()
    user_id = row["id"]
    token = create_access_token({"sub": user_id})
    return user_id, {"Authorization": f"Bearer {token}"}


async def _make_device(db: aiosqlite.Connection, user_id: str) -> str:
    """user_id 소유의 디바이스를 생성하고 device_id를 반환한다."""
    cursor = await db.execute(
        "INSERT INTO devices (user_id, name, os, connection_address, "
        "last_heartbeat, is_online) "
        "VALUES (?, 'dev', 'linux', '127.0.0.1:9090', datetime('now'), 1) "
        "RETURNING id",
        (user_id,),
    )
    row = await cursor.fetchone()
    await db.commit()
    return row["id"]


@pytest.mark.asyncio
async def test_create_share_success(
    client: AsyncClient, auth_headers: dict, auth_user_id: str, db
):
    """소유자가 자기 디바이스 파일에 공유 토큰을 발급한다."""
    device_id = await _make_device(db, auth_user_id)
    resp = await client.post(
        "/shares",
        json={"device_id": device_id, "physical_path": "a/b.txt",
              "expires_in_seconds": 3600},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["share_token"]
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_create_share_not_owner_403(
    client: AsyncClient, auth_headers: dict, db
):
    """다른 사용자의 디바이스로 공유 토큰을 발급하려 하면 403."""
    # B 소유의 디바이스
    other_id, _ = await _make_user(db, "owner-b@example.com")
    device_id = await _make_device(db, other_id)

    # A(auth_headers)가 B의 디바이스로 공유 시도
    resp = await client.post(
        "/shares",
        json={"device_id": device_id, "physical_path": "x.txt",
              "expires_in_seconds": 3600},
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_share_invalid_expiry_422(
    client: AsyncClient, auth_headers: dict, auth_user_id: str, db
):
    """expires_in_seconds 범위 밖이면 422."""
    device_id = await _make_device(db, auth_user_id)
    resp = await client.post(
        "/shares",
        json={"device_id": device_id, "physical_path": "x.txt",
              "expires_in_seconds": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_share_success(
    client: AsyncClient, auth_headers: dict, auth_user_id: str, db
):
    """수신자가 공유 토큰을 조회하면 device_id를 받는다 (physical_path 비노출)."""
    device_id = await _make_device(db, auth_user_id)
    create = await client.post(
        "/shares",
        json={"device_id": device_id, "physical_path": "secret/path.txt",
              "expires_in_seconds": 3600},
        headers=auth_headers,
    )
    token = create.json()["share_token"]

    # 수신자 B로 조회
    _b_id, b_headers = await _make_user(db, "recipient@example.com")
    resp = await client.get(f"/shares/{token}", headers=b_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["device_id"] == device_id
    assert data["expired"] is False
    # physical_path는 응답에 없어야 함
    assert "physical_path" not in data


@pytest.mark.asyncio
async def test_get_share_not_found_404(client: AsyncClient, auth_headers: dict):
    """존재하지 않는 토큰 조회 시 404."""
    resp = await client.get("/shares/nonexistent-token", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_share_expired_410(
    client: AsyncClient, auth_headers: dict, auth_user_id: str, db
):
    """만료된 토큰 조회 시 410."""
    device_id = await _make_device(db, auth_user_id)
    create = await client.post(
        "/shares",
        json={"device_id": device_id, "physical_path": "p.txt",
              "expires_in_seconds": 3600},
        headers=auth_headers,
    )
    token = create.json()["share_token"]

    # expires_at을 과거로 조작
    await db.execute(
        "UPDATE shares SET expires_at = '2000-01-01T00:00:00' WHERE token = ?",
        (token,),
    )
    await db.commit()

    resp = await client.get(f"/shares/{token}", headers=auth_headers)
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_verify_share_path_match(
    client: AsyncClient, auth_headers: dict, auth_user_id: str, db
):
    """verify는 경로가 일치할 때만 valid=true."""
    device_id = await _make_device(db, auth_user_id)
    create = await client.post(
        "/shares",
        json={"device_id": device_id, "physical_path": "a/b.txt",
              "expires_in_seconds": 3600},
        headers=auth_headers,
    )
    token = create.json()["share_token"]

    # 경로 일치 → valid
    ok = await client.post(f"/shares/{token}/verify",
                           json={"physical_path": "a/b.txt"})
    assert ok.status_code == 200
    assert ok.json()["valid"] is True

    # 경로 불일치 → invalid (경로 격리)
    bad = await client.post(f"/shares/{token}/verify",
                            json={"physical_path": "a/other.txt"})
    assert bad.status_code == 200
    assert bad.json()["valid"] is False


@pytest.mark.asyncio
async def test_verify_share_expired_monotonic(
    client: AsyncClient, auth_headers: dict, auth_user_id: str, db
):
    """만료되면 경로가 일치해도 valid=false (만료 단조성)."""
    device_id = await _make_device(db, auth_user_id)
    create = await client.post(
        "/shares",
        json={"device_id": device_id, "physical_path": "a/b.txt",
              "expires_in_seconds": 3600},
        headers=auth_headers,
    )
    token = create.json()["share_token"]

    await db.execute(
        "UPDATE shares SET expires_at = '2000-01-01T00:00:00' WHERE token = ?",
        (token,),
    )
    await db.commit()

    resp = await client.post(f"/shares/{token}/verify",
                             json={"physical_path": "a/b.txt"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


@pytest.mark.asyncio
async def test_routing_with_share_token_bypasses_ownership(
    client: AsyncClient, auth_headers: dict, auth_user_id: str, db
):
    """유효한 share_token 보유자는 소유권 없이도 routing 정보를 받는다."""
    device_id = await _make_device(db, auth_user_id)
    create = await client.post(
        "/shares",
        json={"device_id": device_id, "physical_path": "a/b.txt",
              "expires_in_seconds": 3600},
        headers=auth_headers,
    )
    token = create.json()["share_token"]

    # 수신자 B (디바이스 소유 아님)
    _b_id, b_headers = await _make_user(db, "recip2@example.com")

    # share_token 없이 → 403
    denied = await client.get(f"/routing/{device_id}", headers=b_headers)
    assert denied.status_code == 403

    # share_token 헤더 있으면 → 200
    ok = await client.get(
        f"/routing/{device_id}",
        headers={**b_headers, "X-Share-Token": token},
    )
    assert ok.status_code == 200
    assert ok.json()["device_id"] == device_id
