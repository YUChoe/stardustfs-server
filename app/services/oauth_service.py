"""OAuth authentication: Google and GitHub provider support."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import get_settings
from app.exceptions import InvalidCredentialsError, StardustException

logger = logging.getLogger(__name__)

# OAuth provider 설정
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USERINFO_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

SUPPORTED_PROVIDERS = ("google", "github")


class UnsupportedProviderError(StardustException):
    """미지원 OAuth provider."""

    def __init__(self, provider: str) -> None:
        super().__init__(400, f"Unsupported OAuth provider: {provider}")


class OAuthService:
    """OAuth 인증 코드 교환 및 사용자 정보 조회."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._http_client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 반환. 외부 주입이 없으면 새로 생성."""
        if self._http_client is not None:
            return self._http_client
        return httpx.AsyncClient()

    async def get_user_info(self, provider: str, code: str) -> dict:
        """OAuth provider에서 사용자 정보를 조회한다.

        Args:
            provider: 'google' 또는 'github'
            code: OAuth 인증 코드

        Returns:
            dict with email, name, oauth_id, oauth_provider

        Raises:
            UnsupportedProviderError: 미지원 provider
            InvalidCredentialsError: 인증 실패
        """
        if provider not in SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(provider)

        if provider == "google":
            return await self._google_auth(code)
        else:
            return await self._github_auth(code)

    async def _google_auth(self, code: str) -> dict:
        """Google OAuth 인증 코드 교환 + 사용자 정보 조회."""
        settings = get_settings()
        client = await self._get_client()
        should_close = self._http_client is None

        try:
            # 인증 코드 → access_token 교환
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": "postmessage",
                },
            )

            if token_resp.status_code != 200:
                logger.warning(f"Google token exchange failed: {token_resp.status_code}")
                raise InvalidCredentialsError()

            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise InvalidCredentialsError()

            # access_token으로 사용자 정보 조회
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if userinfo_resp.status_code != 200:
                logger.warning(f"Google userinfo failed: {userinfo_resp.status_code}")
                raise InvalidCredentialsError()

            userinfo = userinfo_resp.json()
            email = userinfo.get("email")
            if not email:
                raise InvalidCredentialsError()

            return {
                "email": email,
                "name": userinfo.get("name", ""),
                "oauth_id": userinfo.get("id", ""),
                "oauth_provider": "google",
            }
        finally:
            if should_close:
                await client.aclose()

    async def _github_auth(self, code: str) -> dict:
        """GitHub OAuth 인증 코드 교환 + 사용자 정보 조회."""
        settings = get_settings()
        client = await self._get_client()
        should_close = self._http_client is None

        try:
            # 인증 코드 → access_token 교환
            token_resp = await client.post(
                GITHUB_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                },
                headers={"Accept": "application/json"},
            )

            if token_resp.status_code != 200:
                logger.warning(f"GitHub token exchange failed: {token_resp.status_code}")
                raise InvalidCredentialsError()

            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise InvalidCredentialsError()

            # 사용자 정보 조회
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
            userinfo_resp = await client.get(GITHUB_USERINFO_URL, headers=headers)

            if userinfo_resp.status_code != 200:
                logger.warning(f"GitHub userinfo failed: {userinfo_resp.status_code}")
                raise InvalidCredentialsError()

            userinfo = userinfo_resp.json()
            email = userinfo.get("email")

            # GitHub에서 이메일이 비공개인 경우 emails API 사용
            if not email:
                emails_resp = await client.get(GITHUB_EMAILS_URL, headers=headers)
                if emails_resp.status_code == 200:
                    emails = emails_resp.json()
                    for e in emails:
                        if e.get("primary") and e.get("verified"):
                            email = e.get("email")
                            break

            if not email:
                raise InvalidCredentialsError()

            return {
                "email": email,
                "name": userinfo.get("name") or userinfo.get("login", ""),
                "oauth_id": str(userinfo.get("id", "")),
                "oauth_provider": "github",
            }
        finally:
            if should_close:
                await client.aclose()
