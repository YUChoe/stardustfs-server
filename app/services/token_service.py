"""JWT token management: issue, refresh, revoke."""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite

from app.config import get_settings
from app.exceptions import TokenExpiredError, TokenInvalidError
from app.security import create_access_token, create_refresh_token, decode_token

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    """Refresh Token을 SHA-256 해시로 변환."""
    return hashlib.sha256(token.encode()).hexdigest()


class TokenService:
    """JWT 토큰 발급, 갱신, 무효화 관리."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def create_token_pair(self, user_id: str) -> dict:
        """Access Token(15분) + Refresh Token 쌍 생성.

        Returns:
            dict with access_token, refresh_token, token_type, expires_in
        """
        settings = get_settings()

        # 토큰 생성 (jti로 고유성 보장)
        access_token = create_access_token({"sub": user_id})
        refresh_token = create_refresh_token({"sub": user_id, "jti": uuid.uuid4().hex})

        # Refresh Token 해시를 DB에 저장
        token_hash = _hash_token(refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )

        await self.db.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, token_hash, expires_at.isoformat()),
        )
        await self.db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    async def refresh_tokens(self, refresh_token: str) -> dict:
        """Refresh Token 검증 후 새 토큰 쌍 발급. 이전 토큰 무효화(회전).

        재사용 감지 시 해당 사용자의 모든 토큰 무효화.

        Returns:
            dict with access_token, refresh_token, token_type, expires_in
        Raises:
            TokenInvalidError: 유효하지 않은 토큰
            TokenExpiredError: 만료된 토큰
        """
        # JWT 디코딩 (만료/서명 검증)
        payload = decode_token(refresh_token)

        # refresh 타입 검증
        if payload.get("type") != "refresh":
            raise TokenInvalidError()

        user_id = payload.get("sub")
        if user_id is None:
            raise TokenInvalidError()

        # DB에서 토큰 해시 조회
        token_hash = _hash_token(refresh_token)
        cursor = await self.db.execute(
            "SELECT id, is_revoked, user_id FROM refresh_tokens WHERE token_hash = ?",
            (token_hash,),
        )
        row = await cursor.fetchone()

        if row is None:
            raise TokenInvalidError()

        # 재사용 감지: 이미 무효화된 토큰이 사용됨
        if row["is_revoked"]:
            logger.warning(
                f"Refresh token reuse detected for user {user_id}, revoking all tokens"
            )
            await self.revoke_all_tokens(user_id)
            raise TokenInvalidError()

        # 이전 토큰 무효화 (회전)
        await self.db.execute(
            "UPDATE refresh_tokens SET is_revoked = 1 WHERE id = ?",
            (row["id"],),
        )
        await self.db.commit()

        # 새 토큰 쌍 발급
        result = await self.create_token_pair(user_id)
        return result

    async def revoke_all_tokens(self, user_id: str) -> None:
        """해당 사용자의 모든 Refresh Token 무효화."""
        await self.db.execute(
            "UPDATE refresh_tokens SET is_revoked = 1 WHERE user_id = ?",
            (user_id,),
        )
        await self.db.commit()
        logger.info(f"All refresh tokens revoked for user {user_id}")

    async def revoke_refresh_token(
        self, user_id: str, refresh_token: str
    ) -> None:
        """주어진 Refresh Token을 본인 소유일 때만 무효화한다 (멱등).

        토큰이 존재하지 않거나 이미 폐기되었어도 예외 없이 통과한다(UPDATE 0행).
        user_id 일치 조건으로 타 사용자 토큰 취소를 방지한다.
        """
        token_hash = _hash_token(refresh_token)
        await self.db.execute(
            "UPDATE refresh_tokens SET is_revoked = 1 "
            "WHERE user_id = ? AND token_hash = ?",
            (user_id, token_hash),
        )
        await self.db.commit()
        logger.info(f"Refresh token revoked for user {user_id}")
