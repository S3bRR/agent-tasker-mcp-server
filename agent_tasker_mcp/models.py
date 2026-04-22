"""Core models and constants for AgentTasker MCP."""

from __future__ import annotations

from enum import Enum


class TaskType(Enum):
    PYTHON_CODE = "python_code"
    HTTP_REQUEST = "http_request"
    DISCOVERY_SEARCH = "discovery_search"
    WEB_SCRAPE = "web_scrape"
    SHELL_COMMAND = "shell_command"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"


ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
RETRYABLE_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}

DEFAULT_MAX_TASKS = 1000
DEFAULT_MAX_PAYLOAD_BYTES = 1_000_000
DEFAULT_MAX_BODY_BYTES = 2_000_000
