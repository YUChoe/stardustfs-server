"""Landing page tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_landing_page_returns_html(client: AsyncClient):
    """GET / 는 200 HTML 응답을 반환해야 한다."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_landing_page_content(client: AsyncClient):
    """랜딩 페이지에 주요 콘텐츠가 포함되어야 한다."""
    resp = await client.get("/")
    html = resp.text
    assert "StardustFS" in html
    assert "P2P" in html
    assert "/auth/register" in html
    assert "/auth/login" in html
