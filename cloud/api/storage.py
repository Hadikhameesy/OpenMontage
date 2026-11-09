"""Supabase PostgREST access using the caller's JWT so database RLS applies."""
from __future__ import annotations

import os
from typing import Any

import requests
from fastapi import HTTPException


def _request(method: str, table: str, access_token: str, *, params=None, body=None):
    base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    if not base_url or not anon_key:
        raise HTTPException(status_code=503, detail="Database service is not configured")
    try:
        response = requests.request(
            method,
            f"{base_url}/rest/v1/{table}",
            headers={
                "apikey": anon_key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            params=params,
            json=body,
            timeout=12,
        )
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Database service unavailable")
    if response.status_code >= 400:
        # Do not leak Postgres details, schema names, or policy expressions.
        if response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail="Not authorized for this resource")
        raise HTTPException(status_code=502, detail="Database request failed")
    if not response.content:
        return []
    try:
        value = response.json()
    except ValueError:
        return []
    return value if isinstance(value, list) else [value]


def list_rows(table: str, token: str, *, params: dict[str, str]):
    return _request("GET", table, token, params=params)


def insert_row(table: str, token: str, values: dict[str, Any]):
    rows = _request("POST", table, token, body=values)
    if not rows:
        raise HTTPException(status_code=502, detail="Database did not return the created record")
    return rows[0]


def update_rows(table: str, token: str, *, params: dict[str, str], values: dict[str, Any]):
    return _request("PATCH", table, token, params=params, body=values)


def call_rpc(name: str, token: str, values: dict[str, Any]):
    """Call a narrowly-scoped Postgres RPC with the caller JWT and RLS identity."""
    if not name.replace("_", "").isalnum():
        raise ValueError("Invalid RPC name")
    return _request("POST", f"rpc/{name}", token, body=values)
