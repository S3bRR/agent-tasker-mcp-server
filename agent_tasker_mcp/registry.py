"""Single manifest for task metadata, schemas, payload building, and validation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List

from .executors.basic import execute_file_read, execute_file_write, execute_python_code, execute_shell_command
from .executors.discovery import execute_discovery_search
from .executors.http import execute_http_request, execute_web_scrape
from .models import ALLOWED_HTTP_METHODS, TaskType

_MISSING = object()


@dataclass(frozen=True)
class TaskSpec:
    fields: tuple[str, ...]
    executor: Callable[[Dict[str, Any]], Any]
    validator: Callable[[Dict[str, Any]], Dict[str, Any]]


def _field(schema: Dict[str, Any], *, default: Any = _MISSING, include_if_none: bool = False) -> Dict[str, Any]:
    spec = {"schema": schema}
    if default is not _MISSING:
        spec["default"] = default
    if include_if_none:
        spec["include_if_none"] = True
    return spec


FIELD_SPECS: Dict[str, Dict[str, Any]] = {
    "code": _field({"type": "string", "description": "Python code"}),
    "url": _field({"type": "string", "description": "Target URL"}),
    "method": _field({"type": "string", "enum": sorted(ALLOWED_HTTP_METHODS), "description": "HTTP method"}, default="GET"),
    "headers": _field({"type": "object", "description": "Headers"}),
    "body": _field({"type": "string", "description": "Request body"}),
    "query": _field({"type": "string", "description": "Search query"}),
    "providers": _field({"type": "array", "items": {"type": "object"}, "description": "Discovery providers"}, include_if_none=True),
    "fetch_top_results": _field({"type": "integer", "description": "Fetch top result pages"}, default=0),
    "fetch_max_chars": _field({"type": "integer", "description": "Chars per fetched page"}, default=4000),
    "max_results": _field({"type": "integer", "description": "Max results"}, default=10),
    "retries": _field({"type": "integer", "description": "Retry count"}, include_if_none=True),
    "retry_backoff_seconds": _field({"type": "integer", "description": "Retry backoff seconds"}, default=1),
    "verify_ssl": _field({"type": "boolean", "description": "Verify SSL"}, default=True),
    "max_body_bytes": _field({"type": "integer", "description": "Max response bytes"}, default=2_000_000),
    "max_links": _field({"type": "integer", "description": "Max links"}, default=50),
    "max_text_chars": _field({"type": "integer", "description": "Max extracted chars"}, default=20000),
    "include_html": _field({"type": "boolean", "description": "Include raw HTML"}, default=False),
    "extract_links": _field({"type": "boolean", "description": "Include links"}, default=True),
    "extract_headings": _field({"type": "boolean", "description": "Include headings"}, default=True),
    "link_include_pattern": _field({"type": "string", "description": "Regex for kept links"}, include_if_none=True),
    "command": _field({"type": "string", "description": "Command"}),
    "path": _field({"type": "string", "description": "File path"}),
    "content": _field({"type": "string", "description": "File content"}),
    "mode": _field({"type": "string", "enum": ["w", "a"], "description": "w or a"}, default="w"),
    "timeout": _field({"type": "integer", "description": "Timeout seconds"}, include_if_none=True),
}


_is_positive_int = lambda value: isinstance(value, int) and not isinstance(value, bool) and value > 0
_is_non_negative_int = lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= 0
_is_string_list = lambda value: isinstance(value, list) and all(isinstance(item, str) for item in value)
_is_string_dict = lambda value: isinstance(value, dict) and all(isinstance(key, str) and isinstance(val, str) for key, val in value.items())
_is_object_list = lambda value: isinstance(value, list) and all(isinstance(item, dict) for item in value)


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("'name' must be a non-empty string")
    return name.strip()


def _require_string(payload: Dict[str, Any], key: str, task_type: TaskType) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' is required for {task_type.value} tasks")
    return value


def _check(payload: Dict[str, Any], key: str, predicate: Callable[[Any], bool], message: str) -> None:
    value = payload.get(key)
    if value is not None and not predicate(value):
        raise ValueError(message)


def _check_keys(payload: Dict[str, Any], keys: Iterable[str], predicate: Callable[[Any], bool], message: str) -> None:
    for key in keys:
        _check(payload, key, predicate, message.format(key=key))


def _normalize(
    payload: Dict[str, Any],
    task_type: TaskType,
    *,
    required: Iterable[str] = (),
    timeout: bool = False,
    positive_ints: Iterable[str] = (),
    non_negative_ints: Iterable[str] = (),
    booleans: Iterable[str] = (),
    strings: Iterable[str] = (),
    string_lists: Iterable[str] = (),
    string_dicts: Iterable[str] = (),
    objects: Iterable[str] = (),
    object_lists: Iterable[str] = (),
) -> Dict[str, Any]:
    normalized = dict(payload)
    if timeout:
        timeout_value = normalized.get("timeout")
        if timeout_value is not None and not _is_positive_int(timeout_value):
            raise ValueError(f"'timeout' must be a positive integer for {task_type.value} tasks")
    for key in required:
        _require_string(normalized, key, task_type)
    _check_keys(normalized, positive_ints, _is_positive_int, "'{key}' must be a positive integer")
    _check_keys(normalized, non_negative_ints, _is_non_negative_int, "'{key}' must be a non-negative integer")
    _check_keys(normalized, booleans, lambda value: isinstance(value, bool), "'{key}' must be a boolean")
    _check_keys(normalized, strings, lambda value: isinstance(value, str), "'{key}' must be a string")
    _check_keys(normalized, string_lists, _is_string_list, "'{key}' must be an array of strings")
    _check_keys(normalized, string_dicts, _is_string_dict, "'{key}' must be an object with string keys and string values")
    _check_keys(normalized, objects, lambda value: isinstance(value, dict), "'{key}' must be an object")
    _check_keys(normalized, object_lists, _is_object_list, "'{key}' must be an array of objects")
    return normalized


def _validate_python_code(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _normalize(payload, TaskType.PYTHON_CODE, required=("code",), timeout=True)


def _validate_http_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(
        payload,
        TaskType.HTTP_REQUEST,
        required=("url",),
        timeout=True,
        positive_ints=("max_body_bytes", "retry_backoff_seconds"),
        non_negative_ints=("retries",),
        booleans=("verify_ssl",),
    )
    method = normalized.get("method", "GET")
    if not isinstance(method, str) or method.upper() not in ALLOWED_HTTP_METHODS:
        raise ValueError(f"'method' must be one of: {', '.join(sorted(ALLOWED_HTTP_METHODS))}")
    normalized["method"] = method.upper()
    _check(normalized, "headers", _is_string_dict, "'headers' must be an object of string header names to string values")
    _check(normalized, "body", lambda value: isinstance(value, str), "'body' must be a string when provided")
    return normalized


def _validate_discovery_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(
        payload,
        TaskType.DISCOVERY_SEARCH,
        required=("query",),
        timeout=True,
        positive_ints=("max_results", "fetch_max_chars", "max_body_bytes", "retry_backoff_seconds"),
        non_negative_ints=("fetch_top_results", "retries"),
        object_lists=("providers",),
    )
    providers = normalized.get("providers")
    if not providers:
        raise ValueError("'providers' is required for discovery_search tasks")
    for provider in providers:
        if not isinstance(provider.get("name"), str) or not provider["name"].strip():
            raise ValueError("Each discovery_search provider requires a non-empty 'name'")
        if not isinstance(provider.get("url_template"), str) or not provider["url_template"].strip():
            raise ValueError("Each discovery_search provider requires a non-empty 'url_template'")
        if not isinstance(provider.get("items_path"), str):
            raise ValueError("Each discovery_search provider requires an 'items_path' string")
        if not isinstance(provider.get("title_path"), str) or not provider["title_path"].strip():
            raise ValueError("Each discovery_search provider requires a non-empty 'title_path'")
        if not isinstance(provider.get("url_path"), str) or not provider["url_path"].strip():
            raise ValueError("Each discovery_search provider requires a non-empty 'url_path'")
        method = provider.get("method", "GET")
        if not isinstance(method, str) or method.upper() not in ALLOWED_HTTP_METHODS:
            raise ValueError(f"Each discovery_search provider 'method' must be one of: {', '.join(sorted(ALLOWED_HTTP_METHODS))}")
        _check(provider, "headers", _is_string_dict, "Each discovery_search provider 'headers' must be an object of strings")
    return normalized


def _validate_web_scrape(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(
        payload,
        TaskType.WEB_SCRAPE,
        required=("url",),
        timeout=True,
        positive_ints=("max_links", "max_text_chars", "max_body_bytes", "retry_backoff_seconds"),
        non_negative_ints=("retries",),
        booleans=("verify_ssl", "include_html", "extract_links", "extract_headings"),
        strings=("link_include_pattern",),
    )
    link_pattern = normalized.get("link_include_pattern")
    if link_pattern is not None:
        import re

        try:
            re.compile(link_pattern)
        except re.error as exc:
            raise ValueError(f"'link_include_pattern' is not a valid regex: {exc}")
    return normalized


def _validate_shell_command(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _normalize(payload, TaskType.SHELL_COMMAND, required=("command",), timeout=True)


def _validate_file_read(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _normalize(payload, TaskType.FILE_READ, required=("path",))


def _validate_file_write(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize(payload, TaskType.FILE_WRITE, required=("path",))
    _check(normalized, "content", lambda value: isinstance(value, str), "'content' is required for file_write tasks and must be a string")
    if normalized.get("content") is None:
        raise ValueError("'content' is required for file_write tasks and must be a string")
    if normalized.get("mode", "w") not in {"w", "a"}:
        raise ValueError("'mode' must be either 'w' or 'a'")
    return normalized


TASK_SPECS: Dict[TaskType, TaskSpec] = {
    TaskType.PYTHON_CODE: TaskSpec(("code", "timeout"), execute_python_code, _validate_python_code),
    TaskType.HTTP_REQUEST: TaskSpec(("url", "method", "headers", "body", "timeout", "verify_ssl", "max_body_bytes", "retries", "retry_backoff_seconds"), execute_http_request, _validate_http_request),
    TaskType.DISCOVERY_SEARCH: TaskSpec(("query", "providers", "max_results", "fetch_top_results", "fetch_max_chars", "timeout", "verify_ssl", "max_body_bytes", "retries", "retry_backoff_seconds"), execute_discovery_search, _validate_discovery_search),
    TaskType.WEB_SCRAPE: TaskSpec(("url", "timeout", "verify_ssl", "max_body_bytes", "max_links", "max_text_chars", "include_html", "extract_links", "extract_headings", "link_include_pattern", "retries", "retry_backoff_seconds"), execute_web_scrape, _validate_web_scrape),
    TaskType.SHELL_COMMAND: TaskSpec(("command", "timeout"), execute_shell_command, _validate_shell_command),
    TaskType.FILE_READ: TaskSpec(("path",), execute_file_read, _validate_file_read),
    TaskType.FILE_WRITE: TaskSpec(("path", "content", "mode"), execute_file_write, _validate_file_write),
}

TASK_TYPE_ENUM_VALUES = [task_type.value for task_type in TaskType]


def build_payload(task_type: TaskType, source: Dict[str, Any]) -> Dict[str, Any]:
    return {
        field_name: source.get(field_name) if field_name in source else deepcopy(spec["default"]) if "default" in spec else None
        for field_name in TASK_SPECS[task_type].fields
        for spec in [FIELD_SPECS[field_name]]
        if field_name in source or "default" in spec or spec.get("include_if_none")
    }


def validate_payload(task_type: TaskType, payload: Dict[str, Any]) -> Dict[str, Any]:
    return TASK_SPECS[task_type].validator(payload)


def shared_task_properties() -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "name": {"type": "string", "description": "Task name"},
        "task_type": {"type": "string", "enum": TASK_TYPE_ENUM_VALUES, "description": "Task type"},
    }
    for spec in TASK_SPECS.values():
        for field_name in spec.fields:
            properties.setdefault(field_name, FIELD_SPECS[field_name]["schema"])
    return properties


def task_definition_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            **shared_task_properties(),
            "depends_on": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Task names that must complete before this task runs",
            },
        },
        "required": ["task_type"],
    }


def execute_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            **shared_task_properties(),
            "output_mode": {"type": "string", "enum": ["full", "compact"], "description": "full or compact", "default": "compact"},
        },
        "required": ["task_type"],
    }


def execute_batch_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "tasks": {"type": "array", "description": "Task definitions", "items": task_definition_schema()},
            "output_mode": {"type": "string", "enum": ["full", "compact"], "description": "full or compact", "default": "compact"},
        },
        "required": ["tasks"],
    }
