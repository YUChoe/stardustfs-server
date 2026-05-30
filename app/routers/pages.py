"""Landing page router."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.i18n import detect_language, get_translations

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def landing_page(
    request: Request,
    lang: str | None = Query(default=None),
):
    """서비스 랜딩 페이지 렌더링. 인증 불필요. ?lang=ko|en 으로 언어 선택."""
    accept_lang = request.headers.get("accept-language")
    detected = detect_language(accept_lang, lang)
    t = get_translations(detected)
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"t": t},
    )


@router.get("/auth/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    lang: str | None = Query(default=None),
):
    """회원가입 폼 페이지. 인증 불필요."""
    accept_lang = request.headers.get("accept-language")
    detected = detect_language(accept_lang, lang)
    t = get_translations(detected)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"t": t},
    )


@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    lang: str | None = Query(default=None),
):
    """로그인 폼 페이지. 인증 불필요."""
    accept_lang = request.headers.get("accept-language")
    detected = detect_language(accept_lang, lang)
    t = get_translations(detected)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"t": t},
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    lang: str | None = Query(default=None),
):
    """사용자 세션 관리 대시보드. 클라이언트 측 인증 확인."""
    accept_lang = request.headers.get("accept-language")
    detected = detect_language(accept_lang, lang)
    t = get_translations(detected)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"t": t},
    )
