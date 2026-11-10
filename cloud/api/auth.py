"""Supabase Auth verification for cloud API requests.

The API asks Supabase Auth to resolve the bearer token. This supports projects
using either legacy JWT secrets or newer asymmetric signing keys without
copying signing secrets into this service.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")

    base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    if not base_url or not anon_key:
        raise HTTPException(status_code=503, detail="Authentication service is not configured")

    try:
        response = requests.get(
            f"{base_url}/auth/v1/user",
            headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {credentials.credentials}",
            },
            timeout=8,
        )
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    user = response.json()
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid authenticated user")
    return {"user": user, "access_token": credentials.credentials}


def current_user(session: dict[str, Any] = Depends(current_session)) -> dict[str, Any]:
    return session["user"]
