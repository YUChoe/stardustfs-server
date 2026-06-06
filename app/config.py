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

    # SEO — canonical/og:url용 절대 도메인. 비우면 요청 host에서 추론.
    # 예: STARDUST_SITE_URL=https://stardustfs.example.com
    site_url: str = ""

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

    # UDP 홀펀칭 랑데부 서버 — 직접 P2P 연결의 핵심이므로 기본 활성.
    rendezvous_enabled: bool = True
    rendezvous_host: str = "0.0.0.0"
    rendezvous_port: int = 9091

    # 리플리케이션 정책 (클라이언트가 /replication/policy로 내려받음)
    replication_reciprocity_fraction: float = 0.5  # 제공 용량 중 타인 보관 허용 비율
    replication_min_replicas: int = 1              # 목표 복제본 수(원본 외 추가 사본)

    # 릴레이 정책 — 서버 경유 P2P 릴레이는 서버 대역폭을 쓰는 최후 수단이므로 상품
    # 정책으로 허가를 통제한다. 허가하지 않으면 POST /relay/request가 403으로 거부된다.
    # 현재는 전역 스위치(운영 정책). 향후 사용자 등급(plan)별 허가는 여기에 끼운다.
    relay_enabled: bool = True

    class Config:
        env_file = ".env"
        env_prefix = "STARDUST_"


def get_settings() -> Settings:
    """Settings 싱글톤 인스턴스를 반환한다."""
    return Settings()
