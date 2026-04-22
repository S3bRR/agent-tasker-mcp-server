"""Generic discovery executors."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlencode

from ..common import extract_domain, get_nested_value, normalize_text, tokenize_text
from ..models import DEFAULT_MAX_BODY_BYTES
from .http import decode_json_response, execute_http_request, execute_web_scrape

_EMPTY_VALUES = (None, "", [], 0)

def _max_results(payload: Dict[str, Any]) -> int:
    return payload.get("max_results", 10)

def _request_kwargs(payload: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    return {
        "timeout": payload.get("timeout", 30),
        "verify_ssl": payload.get("verify_ssl", True),
        "max_body_bytes": payload.get("max_body_bytes", DEFAULT_MAX_BODY_BYTES),
        "retries": payload.get("retries"),
        "retry_backoff_seconds": payload.get("retry_backoff_seconds", 1),
        **extra,
    }

def _fetch_json(
    payload: Dict[str, Any],
    context: str,
    *,
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
) -> Dict[str, Any]:
    response = execute_http_request(_request_kwargs(payload, url=url, method=method, headers=headers, body=body))
    return decode_json_response(response, context)

def _ordered_parallel(items: Sequence[Any], worker: Callable[[Any], Any], max_workers: int) -> List[Any]:
    ordered: List[Any] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max(1, min(len(items), max_workers))) as executor:
        future_map = {executor.submit(worker, item): index for index, item in enumerate(items)}
        for future in as_completed(future_map):
            ordered[future_map[future]] = future.result()
    return ordered

def _unique_extend(target: Dict[str, Any], key: str, values: Iterable[Any]) -> None:
    existing = target.setdefault(key, [])
    for value in values:
        if value and value not in existing:
            existing.append(value)

def _status(name: str, *, label: str, count: int = 0, error: Optional[Exception] = None) -> Dict[str, Any]:
    if error is None:
        return {label: name, "status": "ok", "candidates": count}
    return {label: name, "status": "failed", "error": str(error)}

def _fetch_candidates(name: str, fetcher: Callable[[], List[Dict[str, Any]]], *, label: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    try:
        results = fetcher()
        return _status(name, label=label, count=len(results)), results
    except Exception as exc:
        return _status(name, label=label, error=exc), []

def _collect_candidates(
    items: Sequence[Any],
    worker: Callable[[Any], tuple[Dict[str, Any], List[Dict[str, Any]]]],
    *,
    max_workers: int,
    error_key: str,
    failure_prefix: str,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ordered = _ordered_parallel(items, worker, max_workers)
    statuses = [status for status, _results in ordered]
    candidates = [candidate for _status, results in ordered for candidate in results]
    if candidates or not statuses or any(status["status"] == "ok" for status in statuses):
        return statuses, candidates
    failures = "; ".join(f"{status[error_key]}: {status['error']}" for status in statuses)
    raise RuntimeError(f"{failure_prefix}: {failures}")

def _merge_candidates(
    candidates: List[Dict[str, Any]],
    keys_for: Callable[[Dict[str, Any]], Iterable[Optional[str]]],
    *,
    finalize: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    key_to_index: Dict[str, int] = {}
    for candidate in candidates:
        keys = [key for key in keys_for(candidate) if key]
        if not keys:
            continue
        index = next((key_to_index[key] for key in keys if key in key_to_index), None)
        current = dict(candidate) if index is None else merged[index]
        if index is None:
            merged.append(current)
            index = len(merged) - 1
        else:
            for field, value in candidate.items():
                if field in {"source_records", "source_ids"}:
                    _unique_extend(current, field, value or [])
                elif current.get(field) in _EMPTY_VALUES and value not in _EMPTY_VALUES:
                    current[field] = value
            if finalize:
                finalize(current)
        for key in keys:
            key_to_index[key] = index
    return merged

def _match_score(query: str, title: str, body: str = "", *, exact: int, contains: int, title_weight: int, body_weight: int) -> float:
    normalized_query = normalize_text(query)
    normalized_title = normalize_text(title)
    query_tokens = set(tokenize_text(query))
    score = float(normalized_title == normalized_query) * exact
    if not score and normalized_query and normalized_query in normalized_title:
        score += contains
    if query_tokens:
        score += title_weight * (len(query_tokens & set(tokenize_text(title))) / len(query_tokens))
        score += body_weight * (len(query_tokens & set(tokenize_text(body))) / len(query_tokens))
    return score

def render_provider_template(template: str, query: str, limit: int) -> str:
    return template.format(query=query, query_encoded=urlencode({"q": query})[2:], limit=limit)

def _discovery_candidate(item: Dict[str, Any], provider: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = get_nested_value(item, provider["title_path"])
    url = get_nested_value(item, provider["url_path"])
    if not isinstance(title, str) or not title.strip() or not isinstance(url, str) or not url.strip():
        return None
    snippet = get_nested_value(item, provider.get("snippet_path", ""))
    return {
        "title": title.strip(),
        "url": url.strip(),
        "snippet": snippet.strip() if isinstance(snippet, str) else None,
        "domain": extract_domain(url),
        "source_records": [provider["name"]],
        "source_ids": [provider["name"]],
    }

def _score_discovery_candidate(candidate: Dict[str, Any], query: str) -> float:
    score = _match_score(query, candidate.get("title") or "", candidate.get("snippet") or "", exact=150, contains=70, title_weight=70, body_weight=25)
    return round(score + len(candidate.get("source_records", [])) * 3, 3)

def _discovery_context(candidate: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        page = execute_web_scrape(
            {
                **_request_kwargs(payload, url=candidate["url"]),
                "method": "GET",
                "max_links": 0,
                "max_text_chars": payload.get("fetch_max_chars", 4000),
                "include_html": False,
                "extract_links": False,
                "extract_headings": False,
            }
        )
        return {
            "page_context": {
                "title": page.get("title"),
                "meta_description": page.get("meta_description"),
                "text": page.get("text"),
                "final_url": page.get("final_url"),
                "status_code": page.get("status_code"),
            }
        }
    except Exception as exc:
        return {"page_context_error": str(exc)}

def fetch_discovery_context(candidates: List[Dict[str, Any]], payload: Dict[str, Any]) -> None:
    selected = candidates[: payload.get("fetch_top_results", 0)]
    if not selected:
        return
    for candidate, update in zip(selected, _ordered_parallel(selected, lambda item: _discovery_context(item, payload), 8)):
        candidate.update(update)

def _fetch_discovery_provider(provider: Dict[str, Any], payload: Dict[str, Any]) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    name = provider.get("name", "unknown")
    limit = _max_results(payload)

    def fetch() -> List[Dict[str, Any]]:
        body_template = provider.get("body_template")
        data = _fetch_json(
            payload,
            name,
            url=render_provider_template(provider["url_template"], payload["query"], limit),
            method=provider.get("method", "GET").upper(),
            headers=provider.get("headers"),
            body=render_provider_template(body_template, payload["query"], limit) if isinstance(body_template, str) else None,
        )
        items = get_nested_value(data, provider["items_path"])
        if not isinstance(items, list):
            raise RuntimeError(f"{name} items_path did not resolve to a list")
        return [
            candidate
            for item in items[: provider.get("result_limit", limit)]
            if isinstance(item, dict)
            for candidate in [_discovery_candidate(item, provider)]
            if candidate
        ]

    return _fetch_candidates(name, fetch, label="provider")

def execute_discovery_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    providers = payload["providers"]
    provider_statuses, candidates = _collect_candidates(
        providers,
        lambda provider: _fetch_discovery_provider(provider, payload),
        max_workers=8,
        error_key="provider",
        failure_prefix="discovery_search failed across all providers",
    )
    merged = _merge_candidates(candidates, lambda candidate: [candidate.get("url") or normalize_text(candidate.get("title"))])
    for candidate in merged:
        candidate["score"] = _score_discovery_candidate(candidate, payload["query"])
    results = sorted(merged, key=lambda item: item.get("score", 0), reverse=True)[: _max_results(payload)]
    fetch_discovery_context(results, payload)
    return {
        "query": payload["query"],
        "provider_count": len(providers),
        "candidate_count": len(candidates),
        "deduped_count": len(merged),
        "returned_count": len(results),
        "fetch_top_results": payload.get("fetch_top_results", 0),
        "provider_statuses": provider_statuses,
        "results": results,
    }
