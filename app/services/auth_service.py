"""Authentication business logic: register, login."""
from __future__ import annotations

import logging

import aiosqlite

from app.exceptions import DuplicateEmailError, InvalidCredentialsError
from app.security import hash_password, verify_password

logger = logging.getLogger(__name__)


class AuthService:
    """회원가입 및 로그인 비즈니스 로직."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def register(self, email: str, password: str) -> dict:
        """회원가입. 이메일 중복 검사 + bcrypt 해싱 후 저장.

        Returns:
            dict with id, email, created_at
        Raises:
            DuplicateEmailError: 이메일 중복 시
        """
        # 이메일 중복 검사
        cursor = await self.db.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        )
        existing = await cursor.fetchone()
        if existing is not None:
            raise DuplicateEmailError()

        # 비밀번호 해싱
        password_hash = hash_password(password)

        # 사용자 삽입
        cursor = await self.db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?) RETURNING id, email, created_at",
            (email, password_hash),
        )
        row = await cursor.fetchone()
        await self.db.commit()

        logger.info(f"User registered: {email}")
        return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}

    async def login(self, email: str, password: str) -> dict:
        """로그인. 비밀번호 검증 후 사용자 정보 반환.

        Returns:
            dict with id, email
        Raises:
            InvalidCredentialsError: 사용자 없음 또는 비밀번호 불일치
        """
        cursor = await self.db.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
        )
        row = await cursor.fetchone()

        if row is None:
            raise InvalidCredentialsError()

        # OAuth 전용 사용자 (password_hash가 NULL)
        if row["password_hash"] is None:
            raise InvalidCredentialsError()

        if not verify_password(password, row["password_hash"]):
            raise InvalidCredentialsError()

        logger.info(f"User logged in: {email}")
        return {"id": row["id"], "email": row["email"]}
