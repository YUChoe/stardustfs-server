"""Database connection management and schema initialisation."""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import aiosqlite

from app.config import get_settings

logger = logging.getLogger(__name__)

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    oauth_provider TEXT,
    oauth_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    os TEXT NOT NULL,
    connection_address TEXT NOT NULL,
    last_heartbeat TEXT NOT NULL DEFAULT (datetime('now')),
    is_online INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id);

CREATE TABLE IF NOT EXISTS metadata_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    encrypted_blob BLOB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_metadata_backups_user_id ON metadata_backups(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_metadata_backups_user_version
    ON metadata_backups(user_id, version);

CREATE TABLE IF NOT EXISTS key_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    encrypted_blob BLOB NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    is_revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

CREATE TABLE IF NOT EXISTS shares (
    token TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    physical_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shares_owner ON shares(owner_user_id);

-- 리플리케이션(암호화 패리티 백업): 위치 레지스트리 + 상호 보관 회계 (zero-knowledge:
-- 청크 내용/키는 저장하지 않고 위치/크기/회계 메타데이터만 보관)
CREATE TABLE IF NOT EXISTS hosting (
    device_id TEXT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
    provided_bytes INTEGER NOT NULL DEFAULT 0,
    hosted_bytes INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_ref TEXT NOT NULL,
    idx INTEGER NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chunks_owner ON chunks(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(owner_user_id, file_ref);

CREATE TABLE IF NOT EXISTS replicas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    holder_device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(chunk_id, holder_device_id)
);

CREATE INDEX IF NOT EXISTS idx_replicas_chunk ON replicas(chunk_id);
CREATE INDEX IF NOT EXISTS idx_replicas_holder ON replicas(holder_device_id);

-- 디바이스 소스 레지스트리: 각 디바이스가 자신의 로컬 소스 인벤토리를 신고한다
-- (zero-knowledge: 식별자/타입/용량/사용 바이트만, 물리 경로·파일명은 저장하지 않음).
CREATE TABLE IF NOT EXISTS device_sources (
    device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    type TEXT NOT NULL,
    capacity_bytes INTEGER NOT NULL DEFAULT 0,
    used_bytes INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (device_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_device_sources_device ON device_sources(device_id);
"""


async def init_db() -> None:
    """데이터베이스 스키마를 초기화한다. 테이블이 없으면 생성한다."""
    settings = get_settings()
    db_path = settings.database_url

    # DB 파일이 위치할 디렉토리 생성
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(SCHEMA_SQL)
        await db.commit()

    logger.info(f"Database initialised at {db_path}")


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    """aiosqlite 연결을 yield하는 비동기 컨텍스트 매니저."""
    settings = get_settings()
    db = await aiosqlite.connect(settings.database_url)
    try:
        await db.execute("PRAGMA foreign_keys=ON")
        # 동시 writer가 즉시 SQLITE_BUSY로 실패하지 않고 락 해제를 대기하도록 설정.
        # CAS의 UNIQUE(user_id, version) 충돌을 정확히 감지하기 위해 필요.
        await db.execute("PRAGMA busy_timeout=5000")
        db.row_factory = aiosqlite.Row
        yield db
    finally:
        await db.close()
