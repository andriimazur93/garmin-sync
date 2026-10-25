"""Device-only API. Never mount local administration on this application."""
import secrets
from uuid import UUID
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .config import Settings
from .db import Database
from .protocol import SessionRequest, OperationResult, FinishRequest, InventoryPage, InventoryCommit, install_errors
from .sessions import open_session, plan_page, record_result, finish_session, authorize_media
from .media import media_response
from .inventory import stage_inventory_page, commit_inventory


def create_device_app(settings: Settings) -> FastAPI:
    db = Database(settings.database_path)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    install_errors(app)
    app.state.db = db
    app.state.settings = settings

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path.startswith("/api/v1/"):
            expected = "Bearer " + db.identity()["device_token"]
            if not secrets.compare_digest(request.headers.get("authorization", ""), expected):
                return JSONResponse({"detail": "Invalid device credential"}, status_code=401)
        if request.url.path.startswith('/api/v1/') and request.method in {'POST', 'PUT'}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 8192:
                    return JSONResponse({'detail': 'Request exceeds byte budget'}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/info")
    def info():
        return {"server_id": db.identity()["server_id"], "protocol_version": 1}

    @app.api_route("/api/v1/media/{track_id}", methods=["GET", "HEAD"])
    def media(track_id: str, request: Request):
        authorize_media(db, request.headers.get("x-sync-session"), track_id)
        return media_response(db, track_id, request.headers.get("range"), request.method == "HEAD")

    @app.post("/api/v1/sessions")
    def sessions(body: SessionRequest):
        return open_session(db, body)

    @app.get("/api/v1/sessions/{session_id}/plan")
    def plan(session_id: str, cursor: str | None = None):
        return plan_page(db, session_id, cursor)

    @app.put("/api/v1/sessions/{session_id}/results/{operation_id}")
    def results(session_id: str, operation_id: str, body: OperationResult):
        record_result(db, session_id, operation_id, body)
        return {"accepted": True}

    @app.post("/api/v1/sessions/{session_id}/finish")
    def finish(session_id: str, body: FinishRequest):
        finish_session(db, session_id, body.outcome)
        return {"accepted": True}

    @app.put('/api/v1/sessions/{session_id}/inventory/{generation_id}/pages/{page_number}')
    def inventory_page(session_id: UUID, generation_id: UUID, page_number: int, body: InventoryPage):
        stage_inventory_page(db, str(session_id), str(generation_id), page_number,
                             [entry.model_dump() for entry in body.entries])
        return {'accepted': True}

    @app.post('/api/v1/sessions/{session_id}/inventory/{generation_id}/commit')
    def inventory_commit(session_id: UUID, generation_id: UUID, body: InventoryCommit):
        return commit_inventory(db, str(session_id), str(generation_id), body.phase,
                                body.expected_pages, body.expected_entries)

    return app
