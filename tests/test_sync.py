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
