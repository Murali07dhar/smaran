"""RFC 7807 (application/problem+json) error responses for every error path."""
from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("smaran.errors")
PROBLEM_JSON = "application/problem+json"


def problem_response(
    request: Request, status: int, detail: str | None = None, headers: dict | None = None, **extra
) -> JSONResponse:
    try:
        title = HTTPStatus(status).phrase
    except ValueError:  # pragma: no cover
        title = "Error"
    body = {"type": "about:blank", "title": title, "status": status, "instance": request.url.path}
    if detail is not None:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else None
        extra = {} if detail is not None or exc.detail is None else {"errors": jsonable_encoder(exc.detail)}
        return problem_response(request, exc.status_code, detail, headers=exc.headers, **extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = jsonable_encoder(
            exc.errors(), custom_encoder={Exception: str, bytes: lambda b: b.decode("utf-8", "replace")}
        )
        return problem_response(request, 422, "Request validation failed", errors=errors)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return problem_response(request, 500, "Internal server error")
