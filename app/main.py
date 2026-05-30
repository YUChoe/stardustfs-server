"""StardustFS Central Server - FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.exceptions import StardustException
from app.routers import auth, devices, pages, routing, sync


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
