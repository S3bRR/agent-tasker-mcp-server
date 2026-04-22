"""HTTP and scraping executors."""

from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from ..common import HTMLContentExtractor, fallback_html_extract
from ..models import DEFAULT_MAX_BODY_BYTES, RETRYABLE_HTTP_STATUSES


def default_retries(method: str, retries: Optional[int]) -> int:
    if retries is not None:
        return retries
    return 2 if method.upper() in {"GET", "HEAD", "OPTIONS"} else 0


def request_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged = {"User-Agent": "agent-tasker-mcp-server/2.7.0"}
    if headers:
        merged.update(headers)
    return merged


def decode_json_response(response: Dict[str, Any], context: str) -> Dict[str, Any]:
    body = response.get("body") or ""
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{context} returned invalid JSON: {exc}")


def _read_limited_body(stream: Any, max_body_bytes: int) -> tuple[bytes, bool]:
    body = stream.read(max_body_bytes + 1)
    if len(body) <= max_body_bytes:
        return body, False
    return body[:max_body_bytes], True


def _decode_body(body_bytes: bytes, headers: Any) -> str:
    charset = None
    if headers is not None and hasattr(headers, "get_content_charset"):
        charset = headers.get_content_charset()
    if not charset:
        charset = "utf-8"
    return body_bytes.decode(charset, errors="replace")


def _retryable_network_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, (TimeoutError, socket.timeout)) or isinstance(exc.reason, OSError)
    return False


def execute_http_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an HTTP request with optional retry/backoff."""
    url = payload["url"]
    method = payload.get("method", "GET").upper()
    headers = request_headers(payload.get("headers"))
    body = payload.get("body")
    timeout = payload.get("timeout") or 30
    verify_ssl = payload.get("verify_ssl", True)
    max_body_bytes = payload.get("max_body_bytes", DEFAULT_MAX_BODY_BYTES)
    retries = default_retries(method, payload.get("retries"))
    retry_backoff_seconds = payload.get("retry_backoff_seconds", 1)

    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ssl_context = None
    if not verify_ssl:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    last_error: Optional[str] = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
                body_bytes, body_truncated = _read_limited_body(response, max_body_bytes)
                return {
                    "status_code": response.status,
                    "headers": dict(response.headers),
                    "body": _decode_body(body_bytes, response.headers),
                    "body_bytes": len(body_bytes),
                    "body_truncated": body_truncated,
                    "url": response.url,
                    "attempts": attempt + 1,
                }
        except urllib.error.HTTPError as exc:
            try:
                body_bytes, body_truncated = _read_limited_body(exc, max_body_bytes)
                if exc.code in RETRYABLE_HTTP_STATUSES and attempt < retries:
                    time.sleep(retry_backoff_seconds * (2**attempt))
                    continue
                return {
                    "status_code": exc.code,
                    "headers": dict(exc.headers) if exc.headers else {},
                    "body": _decode_body(body_bytes, exc.headers),
                    "body_bytes": len(body_bytes),
                    "body_truncated": body_truncated,
                    "error": str(exc),
                    "url": url,
                    "attempts": attempt + 1,
                }
            finally:
                exc.close()
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_error = str(exc)
            if attempt < retries and _retryable_network_error(exc):
                time.sleep(retry_backoff_seconds * (2**attempt))
                continue
            raise RuntimeError(f"HTTP request failed after {attempt + 1} attempt(s): {last_error}")

    raise RuntimeError(f"HTTP request failed: {last_error or 'unknown error'}")


def execute_web_scrape(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch a webpage and extract lightweight visible content."""
    response = execute_http_request(
        {
            "url": payload["url"],
            "method": "GET",
            "timeout": payload.get("timeout") or 30,
            "verify_ssl": payload.get("verify_ssl", True),
            "max_body_bytes": payload.get("max_body_bytes", DEFAULT_MAX_BODY_BYTES),
            "retries": payload.get("retries"),
            "retry_backoff_seconds": payload.get("retry_backoff_seconds", 1),
            "headers": {
                "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
            },
        }
    )

    body = response.get("body", "")
    content_type = response.get("headers", {}).get("Content-Type") or response.get("headers", {}).get("content-type") or ""
    parser = HTMLContentExtractor(
        response.get("url", payload["url"]),
        max_links=payload.get("max_links", 50),
        link_include_pattern=payload.get("link_include_pattern"),
    )
    parser.feed(body)
    parser.close()
    extracted = parser.extract(max_text_chars=payload.get("max_text_chars", 20000))
    fallback = fallback_html_extract(
        response.get("url", payload["url"]),
        body,
        max_links=payload.get("max_links", 50),
        link_include_pattern=payload.get("link_include_pattern"),
    )
    extracted["title"] = fallback["title"] or extracted["title"]
    if not extracted["text"]:
        extracted["text"] = fallback["text"][: payload.get("max_text_chars", 20000)].rstrip()
        extracted["text_truncated"] = len(fallback["text"]) > payload.get("max_text_chars", 20000)
    if not extracted["links"]:
        extracted["links"] = fallback["links"]
    links = extracted["links"] if payload.get("extract_links", True) else []
    headings = extracted["headings"] if payload.get("extract_headings", True) else []

    result: Dict[str, Any] = {
        "url": payload["url"],
        "final_url": response.get("url", payload["url"]),
        "status_code": response.get("status_code"),
        "content_type": content_type,
        "body_truncated": response.get("body_truncated", False),
        "title": extracted["title"],
        "meta_description": extracted["meta_description"],
        "text": extracted["text"],
        "text_truncated": extracted["text_truncated"],
        "headings": headings,
        "links": links,
        "link_count": len(links),
    }
    if extracted.get("js_rendered_warning"):
        result["js_rendered_warning"] = extracted["js_rendered_warning"]
    if payload.get("include_html", False):
        max_text_chars = payload.get("max_text_chars", 20000)
        result["html"] = body[:max_text_chars]
        result["html_truncated"] = len(body) > max_text_chars
    return result
