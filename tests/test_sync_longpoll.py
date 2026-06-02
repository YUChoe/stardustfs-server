"""Tests for the metadata version long-polling endpoint."""
from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def _clear_notifier():
    """각 테스트 전후로 app.state의 VersionNotifier를 초기화한다."""
    if hasattr(app.state, "version_notifier"):
        delattr(app.state, "version_notifier")
    yield
    if hasattr(app.state, "version_notifier"):
        delattr(app.state, "version_notifier")


async def _upload(client: AsyncClient, headers: dict, blob: bytes,
                  base_version: int | None = None) -> int:
    h = dict(headers)
    if base_version is not None:
        h["X-Base-Version"] = str(base_version)
    resp = await client.put("/sync/metadata", content=blob, headers=h)
    assert resp.status_code == 200
    return resp.json()["version"]


@pytest.mark.asyncio
async def test_wait_returns_immediately_when_version_higher(
    client: AsyncClient, auth_headers: dict
):
    """서버 version이 known보다 크면 즉시 반환한다."""
    await _upload(client, auth_headers, b"blob-v1")  # version 1

    resp = await client.get(
        "/sync/metadata/wait", params={"known_version": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["changed"] is True
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_wait_wakes_on_upload(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """대기 중 다른 업로드로 version이 오르면 롱폴러가 깨어난다."""
    import app.routers.sync as sync_module
    monkeypatch.setattr(sync_module, "_WAIT_TIMEOUT", 10.0)

    await _upload(client, auth_headers, b"blob-v1")  # version 1

    async def waiter():
        return await client.get(
            "/sync/metadata/wait", params={"known_version": 1},
            headers=auth_headers,
        )

    async def uploader():
        await asyncio.sleep(0.3)
        await _upload(client, auth_headers, b"blob-v2", base_version=1)

    wait_resp, _ = await asyncio.gather(waiter(), uploader())
    assert wait_resp.status_code == 200
    data = wait_resp.json()
    assert data["changed"] is True
    assert data["version"] == 2


@pytest.mark.asyncio
async def test_wait_timeout_changed_false(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """타임아웃까지 변경 없으면 changed=false."""
    import app.routers.sync as sync_module
    monkeypatch.setattr(sync_module, "_WAIT_TIMEOUT", 0.5)
    monkeypatch.setattr(sync_module, "_WAIT_TICK", 0.2)

    await _upload(client, auth_headers, b"blob-v1")  # version 1

    resp = await client.get(
        "/sync/metadata/wait", params={"known_version": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["changed"] is False
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_wait_no_metadata_version_zero(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """메타데이터가 없으면 version 0, known_version 0이면 타임아웃."""
    import app.routers.sync as sync_module
    monkeypatch.setattr(sync_module, "_WAIT_TIMEOUT", 0.5)
    monkeypatch.setattr(sync_module, "_WAIT_TICK", 0.2)

    resp = await client.get(
        "/sync/metadata/wait", params={"known_version": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["changed"] is False
    assert data["version"] == 0


@pytest.mark.asyncio
async def test_wait_requires_auth(client: AsyncClient):
    """인증 없이 호출하면 401/403."""
    resp = await client.get("/sync/metadata/wait", params={"known_version": 0})
    assert resp.status_code in (401, 403)
