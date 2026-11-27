from typing import Any
from uuid import uuid4

import structlog
from starlette.types import Message, Receive, Scope, Send


class RequestIDMiddleware:
    """Attach a per-request identifier to the logs and the response.

    Pure ASGI middleware so every response carries the header, including the
    422 raised by validation and the 404 of an unknown route. A route
    dependency would only run once the request has matched a route.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            await self.app(scope, receive, send_with_request_id)
