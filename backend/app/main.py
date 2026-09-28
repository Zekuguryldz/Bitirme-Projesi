from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.routers.dashboard import router as dashboard_router
from app.routers.notifications import router as notifications_router
from app.routers.pages import router as pages_router
from app.routers.products import router as products_router


app = FastAPI(
    title="Fiyat ve Shrinkflation Izleme Paneli",
    description="Supabase PostgreSQL veritabanindaki urun ve fiyat verilerini sunan FastAPI tabanli izleme uygulamasi.",
    version="1.0.0",
    docs_url=None,
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(pages_router)
app.include_router(products_router)
app.include_router(dashboard_router)
app.include_router(notifications_router)


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui() -> HTMLResponse:
    swagger_ui = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
    )
    custom_html = swagger_ui.body.decode("utf-8").replace(
        "</head>",
        "<style>.swagger-ui .topbar .download-url-wrapper, .swagger-ui .info a[href='/openapi.json'], .swagger-ui .info a[href='./openapi.json'] { display: none !important; }</style></head>",
    )
    response_headers = dict(swagger_ui.headers)
    response_headers.pop("content-length", None)
    return HTMLResponse(
        content=custom_html,
        status_code=swagger_ui.status_code,
        headers=response_headers,
    )


@app.get("/api", tags=["Root"], summary="Servis durum mesaji")
def root():
    return {"message": "Backend servisi calisiyor."}


@app.get("/health", tags=["Health"], summary="Veritabani baglanti kontrolu")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Veritabani baglantisi kurulamadi.",
        ) from exc

    return {"status": "ok"}
