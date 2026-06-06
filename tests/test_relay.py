"""Tests for the P2P relay fallback endpoints (long-polling)."""
from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.main import app
from app.security import create_access_token, hash_password


async def _register_device(client: AsyncClient, headers: dict, name: str) -> str:
    """디바이스를 등록하고 device_id를 반환한다."""
    resp = await client.post(
        "/devices",
        json={"name": name, "os": "Linux", "connection_address": "10.0.0.1:9090"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture(autouse=True)
def _clear_relay_hub():
    """각 테스트 전후로 app.state의 RelayHub를 초기화한다."""
    if hasattr(app.state, "relay_hub"):
        delattr(app.state, "relay_hub")
    yield
    if hasattr(app.state, "relay_hub"):
        delattr(app.state, "relay_hub")


@pytest.mark.asyncio
async def test_relay_round_trip(client: AsyncClient, auth_headers: dict):
    """요청자가 올린 요청을 대상이 폴링→응답하면 요청자가 결과를 받는다."""
    device_id = await _register_device(client, auth_headers, "target-pc")

    async def requester():
        # 1. 요청 적재
        r = await client.post(
            "/relay/request",
            json={
                "target_device_id": device_id,
                "op": "read",
                "payload": {"physical_path": "f.bin", "source_id": "loop-001"},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        request_id = r.json()["request_id"]
        # 2. 응답 대기
        w = await client.get(
            f"/relay/response/{request_id}", headers=auth_headers
        )
        return w

    async def target():
        # 1. 폴링으로 요청 수신
        p = await client.get(
            "/relay/poll",
            params={"device_id": device_id},
            headers=auth_headers,
        )
        assert p.status_code == 200
        polled = p.json()
        assert polled["op"] == "read"
        assert polled["payload"]["physical_path"] == "f.bin"
        # 2. 결과 업로드 (불투명 result)
        await client.post(
            f"/relay/response/{polled['request_id']}",
            json={"status": 200, "result": {"data": "QUJD"}},
            headers=auth_headers,
        )

    w, _ = await asyncio.gather(requester(), target())
    assert w.status_code == 200
    envelope = w.json()
    assert envelope["status"] == 200
    assert envelope["result"]["data"] == "QUJD"


@pytest.mark.asyncio
async def test_relay_request_cross_user_forbidden(
    client: AsyncClient, auth_headers: dict, db
):
    """다른 user_id 소유 디바이스로의 릴레이 요청은 403."""
    # 대상 디바이스는 auth_headers 사용자 소유
    device_id = await _register_device(client, auth_headers, "owner-pc")

    # 다른 사용자 생성 + 토큰
    pw = hash_password("otherpassword123")
    cur = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        ("other@example.com", pw),
    )
    other_id = (await cur.fetchone())["id"]
    await db.commit()
    other_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': other_id})}"
    }

    r = await client.post(
        "/relay/request",
        json={
            "target_device_id": device_id,
            "op": "read",
            "payload": {},
        },
        headers=other_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_relay_replica_op_cross_user_allowed(
    client: AsyncClient, auth_headers: dict, db
):
    """복제본 op는 타 user_id 소유 디바이스로도 릴레이 큐잉이 허용된다(200).

    상호 호스팅 — 소유자=요청자 인가는 홀더 ParityStore가 집행하므로 서버 릴레이는
    교차 사용자를 막지 않는다.
    """
    device_id = await _register_device(client, auth_headers, "holder-pc")

    pw = hash_password("otherpassword123")
    cur = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id",
        ("owner@example.com", pw),
    )
    other_id = (await cur.fetchone())["id"]
    await db.commit()
    other_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': other_id})}"
    }

    for op in ("replica_store", "replica_fetch", "replica_delete"):
        r = await client.post(
            "/relay/request",
            json={
                "target_device_id": device_id,
                "op": op,
                "payload": {"chunk_id": "c1", "auth_token": "owner-token"},
            },
            headers=other_headers,
        )
        assert r.status_code == 200, op
        assert "request_id" in r.json()


@pytest.mark.asyncio
async def test_relay_request_unknown_device_404(
    client: AsyncClient, auth_headers: dict
):
    """존재하지 않는 대상 디바이스는 404."""
    r = await client.post(
        "/relay/request",
        json={
            "target_device_id": "nonexistent-device",
            "op": "read",
            "payload": {},
        },
        headers=auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_relay_response_timeout_504(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """대상이 응답하지 않으면 요청자는 504를 받는다."""
    import app.routers.relay as relay_module

    # 타임아웃을 짧게 패치
    monkeypatch.setattr(relay_module, "_RESPONSE_TIMEOUT", 0.3)

    device_id = await _register_device(client, auth_headers, "silent-pc")

    r = await client.post(
        "/relay/request",
        json={"target_device_id": device_id, "op": "read", "payload": {}},
        headers=auth_headers,
    )
    request_id = r.json()["request_id"]

    w = await client.get(
        f"/relay/response/{request_id}", headers=auth_headers
    )
    assert w.status_code == 504


@pytest.mark.asyncio
async def test_relay_poll_empty_204(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """대기열이 비어있으면 폴링은 204."""
    import app.routers.relay as relay_module

    monkeypatch.setattr(relay_module, "_POLL_TIMEOUT", 0.3)

    device_id = await _register_device(client, auth_headers, "idle-pc")

    p = await client.get(
        "/relay/poll",
        params={"device_id": device_id},
        headers=auth_headers,
    )
    assert p.status_code == 204


@pytest.mark.asyncio
async def test_relay_request_denied_when_policy_disabled(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """상품 정책으로 릴레이가 허가되지 않으면 POST /relay/request는 403."""
    import app.routers.relay as relay_module

    monkeypatch.setattr(relay_module, "_relay_permitted", lambda _u: False)
    device_id = await _register_device(client, auth_headers, "gated-pc")
    r = await client.post(
        "/relay/request",
        json={"target_device_id": device_id, "op": "read", "payload": {}},
        headers=auth_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_relay_requires_auth(client: AsyncClient):
    """인증 없이 호출하면 401/403."""
    r = await client.post(
        "/relay/request",
        json={"target_device_id": "x", "op": "read", "payload": {}},
    )
    assert r.status_code in (401, 403)
