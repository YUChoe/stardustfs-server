"""Landing page router."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """서비스 랜딩 페이지 렌더링. 인증 불필요."""
    return templates.TemplateResponse(request=request, name="landing.html")
