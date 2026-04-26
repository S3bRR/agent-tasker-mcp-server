"""Basic local task executors."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from ..common import PYTHON_EXECUTION_RUNNER


def _preview_output(value: str, limit: int = 500) -> str:
    stripped = value.strip()
    return stripped[:limit] + "..." if len(stripped) > limit else stripped


def execute_python_code(payload: Dict[str, Any]) -> Any:
    """Execute Python code string and return the result variable."""
    code = payload["code"]
    timeout = payload.get("timeout") or 30
    try:
        completed = subprocess.run(
            [sys.executable, "-c", PYTHON_EXECUTION_RUNNER],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Python code execution timed out after {timeout}s")
    except Exception as exc:
        raise RuntimeError(f"Code execution failed: {exc}")

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "Unknown error"
        raise RuntimeError(f"Code execution failed: {stderr}")

    try:
        result = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Code execution returned invalid JSON: {exc}")
    return result.get("result")


def execute_shell_command(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a shell command and capture output."""
    command = payload["command"]
    timeout = payload.get("timeout") or 60
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Command timed out after {timeout}s")
    except Exception as exc:
        raise RuntimeError(f"Command execution failed: {exc}")
    if result.returncode != 0:
        detail = _preview_output(result.stderr) or _preview_output(result.stdout) or "No output"
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {command}\n{detail}")
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "return_code": result.returncode,
        "command": command,
    }


def execute_file_read(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Read a file from disk."""
    path = payload["path"]
    try:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return {
            "path": str(file_path.absolute()),
            "content": content,
            "size_bytes": file_path.stat().st_size,
            "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
        }
    except Exception as exc:
        raise RuntimeError(f"File read failed: {exc}")


def execute_file_write(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Write content to a file."""
    path = payload["path"]
    content = payload["content"]
    mode = payload.get("mode", "w")
    try:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "a":
            with open(file_path, "a", encoding="utf-8") as handle:
                handle.write(content)
        else:
            file_path.write_text(content, encoding="utf-8")
        return {
            "path": str(file_path.absolute()),
            "size_bytes": file_path.stat().st_size,
            "mode": mode,
        }
    except Exception as exc:
        raise RuntimeError(f"File write failed: {exc}")
