"""Property-Based Tests for file sharing (MVP5).

Property 1: 공유 토큰 경로 격리 — 토큰에 묶인 경로만 valid, 그 외 모두 invalid
Property 2: 만료 단조성 — expires_at 전후 valid 전이, 한번 만료되면 회복 없음

ShareService를 인메모리 DB로 실제 구동하여 검증한다. ShareService가 async이므로
hypothesis 동기 테스트 본문에서 asyncio.run으로 구동한다.
"""
from __future__ import annotations

import asyncio
import os

import aiosqlite
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

os.environ.setdefault("STARDUST_JWT_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("STARDUST_DATABASE_URL", ":memory:")

from app.database import SCHEMA_SQL
from app.services.share_service import ShareService

# 경로 문자열 전략 (path traversal 무관, 일반 경로)
_path_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1, max_size=20,
)


async def _setup_share(bound_path: str, expires_in_seconds: int):
    """인메모리 DB에 사용자+디바이스+공유를 구성하고 (db, service, token) 반환."""
    db = await aiosqlite.connect(":memory:")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.executescript(SCHEMA_SQL)
    db.row_factory = aiosqlite.Row

    cursor = await db.execute(
        "INSERT INTO users (email, password_hash) VALUES ('o@e.com', 'h') "
        "RETURNING id"
    )
    owner_id = (await cursor.fetchone())["id"]
    cursor = await db.execute(
        "INSERT INTO devices (user_id, name, os, connection_address, "
        "last_heartbeat, is_online) "
        "VALUES (?, 'd', 'l', '127.0.0.1:9090', datetime('now'), 1) RETURNING id",
        (owner_id,),
    )
    device_id = (await cursor.fetchone())["id"]
    await db.commit()

    service = ShareService(db)
    result = await service.create_share(
        owner_id, device_id, bound_path, expires_in_seconds
    )
    return db, service, result["share_token"]


# ============================================================
# Property 1: 공유 토큰 경로 격리
# ============================================================


@settings(max_examples=150, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(bound_path=_path_strategy, request_path=_path_strategy)
def test_property1_path_isolation(bound_path, request_path):
    """verify는 요청 경로가 묶인 경로와 일치할 때만 valid=true."""
    async def run():
        db, service, token = await _setup_share(bound_path, 3600)
        try:
            result = await service.verify_share(token, request_path)
            if request_path == bound_path:
                assert result["valid"] is True
            else:
                assert result["valid"] is False
        finally:
            await db.close()

    asyncio.run(run())


# ============================================================
# Property 2: 만료 단조성
# ============================================================


@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(bound_path=_path_strategy)
def test_property2_expiry_monotonic(bound_path):
    """미만료면 (경로 일치 시) valid=true, 만료시키면 항상 valid=false."""
    async def run():
        db, service, token = await _setup_share(bound_path, 3600)
        try:
            # 미만료 + 경로 일치 → valid
            before = await service.verify_share(token, bound_path)
            assert before["valid"] is True

            # expires_at을 과거로 조작 (만료)
            await db.execute(
                "UPDATE shares SET expires_at = '2000-01-01T00:00:00' "
                "WHERE token = ?",
                (token,),
            )
            await db.commit()

            # 만료 후 경로가 일치해도 valid=false
            after = await service.verify_share(token, bound_path)
            assert after["valid"] is False

            # 재조회해도 여전히 false (회복 없음)
            again = await service.verify_share(token, bound_path)
            assert again["valid"] is False
        finally:
            await db.close()

    asyncio.run(run())


@settings(max_examples=80, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(expires_in=st.integers(min_value=1, max_value=2_592_000))
def test_property2_fresh_token_valid(expires_in):
    """임의의 유효 만료 시간으로 발급한 토큰은 즉시 검증 시 valid."""
    async def run():
        db, service, token = await _setup_share("a/b.txt", expires_in)
        try:
            result = await service.verify_share(token, "a/b.txt")
            assert result["valid"] is True
        finally:
            await db.close()

    asyncio.run(run())
