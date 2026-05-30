"""Routing endpoint tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient

import aiosqlite


@pytest.mark.asyncio
async def test_routing_success(client: AsyncClient, auth_headers: dict, auth_user_id: str, db: aiosqlite.Connection):
    """라우팅 조회 성공 - 온라인 디바이스."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        "INSERT INTO devices (id, user_id, name, os, connection_address, last_heartbeat, is_online) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        ("dev-001", auth_user_id, "MyPC", "linux", "192.168.1.10:9000", now),
    )
    await db.commit()

    resp = await client.get("/routing/dev-001", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["device_id"] == "dev-001"
    assert data["connection_address"] == "192.168.1.10:9000"
    assert data["is_online"] is True


@pytest.mark.asyncio
async def test_routing_offline(client: AsyncClient, auth_headers: dict, auth_user_id: str, db: aiosqlite.Connection):
    """라우팅 조회 - 오프라인 디바이스 (heartbeat 10분 전)."""
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        "INSERT INTO devices (id, user_id, name, os, connection_address, last_heartbeat, is_online) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        ("dev-002", auth_user_id, "OldPC", "windows", "10.0.0.5:9000", old_time),
    )
    await db.commit()

    resp = await client.get("/routing/dev-002", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_online"] is False


@pytest.mark.asyncio
async def test_routing_not_found(client: AsyncClient, auth_headers: dict):
    """라우팅 조회 - 미존재 디바이스 404."""
    resp = await client.get("/routing/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_routing_access_denied(client: AsyncClient, auth_headers: dict, db: aiosqlite.Connection):
    """라우팅 조회 - 다른 사용자의 디바이스 403."""
    # 다른 사용자 생성
    from app.security import hash_password
    pw = hash_password("otherpass123")
    cursor = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        ("other@example.com", pw),
    )
    other_user = (await cursor.fetchone())["id"]
    await db.commit()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        "INSERT INTO devices (id, user_id, name, os, connection_address, last_heartbeat, is_online) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        ("dev-other", other_user, "OtherPC", "macos", "10.0.0.99:9000", now),
    )
    await db.commit()

    resp = await client.get("/routing/dev-other", headers=auth_headers)
    assert resp.status_code == 403
