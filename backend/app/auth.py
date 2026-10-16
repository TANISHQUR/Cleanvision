"""
Minimal auth for the prototype.

Admins log in with a username/password from settings and receive a signed,
expiring token. The detector authenticates with a shared token header.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import Header, HTTPException, Query, status

from .settings import settings


def _sign(payload: str) -> str:
    return hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(username: str) -> str:
    exp = int(time.time()) + settings.token_ttl_hours * 3600
    payload = f"{username}|{exp}"
    body = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    return f"{body}.{_sign(payload)}"


def verify_token(token: str) -> str | None:
    try:
        body, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        username, exp = payload.rsplit("|", 1)
        if int(exp) < time.time():
            return None
        return username
    except (ValueError, UnicodeDecodeError):
        return None


def check_login(username: str, password: str) -> bool:
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
        password, settings.admin_password
    )


async def require_admin(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None, description="Alternative to the header, used by <img>/<video> tags"),
) -> str:
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:]
    elif token:
        raw = token
    user = verify_token(raw) if raw else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in again: your session is missing or expired.")
    return user


async def require_detector(x_detector_token: str | None = Header(default=None)) -> None:
    if not x_detector_token or not hmac.compare_digest(x_detector_token, settings.detector_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid detector token.")
