"""Loopback-only administration with same-origin mutation protection."""
import secrets
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .config import Settings
from .db import Database
from .protocol import DesiredRequest, AssociationRequest, install_errors
from .state import set_desired, confirm_association
from .inventory import get_status
from .catalog import scan_catalog, catalog_page, CatalogError


def create_admin_app(settings: Settings) -> FastAPI:
    db = Database(settings.database_path)
    scan_catalog(db, settings.music_root)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    install_errors(app)
    app.state.db = db
    app.state.settings = settings

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return JSONResponse({"detail": "Untrusted host"}, status_code=400)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected_origin = f"{request.url.scheme}://{request.url.netloc}"
            if origin is not None and origin != expected_origin:
                return JSONResponse({"detail": "Untrusted origin"}, status_code=403)
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), db.identity()["csrf_token"]):
                return JSONResponse({"detail": "Missing CSRF token"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; object-src 'none'"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/local/status")
    def status():
        return get_status(db) | {"csrf_token": db.identity()["csrf_token"]}

    @app.post("/api/local/rescan")
    def rescan():
        return scan_catalog(db, settings.music_root)

    @app.get("/api/local/catalog")
    def catalog(cursor: str | None = None):
        try:
            return catalog_page(db, cursor)
        except CatalogError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.put("/api/local/desired/{track_id}")
    def desired(track_id: str, body: DesiredRequest):
        return {"desired_revision": set_desired(db, track_id, body.present)}

    @app.post("/api/local/association/confirm")
    def association(body: AssociationRequest):
        return confirm_association(db, str(body.device_epoch), str(body.server_id))

    static = Path(__file__).with_name('static')
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/')
    def management_page():
        return FileResponse(static / 'index.html')

    return app
