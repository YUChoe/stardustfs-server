"""Tests for device management endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

import aiosqlite

from app.security import create_access_token


@pytest.mark.asyncio
async def test_register_device(client: AsyncClient, auth_headers: dict):
    """디바이스 등록 성공."""
    resp = await client.post(
        "/devices",
        json={"name": "My PC", "os": "Windows", "connection_address": "192.168.1.10:9000"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My PC"
    assert data["os"] == "Windows"
    assert data["connection_address"] == "192.168.1.10:9000"
    assert data["is_online"] is True
    assert "id" in data
    assert "last_heartbeat" in data


@pytest.mark.asyncio
async def test_list_devices(client: AsyncClient, auth_headers: dict):
    """디바이스 목록 조회."""
    # 2개 등록
    await client.post(
        "/devices",
        json={"name": "PC-A", "os": "Linux", "connection_address": "10.0.0.1:9000"},
        headers=auth_headers,
    )
    await client.post(
        "/devices",
        json={"name": "PC-B", "os": "macOS", "connection_address": "10.0.0.2:9000"},
        headers=auth_headers,
    )

    resp = await client.get("/devices", headers=auth_headers)
    assert resp.status_code == 200
    devices = resp.json()
    assert len(devices) == 2
    names = {d["name"] for d in devices}
    assert names == {"PC-A", "PC-B"}


@pytest.mark.asyncio
async def test_delete_device(client: AsyncClient, auth_headers: dict):
    """디바이스 삭제 성공."""
    resp = await client.post(
        "/devices",
        json={"name": "ToDelete", "os": "Linux", "connection_address": "1.2.3.4:5000"},
        headers=auth_headers,
    )
    device_id = resp.json()["id"]

    del_resp = await client.delete(f"/devices/{device_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # 목록에서 사라졌는지 확인
    list_resp = await client.get("/devices", headers=auth_headers)
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_device_not_found(client: AsyncClient, auth_headers: dict):
    """존재하지 않는 디바이스 삭제 시 404."""
    resp = await client.delete("/devices/nonexistent-id", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_device_access_denied(
    client: AsyncClient, db: aiosqlite.Connection, auth_headers: dict
):
    """다른 사용자의 디바이스 삭제 시 403."""
    # 다른 사용자 생성
    from app.security import hash_password

    cursor = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        ("other@example.com", hash_password("password123")),
    )
    other_row = await cursor.fetchone()
    other_user_id = other_row["id"]
    await db.commit()

    # 다른 사용자의 디바이스 등록
    other_token = create_access_token({"sub": other_user_id})
    other_headers = {"Authorization": f"Bearer {other_token}"}
    resp = await client.post(
        "/devices",
        json={"name": "OtherPC", "os": "Linux", "connection_address": "5.5.5.5:9000"},
        headers=other_headers,
    )
    other_device_id = resp.json()["id"]

    # 원래 사용자가 삭제 시도
    del_resp = await client.delete(f"/devices/{other_device_id}", headers=auth_headers)
    assert del_resp.status_code == 403


@pytest.mark.asyncio
async def test_heartbeat(client: AsyncClient, auth_headers: dict):
    """Heartbeat 갱신 성공."""
    resp = await client.post(
        "/devices",
        json={"name": "HB-PC", "os": "Linux", "connection_address": "10.0.0.1:9000"},
        headers=auth_headers,
    )
    device_id = resp.json()["id"]

    hb_resp = await client.put(
        f"/devices/{device_id}/heartbeat",
        json={"connection_address": "10.0.0.99:9000"},
        headers=auth_headers,
    )
    assert hb_resp.status_code == 200
    assert hb_resp.json()["status"] == "ok"

    # 목록에서 connection_address 갱신 확인
    list_resp = await client.get("/devices", headers=auth_headers)
    device = list_resp.json()[0]
    assert device["connection_address"] == "10.0.0.99:9000"


@pytest.mark.asyncio
async def test_heartbeat_without_address(client: AsyncClient, auth_headers: dict):
    """connection_address 없이 heartbeat 전송."""
    resp = await client.post(
        "/devices",
        json={"name": "HB-PC2", "os": "Linux", "connection_address": "10.0.0.1:9000"},
        headers=auth_headers,
    )
    device_id = resp.json()["id"]

    hb_resp = await client.put(
        f"/devices/{device_id}/heartbeat",
        json={},
        headers=auth_headers,
    )
    assert hb_resp.status_code == 200


@pytest.mark.asyncio
async def test_heartbeat_access_denied(
    client: AsyncClient, db: aiosqlite.Connection, auth_headers: dict
):
    """다른 사용자의 디바이스에 heartbeat 시 403."""
    from app.security import hash_password

    cursor = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        ("hb-other@example.com", hash_password("password123")),
    )
    other_row = await cursor.fetchone()
    other_user_id = other_row["id"]
    await db.commit()

    other_token = create_access_token({"sub": other_user_id})
    other_headers = {"Authorization": f"Bearer {other_token}"}
    resp = await client.post(
        "/devices",
        json={"name": "OtherHB", "os": "Linux", "connection_address": "5.5.5.5:9000"},
        headers=other_headers,
    )
    other_device_id = resp.json()["id"]

    hb_resp = await client.put(
        f"/devices/{other_device_id}/heartbeat",
        json={},
        headers=auth_headers,
    )
    assert hb_resp.status_code == 403


@pytest.mark.asyncio
async def test_device_list_isolation(
    client: AsyncClient, db: aiosqlite.Connection, auth_headers: dict
):
    """디바이스 목록 소유권 격리 - 다른 사용자의 디바이스가 보이지 않아야 한다."""
    from app.security import hash_password

    # 원래 사용자 디바이스 등록
    await client.post(
        "/devices",
        json={"name": "MyDevice", "os": "Linux", "connection_address": "10.0.0.1:9000"},
        headers=auth_headers,
    )

    # 다른 사용자 생성 + 디바이스 등록
    cursor = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        ("isolation@example.com", hash_password("password123")),
    )
    other_row = await cursor.fetchone()
    other_user_id = other_row["id"]
    await db.commit()

    other_token = create_access_token({"sub": other_user_id})
    other_headers = {"Authorization": f"Bearer {other_token}"}
    await client.post(
        "/devices",
        json={"name": "OtherDevice", "os": "macOS", "connection_address": "10.0.0.2:9000"},
        headers=other_headers,
    )

    # 원래 사용자 목록에는 자신의 디바이스만 보여야 함
    resp = await client.get("/devices", headers=auth_headers)
    devices = resp.json()
    assert len(devices) == 1
    assert devices[0]["name"] == "MyDevice"

    # 다른 사용자 목록에는 자신의 디바이스만 보여야 함
    resp2 = await client.get("/devices", headers=other_headers)
    devices2 = resp2.json()
    assert len(devices2) == 1
    assert devices2[0]["name"] == "OtherDevice"


@pytest.mark.asyncio
async def test_no_auth_returns_401(client: AsyncClient):
    """인증 없이 디바이스 API 접근 시 401."""
    resp = await client.get("/devices")
    assert resp.status_code in (401, 403)
