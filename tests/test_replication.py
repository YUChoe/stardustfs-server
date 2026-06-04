"""리플리케이션(레지스트리/배치/회계/건강성) 엔드포인트 테스트."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _token(client: AsyncClient, email: str) -> str:
    await client.post(
        "/auth/register", json={"email": email, "password": "securepass123"}
    )
    resp = await client.post(
        "/auth/login", json={"email": email, "password": "securepass123"}
    )
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _device(client: AsyncClient, token: str, name: str) -> str:
    resp = await client.post(
        "/devices",
        json={"name": name, "os": "Linux", "connection_address": "127.0.0.1:9090"},
        headers=_h(token),
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_policy_returns_defaults(client: AsyncClient):
    a = await _token(client, "rep-policy@example.com")
    r = await client.get("/replication/policy", headers=_h(a))
    assert r.status_code == 200
    body = r.json()
    assert body["reciprocity_fraction"] == 0.5
    assert body["min_replicas"] == 1


@pytest.mark.asyncio
async def test_policy_requires_auth(client: AsyncClient):
    r = await client.get("/replication/policy")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_register_chunk_and_replica_and_list(client: AsyncClient):
    a = await _token(client, "rep-a@example.com")
    b = await _token(client, "rep-b@example.com")
    dev_b = await _device(client, b, "host-b")

    # A가 청크 등록
    r = await client.post(
        "/replication/chunks",
        json={"chunk_id": "c1", "file_ref": "f1", "idx": 0, "size": 100},
        headers=_h(a),
    )
    assert r.status_code == 200

    # A가 B의 디바이스에 복제본 저장 확정
    r = await client.post(
        "/replication/replicas",
        json={"chunk_id": "c1", "holder_device_id": dev_b},
        headers=_h(a),
    )
    assert r.status_code == 200

    # 홀더 목록 조회
    r = await client.get("/replication/replicas/c1", headers=_h(a))
    assert r.status_code == 200
    holders = r.json()
    assert len(holders) == 1
    assert holders[0]["device_id"] == dev_b
    assert holders[0]["is_online"] is True

    # 건강성
    r = await client.get("/replication/health/c1", headers=_h(a))
    assert r.json() == {"chunk_id": "c1", "total": 1, "online": 1}


@pytest.mark.asyncio
async def test_list_chunks_by_file_ref_owner_scoped(client: AsyncClient):
    a = await _token(client, "rep-k@example.com")
    b = await _token(client, "rep-l@example.com")
    # A가 file_ref="fr1"에 청크 2개 등록(idx 역순으로 넣어도 정렬 확인)
    for chunk_id, idx in (("k1", 1), ("k0", 0)):
        await client.post(
            "/replication/chunks",
            json={"chunk_id": chunk_id, "file_ref": "fr1", "idx": idx, "size": 10},
            headers=_h(a),
        )
    # B가 다른 file_ref에 등록(격리 확인)
    await client.post(
        "/replication/chunks",
        json={"chunk_id": "kb", "file_ref": "fr1", "idx": 0, "size": 10},
        headers=_h(b),
    )
    r = await client.get("/replication/chunks/fr1", headers=_h(a))
    assert r.status_code == 200
    rows = r.json()
    assert [row["chunk_id"] for row in rows] == ["k0", "k1"]  # idx 순
    # B는 자신의 청크만
    r = await client.get("/replication/chunks/fr1", headers=_h(b))
    assert [row["chunk_id"] for row in r.json()] == ["kb"]
    # 등록 없는 file_ref → 빈 목록
    r = await client.get("/replication/chunks/none", headers=_h(a))
    assert r.json() == []


@pytest.mark.asyncio
async def test_replica_requires_owned_chunk(client: AsyncClient):
    a = await _token(client, "rep-c@example.com")
    b = await _token(client, "rep-d@example.com")
    dev_a = await _device(client, a, "host-a")
    # B가 등록한 청크
    await client.post(
        "/replication/chunks",
        json={"chunk_id": "cb", "file_ref": "f", "idx": 0, "size": 10},
        headers=_h(b),
    )
    # A가 B 소유 청크에 복제 기록 시도 → 404
    r = await client.post(
        "/replication/replicas",
        json={"chunk_id": "cb", "holder_device_id": dev_a},
        headers=_h(a),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_placement_respects_capacity_and_reciprocity(client: AsyncClient):
    a = await _token(client, "rep-e@example.com")
    b = await _token(client, "rep-f@example.com")
    dev_b = await _device(client, b, "host-b")

    # 용량 미신고 → 후보 없음
    r = await client.post(
        "/replication/placement", json={"size": 10, "count": 3}, headers=_h(a)
    )
    assert r.json()["holders"] == []

    # B가 provided=100 신고 → 가용 50(=0.5*100)
    r = await client.post(
        "/replication/hosting",
        json={"device_id": dev_b, "provided_bytes": 100},
        headers=_h(b),
    )
    assert r.status_code == 200

    # size 40 → 50 >= 40 → 후보 포함
    r = await client.post(
        "/replication/placement", json={"size": 40, "count": 3}, headers=_h(a)
    )
    holders = r.json()["holders"]
    assert any(h["device_id"] == dev_b for h in holders)

    # size 60 → 50 < 60 → 호혜 한도 초과로 제외
    r = await client.post(
        "/replication/placement", json={"size": 60, "count": 3}, headers=_h(a)
    )
    assert all(h["device_id"] != dev_b for h in r.json()["holders"])

    # exclude로 제외
    r = await client.post(
        "/replication/placement",
        json={"size": 40, "count": 3, "exclude": [dev_b]}, headers=_h(a),
    )
    assert all(h["device_id"] != dev_b for h in r.json()["holders"])


@pytest.mark.asyncio
async def test_non_providing_device_never_placed(client: AsyncClient):
    """호혜 미충족(제공 용량 미신고) device는 신규 배치 후보에서 제외된다(6.3)."""
    a = await _token(client, "rep-m@example.com")
    b = await _token(client, "rep-n@example.com")
    # B 디바이스는 온라인이지만 provided_bytes를 신고하지 않음
    dev_b = await _device(client, b, "host-b")
    r = await client.post(
        "/replication/placement", json={"size": 1, "count": 3}, headers=_h(a)
    )
    assert all(h["device_id"] != dev_b for h in r.json()["holders"])


@pytest.mark.asyncio
async def test_set_hosting_requires_own_device(client: AsyncClient):
    a = await _token(client, "rep-g@example.com")
    b = await _token(client, "rep-h@example.com")
    dev_b = await _device(client, b, "host-b")
    # A가 B의 디바이스 용량 신고 시도 → 404
    r = await client.post(
        "/replication/hosting",
        json={"device_id": dev_b, "provided_bytes": 100}, headers=_h(a),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_replica_record_is_idempotent_for_hosted_bytes(client: AsyncClient):
    a = await _token(client, "rep-i@example.com")
    b = await _token(client, "rep-j@example.com")
    dev_b = await _device(client, b, "host-b")
    await client.post(
        "/replication/hosting",
        json={"device_id": dev_b, "provided_bytes": 1000}, headers=_h(b),
    )
    await client.post(
        "/replication/chunks",
        json={"chunk_id": "cidem", "file_ref": "f", "idx": 0, "size": 100},
        headers=_h(a),
    )
    # 동일 복제본 두 번 기록 → hosted_bytes는 1회만 증가(멱등)
    for _ in range(2):
        r = await client.post(
            "/replication/replicas",
            json={"chunk_id": "cidem", "holder_device_id": dev_b}, headers=_h(a),
        )
        assert r.status_code == 200
    # size 가용: 0.5*1000 - 100(1회만) = 400 >= 400 이어야 후보 포함
    r = await client.post(
        "/replication/placement", json={"size": 400, "count": 3}, headers=_h(a)
    )
    assert any(h["device_id"] == dev_b for h in r.json()["holders"])
    # 401 가용 초과(중복 가산됐다면 300만 남아 실패할 것) → 제외
    r = await client.post(
        "/replication/placement", json={"size": 401, "count": 3}, headers=_h(a)
    )
    assert all(h["device_id"] != dev_b for h in r.json()["holders"])
