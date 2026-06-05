"""Landing page router."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.i18n import detect_language, get_translations

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory="templates")


def _site_base(request: Request) -> str:
    """canonical/og URL용 절대 도메인. STARDUST_SITE_URL 우선, 없으면 요청 host."""
    configured = get_settings().site_url
    base = configured if configured else str(request.base_url)
    return base.rstrip("/")


@router.get("/", response_class=HTMLResponse)
async def landing_page(
    request: Request,
    lang: str | None = Query(default=None),
):
    """서비스 랜딩 페이지 렌더링. 인증 불필요. ?lang=ko|en 으로 언어 선택."""
    accept_lang = request.headers.get("accept-language")
    detected = detect_language(accept_lang, lang)
    t = get_translations(detected)
    base = _site_base(request)
    seo = {
        "canonical": f"{base}/",
        "url_ko": f"{base}/?lang=ko",
        "url_en": f"{base}/?lang=en",
    }
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"t": t, "seo": seo},
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt(request: Request):
    """크롤러 지침. 공개 페이지만 색인 허용, 사이트맵 안내."""
    base = _site_base(request)
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /auth/\n"
        "Disallow: /dashboard\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
async def sitemap_xml(request: Request):
    """랜딩 페이지 사이트맵(ko/en hreflang 대체 포함)."""
    base = _site_base(request)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        "  <url>\n"
        f"    <loc>{base}/</loc>\n"
        f'    <xhtml:link rel="alternate" hreflang="ko" href="{base}/?lang=ko"/>\n'
        f'    <xhtml:link rel="alternate" hreflang="en" href="{base}/?lang=en"/>\n'
        f'    <xhtml:link rel="alternate" hreflang="x-default" href="{base}/"/>\n'
        "  </url>\n"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


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
