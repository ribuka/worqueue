"""ASGI middleware that refuses requests other sites' pages could send to the local server."""

from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

ALLOWED_HOSTS = ("127.0.0.1", "localhost")
SAFE_METHODS = ("GET", "HEAD")
JSON_MEDIA_TYPE = "application/json"


class RequestGuard:
    """Refuse a request whose ``Host`` is not local, or a write that is not JSON.

    A ``Host`` other than ``127.0.0.1`` or ``localhost`` is answered with 403, so a
    page of another site cannot reach the server through DNS rebinding. A request
    other than GET or HEAD whose ``Content-Type`` is not ``application/json`` is
    answered with 415: a page of another site can then send a write only with a CORS
    preflight, which the server never allows.

    Parameters
    ----------
    app : ASGIApp
        The application to protect.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass a request on, or answer it with 403 or 415."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if urlsplit(f"//{headers.get('host', '')}").hostname not in ALLOWED_HOSTS:
            response = JSONResponse({"error": "forbidden host"}, status_code=403)
        elif scope["method"] not in SAFE_METHODS and _media_type(headers) != JSON_MEDIA_TYPE:
            response = JSONResponse({"error": "JSON で送ってください"}, status_code=415)
        else:
            await self._app(scope, receive, send)
            return
        await response(scope, receive, send)


def _media_type(headers: Headers) -> str:
    """Return the media type of ``Content-Type`` in lower case, without its parameters."""
    return headers.get("content-type", "").split(";")[0].strip().lower()
