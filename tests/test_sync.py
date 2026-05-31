"""Tests for sync (metadata/key backup) endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_metadata(client: AsyncClient, auth_headers: dict):
    """메타데이터 업로드 성공."""
    blob = b"encrypted-metadata-blob-content"
    resp = await client.put(
        "/sync/metadata",
        content=blob,
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_upload_metadata_version_increment(client: AsyncClient, auth_headers: dict):
    """메타데이터 업로드 시 version 증가."""
    headers = {**auth_headers, "Content-Type": "application/octet-stream"}
    await client.put("/sync/metadata", content=b"blob1", headers=headers)
    resp = await client.put("/sync/metadata", content=b"blob2", headers=headers)
    assert resp.json()["version"] == 2


@pytest.mark.asyncio
async def test_download_metadata(client: AsyncClient, auth_headers: dict):
    """메타데이터 다운로드 성공."""
    blob = b"my-encrypted-metadata"
    headers = {**auth_headers, "Content-Type": "application/octet-stream"}
    await client.put("/sync/metadata", content=blob, headers=headers)

    resp = await client.get("/sync/metadata", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == blob
    assert resp.headers["X-Metadata-Version"] == "1"
    assert resp.headers["content-type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_download_metadata_latest(client: AsyncClient, auth_headers: dict):
    """여러 번 업로드 후 최신 blob 다운로드."""
    headers = {**auth_headers, "Content-Type": "application/octet-stream"}
    await client.put("/sync/metadata", content=b"old-data", headers=headers)
    await client.put("/sync/metadata", content=b"new-data", headers=headers)

    resp = await client.get("/sync/metadata", headers=auth_headers)
    assert resp.content == b"new-data"
    assert resp.headers["X-Metadata-Version"] == "2"


@pytest.mark.asyncio
async def test_download_metadata_not_found(client: AsyncClient, auth_headers: dict):
    """백업 미존재 시 404."""
    resp = await client.get("/sync/metadata", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_metadata_empty_body(client: AsyncClient, auth_headers: dict):
    """빈 body 업로드 시 422."""
    resp = await client.put(
        "/sync/metadata",
        content=b"",
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_metadata_status_includes_tombstone_retention(
    client: AsyncClient, auth_headers: dict
):
    """status 응답에 tombstone_retention_days 정책값이 포함된다 (기본 30)."""
    resp = await client.get("/sync/metadata/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "tombstone_retention_days" in data
    assert data["tombstone_retention_days"] == 30


@pytest.mark.asyncio
async def test_upload_metadata_cas_accepts_matching_base(
    client: AsyncClient, auth_headers: dict
):
    """X-Base-Version이 현재 서버 version과 일치하면 업로드 수락."""
    headers = {**auth_headers, "Content-Type": "application/octet-stream"}
    # 최초 업로드 (base=0, 서버 version 0)
    resp = await client.put(
        "/sync/metadata", content=b"v1",
        headers={**headers, "X-Base-Version": "0"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 1

    # base=1로 다음 업로드 → 수락, version 2
    resp = await client.put(
        "/sync/metadata", content=b"v2",
        headers={**headers, "X-Base-Version": "1"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2


@pytest.mark.asyncio
async def test_upload_metadata_cas_rejects_stale_base(
    client: AsyncClient, auth_headers: dict
):
    """X-Base-Version이 서버 version보다 낮으면(stale) 409 거부."""
    headers = {**auth_headers, "Content-Type": "application/octet-stream"}
    # 서버를 version 2까지 올림
    await client.put(
        "/sync/metadata", content=b"v1",
        headers={**headers, "X-Base-Version": "0"},
    )
    await client.put(
        "/sync/metadata", content=b"v2",
        headers={**headers, "X-Base-Version": "1"},
    )

    # 다른 디바이스가 stale base=1로 업로드 시도 → 409
    resp = await client.put(
        "/sync/metadata", content=b"stale",
        headers={**headers, "X-Base-Version": "1"},
    )
    assert resp.status_code == 409

    # 충돌 후에도 서버 데이터는 보존됨 (덮어쓰이지 않음)
    dl = await client.get("/sync/metadata", headers=auth_headers)
    assert dl.content == b"v2"
    assert dl.headers["X-Metadata-Version"] == "2"


@pytest.mark.asyncio
async def test_upload_metadata_without_base_version_forces(
    client: AsyncClient, auth_headers: dict
):
    """X-Base-Version 헤더가 없으면 CAS 없이 강제 업로드 (하위 호환)."""
    headers = {**auth_headers, "Content-Type": "application/octet-stream"}
    await client.put("/sync/metadata", content=b"v1", headers=headers)
    # 헤더 없이 또 업로드 → 충돌 없이 version 증가
    resp = await client.put("/sync/metadata", content=b"v2", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["version"] == 2


@pytest.mark.asyncio
async def test_upload_metadata_cas_invalid_header(
    client: AsyncClient, auth_headers: dict
):
    """X-Base-Version이 정수가 아니면 422."""
    resp = await client.put(
        "/sync/metadata", content=b"v1",
        headers={
            **auth_headers,
            "Content-Type": "application/octet-stream",
            "X-Base-Version": "not-a-number",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_key(client: AsyncClient, auth_headers: dict):
    """키 업로드 성공."""
    blob = b"encrypted-master-key"
    resp = await client.put(
        "/sync/key",
        content=blob,
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_download_key(client: AsyncClient, auth_headers: dict):
    """키 다운로드 성공."""
    blob = b"my-encrypted-key"
    headers = {**auth_headers, "Content-Type": "application/octet-stream"}
    await client.put("/sync/key", content=blob, headers=headers)

    resp = await client.get("/sync/key", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == blob
    assert resp.headers["content-type"] == "application/octet-stream"


@pytest.mark.asyncio
async def test_upload_key_upsert(client: AsyncClient, auth_headers: dict):
    """키 두 번 업로드 시 덮어쓰기."""
    headers = {**auth_headers, "Content-Type": "application/octet-stream"}
    await client.put("/sync/key", content=b"key-v1", headers=headers)
    await client.put("/sync/key", content=b"key-v2", headers=headers)

    resp = await client.get("/sync/key", headers=auth_headers)
    assert resp.content == b"key-v2"


@pytest.mark.asyncio
async def test_download_key_not_found(client: AsyncClient, auth_headers: dict):
    """키 백업 미존재 시 404."""
    resp = await client.get("/sync/key", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_key_empty_body(client: AsyncClient, auth_headers: dict):
    """빈 body 키 업로드 시 422."""
    resp = await client.put(
        "/sync/key",
        content=b"",
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_no_auth(client: AsyncClient):
    """인증 없이 sync API 접근 시 401."""
    resp = await client.get("/sync/metadata")
    assert resp.status_code in (401, 403)
