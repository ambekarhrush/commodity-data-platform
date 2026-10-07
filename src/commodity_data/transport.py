"""Bounded retry policy. Never expose credential-bearing request URLs in errors."""

import time
from typing import Any

import httpx


def get(session: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
    for attempt in range(4):
        response = session.get(url, **kwargs)
        if response.status_code == 200:
            return response
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == 3:
            raise ValueError(f"Provider HTTP status {response.status_code}")
        retry = response.headers.get("Retry-After", "")
        delay = min(float(retry), 30) if retry.isdigit() else 2**attempt
        time.sleep(delay)
    raise RuntimeError("Unreachable retry state")
