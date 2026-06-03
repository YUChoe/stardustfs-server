"""StardustFS Central Server - FastAPI application entry point."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.exceptions import StardustException
from app.routers import (
    auth, devices, network, pages, relay, replication, routing, shares, sync,
)


def setup_logging() -> None:
    """로깅 포맷 설정. 시분초.ms + 레벨 + 위치 + 메시지."""
    fmt = "%(asctime)s.%(msecs)03d %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        stream=sys.stdout,
        force=True,
    )
    # uvicorn 로거도 동일 포맷 적용
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        uv_logger.addHandler(handler)
        uv_logger.propagate = False


setup_logging()


def _verify_access_token(token: str) -> str | None:
    """access JWT를 검증해 user_id(sub)를 반환한다. 실패 시 None.

    UDP 랑데부 서버용(HTTP 미들웨어 밖). DB 조회 없이 서명/만료만 본다.
    """
    from app.security import decode_token

    try:
        payload = decode_token(token)
    except Exception:
        return None
    if payload.get("type") != "access":
        return None
    return payload.get("sub")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """앱 시작 시 DB 초기화 + (선택) UDP 랑데부 서버 시작."""
    await init_db()

    from app.config import get_settings

    settings = get_settings()
    rendezvous = None
    if settings.rendezvous_enabled:
        from app.rendezvous import RendezvousServer

        rendezvous = RendezvousServer(
            settings.rendezvous_host,
            settings.rendezvous_port,
            _verify_access_token,
        )
        await rendezvous.start()
    try:
        yield
    finally:
        if rendezvous is not None:
            await rendezvous.stop()


app = FastAPI(title="StardustFS Central Server", lifespan=lifespan)


@app.exception_handler(StardustException)
async def stardust_exception_handler(request: Request, exc: StardustException) -> JSONResponse:
    """커스텀 예외를 JSON 응답으로 변환."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# 라우터 등록
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(sync.router)
app.include_router(routing.router)
app.include_router(network.router)
app.include_router(relay.router)
app.include_router(shares.router)
app.include_router(replication.router)
app.include_router(pages.router)

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")
