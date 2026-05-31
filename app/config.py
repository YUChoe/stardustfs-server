"""Application configuration using pydantic-settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """StardustFS Central Server 설정."""

    # 서버 설정
    app_name: str = "StardustFS Central Server"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # 데이터베이스
    database_url: str = "data/stardustfs.db"

    # JWT 설정
    jwt_secret_key: str  # 환경변수 필수
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # OAuth 설정
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    # Heartbeat 설정
    heartbeat_timeout_minutes: int = 5

    # Tombstone 정리(GC) 정책 — 클라이언트에 전달, 서버는 GC 직접 수행 안 함
    tombstone_retention_days: int = 30

    class Config:
        env_file = ".env"
        env_prefix = "STARDUST_"


def get_settings() -> Settings:
    """Settings 싱글톤 인스턴스를 반환한다."""
    return Settings()
