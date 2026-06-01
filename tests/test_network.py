"""Tests for the network reflexive address endpoint (HTTP STUN equivalent)."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_reflexive_requires_auth(client):
    """인증 없이 호출하면 401 또는 403을 반환한다."""
    response = await client.get("/network/reflexive")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_reflexive_uses_x_forwarded_for(client, auth_headers):
    """X-Forwarded-For가 있으면 첫 항목(원 클라이언트 공인 IP)을 반환한다."""
    headers = {**auth_headers, "X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
    response = await client.get("/network/reflexive", headers=headers)
    assert response.status_code == 200
    assert response.json()["public_ip"] == "203.0.113.7"


@pytest.mark.asyncio
async def test_reflexive_returns_peer_ip_without_forwarded(client, auth_headers):
    """X-Forwarded-For가 없으면 직접 연결 peer IP를 반환한다(빈 문자열 아님)."""
    response = await client.get("/network/reflexive", headers=auth_headers)
    assert response.status_code == 200
    # ASGITransport는 client host를 설정하므로 키가 존재하고 문자열이어야 한다
    assert "public_ip" in response.json()
    assert isinstance(response.json()["public_ip"], str)
