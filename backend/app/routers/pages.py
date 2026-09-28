from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"request": request, "page_title": "Ana Sayfa"},
    )


@router.get("/urunler", response_class=HTMLResponse)
def products_page(request: Request):
    return templates.TemplateResponse(
        request,
        "products.html",
        {"request": request, "page_title": "Ürünler"},
    )


@router.get("/urun-karsilastirmalari", response_class=HTMLResponse)
def product_comparisons_page(request: Request):
    return templates.TemplateResponse(
        request,
        "product_comparisons.html",
        {"request": request, "page_title": "Ürün Karşılaştırmaları"},
    )


@router.get("/riskli-urunler", response_class=HTMLResponse)
def risky_products_page(request: Request):
    return templates.TemplateResponse(
        request,
        "risky_products.html",
        {"request": request, "page_title": "Riskli Ürünler"},
    )


@router.get("/hakkinda", include_in_schema=False)
def about_page():
    return RedirectResponse(url="/", status_code=307)
