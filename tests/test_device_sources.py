"""디바이스 소스 레지스트리(신고/조회) 엔드포인트 테스트."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

import aiosqlite

from app.security import create_access_token, hash_password


async def _register(client: AsyncClient, headers: dict, name: str) -> str:
    resp = await client.post(
        "/devices",
        json={"name": name, "os": "Linux", "connection_address": "10.0.0.1:9000"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_report_and_list_sources(client: AsyncClient, auth_headers: dict):
    """신고한 소스가 조회에 device 정보와 함께 나타난다."""
    dev_id = await _register(client, auth_headers, "PC-A")
    resp = await client.put(
        f"/devices/{dev_id}/sources",
        json={"sources": [
            {"source_id": "loop-1", "type": "loopback",
             "capacity_bytes": 1000, "used_bytes": 300},
            {"source_id": "loop-2", "type": "loopback",
             "capacity_bytes": 2000, "used_bytes": 0},
        ]},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await client.get("/devices/sources", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    by_id = {r["source_id"]: r for r in rows}
    assert by_id["loop-1"]["device_id"] == dev_id
    assert by_id["loop-1"]["device_name"] == "PC-A"
    assert by_id["loop-1"]["capacity_bytes"] == 1000
    assert by_id["loop-1"]["used_bytes"] == 300
    assert by_id["loop-1"]["is_online"] is True


@pytest.mark.asyncio
async def test_report_replaces_previous(client: AsyncClient, auth_headers: dict):
    """재신고는 전량 교체(멱등)된다."""
    dev_id = await _register(client, auth_headers, "PC-A")
    await client.put(
        f"/devices/{dev_id}/sources",
        json={"sources": [{"source_id": "old", "type": "loopback",
                           "capacity_bytes": 1, "used_bytes": 0}]},
        headers=auth_headers,
    )
    await client.put(
        f"/devices/{dev_id}/sources",
        json={"sources": [{"source_id": "new", "type": "loopback",
                           "capacity_bytes": 2, "used_bytes": 0}]},
        headers=auth_headers,
    )
    rows = (await client.get("/devices/sources", headers=auth_headers)).json()
    assert [r["source_id"] for r in rows] == ["new"]


@pytest.mark.asyncio
async def test_report_unknown_device_rejected(
    client: AsyncClient, auth_headers: dict
):
    """존재하지 않는 device 신고는 404."""
    resp = await client.put(
        "/devices/nonexistent/sources",
        json={"sources": []},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ownership_isolation(client: AsyncClient, auth_headers: dict,
                                   db: aiosqlite.Connection):
    """다른 사용자의 device에는 신고할 수 없고, 조회는 본인 것만 반환한다."""
    dev_id = await _register(client, auth_headers, "PC-A")

    # 두 번째 사용자
    other_hash = hash_password("password456")
    cur = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        ("other@example.com", other_hash),
    )
    other_id = (await cur.fetchone())["id"]
    await db.commit()
    other_headers = {"Authorization": f"Bearer {create_access_token({'sub': other_id})}"}

    # 타인이 내 device에 신고 시도 → 403
    resp = await client.put(
        f"/devices/{dev_id}/sources",
        json={"sources": [{"source_id": "x", "type": "loopback",
                           "capacity_bytes": 1, "used_bytes": 0}]},
        headers=other_headers,
    )
    assert resp.status_code == 403

    # 타인의 조회에는 내 소스가 없어야 한다
    rows = (await client.get("/devices/sources", headers=other_headers)).json()
    assert rows == []
