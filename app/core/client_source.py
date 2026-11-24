"""
Which client (iOS app or web app) a request came from.

Clients send `X-Client: ios/<version>` or `X-Client: web`. Older iOS builds do not send it,
so the User-Agent is used as a fallback: URLSession requests carry `CFNetwork`, browsers
start with `Mozilla/`.
"""

from enum import Enum
from typing import Optional

from fastapi import Request

CLIENT_HEADER = "X-Client"


class ClientSource(str, Enum):
    IOS = "ios"
    WEB = "web"
    UNKNOWN = "unknown"


def detect_client_source(client_header: Optional[str], user_agent: Optional[str]) -> str:
    """Return the client source for the given `X-Client` and `User-Agent` values."""
    if client_header:
        name = client_header.split("/", 1)[0].strip().lower()
        if name in (ClientSource.IOS.value, ClientSource.WEB.value):
            return name

    agent = user_agent or ""
    if "CFNetwork" in agent:
        return ClientSource.IOS.value
    if agent.startswith("Mozilla/"):
        return ClientSource.WEB.value
    return ClientSource.UNKNOWN.value


def get_client_source(request: Request) -> str:
    """FastAPI dependency: the client source of the current request."""
    return detect_client_source(request.headers.get(CLIENT_HEADER), request.headers.get("user-agent"))
