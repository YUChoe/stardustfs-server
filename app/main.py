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
from app.routers import auth, devices, pages, routing, sync


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """앱 시작 시 DB 초기화."""
    await init_db()
    yield


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
app.include_router(pages.router)

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")
