#!/usr/bin/env python3
"""StardustFS Central Server 엔트리포인트.

Usage:
    python main.py
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(env_file) and not os.environ.get("STARDUST_JWT_SECRET_KEY"):
        print(
            "ERROR: .env 파일이 없고 STARDUST_JWT_SECRET_KEY 환경변수도 설정되지 않았습니다.\n"
            "  1. cp .env.example .env\n"
            "  2. .env 파일에서 STARDUST_JWT_SECRET_KEY 값을 설정하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from app.config import get_settings
        settings = get_settings()
    except Exception as e:
        print(f"ERROR: 설정 로드 실패: {e}", file=sys.stderr)
        print(
            "  필수 환경변수: STARDUST_JWT_SECRET_KEY\n"
            "  .env 파일 또는 환경변수를 확인하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
