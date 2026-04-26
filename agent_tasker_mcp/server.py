"""Minimal stdio MCP server and parallel execution engine."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, TextIO

try:
    import resource
except ImportError:  # pragma: no cover - platform dependent
    resource = None

from .common import apply_output_mode
from .models import DEFAULT_MAX_PAYLOAD_BYTES, DEFAULT_MAX_TASKS, TaskType
from .registry import TASK_SPECS, build_payload, execute_batch_schema, execute_schema, validate_name, validate_payload
from .version import package_version

SERVER_NAME = "agent-tasker"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_VERSION = package_version()


class _LifecycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class _PreparedTask:
    id: str
    name: str
    task_type: TaskType
    payload: Dict[str, Any]
    depends_on: tuple[str, ...] = ()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _current_memory_mb() -> Optional[float]:
    if resource is None:
        return None
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def _now_iso() -> str:
    return datetime.now().isoformat()


def _jsonrpc_result(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_result(payload: Dict[str, Any], *, is_error: bool = False) -> Dict[str, Any]:
    text = json.dumps(payload, default=str, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": is_error,
    }


def _tool_payload_failed(payload: Dict[str, Any]) -> bool:
    task = payload.get("task")
    if isinstance(task, dict):
        return task.get("status") == "failed"
    failed = payload.get("failed")
    return isinstance(failed, int) and failed > 0


class AgentTasker:
    """Parallel task execution engine for AI agents."""

    def __init__(
        self,
        max_workers: int = 4,
        max_tasks: int = DEFAULT_MAX_TASKS,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        max_memory_mb: int = _env_int("AGENT_TASKER_MAX_MEMORY_MB", 0),
    ):
        if not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("'max_workers' must be a positive integer")
        self.max_workers = max_workers
        self.max_tasks = max_tasks
        self.max_payload_bytes = max_payload_bytes
        self.max_memory_mb = max_memory_mb
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _check_payload_size(self, payload: Dict[str, Any]) -> None:
        size = len(json.dumps(payload, default=str))
        if size > self.max_payload_bytes:
            raise RuntimeError(f"Payload too large ({size} bytes > {self.max_payload_bytes} bytes)")

    def _check_memory_guard(self) -> None:
        if self.max_memory_mb <= 0:
            return
        rss_mb = _current_memory_mb()
        if rss_mb is not None and rss_mb > self.max_memory_mb:
            raise RuntimeError(f"Memory guard triggered ({rss_mb:.1f}MB > {self.max_memory_mb}MB)")

    @staticmethod
    def _normalize_dependencies(depends_on: Any) -> tuple[str, ...]:
        if depends_on is None:
            return ()
        if not isinstance(depends_on, list):
            raise ValueError("'depends_on' must be an array of task names")
        normalized: List[str] = []
        for item in depends_on:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("'depends_on' must be an array of non-empty task names")
            name = item.strip()
            if name not in normalized:
                normalized.append(name)
        return tuple(normalized)

    def _prepare_task(self, name: str, task_type: TaskType, payload: Dict[str, Any], depends_on: Any = None) -> _PreparedTask:
        validated_name = validate_name(name)
        validated_payload = validate_payload(task_type, payload)
        self._check_payload_size(validated_payload)
        return _PreparedTask(
            id=uuid.uuid4().hex[:12],
            name=validated_name,
            task_type=task_type,
            payload=validated_payload,
            depends_on=self._normalize_dependencies(depends_on),
        )

    @staticmethod
    def _validate_dependency_graph(prepared: List[_PreparedTask]) -> None:
        task_names = {task.name for task in prepared}
        dependents = {task.name: [] for task in prepared}
        pending_counts = {task.name: len(task.depends_on) for task in prepared}
        for task in prepared:
            for dependency in task.depends_on:
                if dependency == task.name:
                    raise ValueError(f"Task '{task.name}' cannot depend on itself")
                if dependency not in task_names:
                    raise ValueError(f"Task '{task.name}' depends on unknown task '{dependency}'")
                dependents[dependency].append(task.name)
        ready = deque(name for name, count in pending_counts.items() if count == 0)
        visited = 0
        while ready:
            current = ready.popleft()
            visited += 1
            for child in dependents[current]:
                pending_counts[child] -= 1
                if pending_counts[child] == 0:
                    ready.append(child)
        if visited != len(prepared):
            raise ValueError("Task dependencies must be acyclic")

    def _prepare_tasks(self, task_definitions: List[tuple[str, TaskType, Dict[str, Any]]]) -> List[_PreparedTask]:
        if len(task_definitions) > self.max_tasks:
            raise RuntimeError(f"Task limit reached ({self.max_tasks})")
        self._check_memory_guard()
        prepared: List[_PreparedTask] = []
        seen_names = set()
        for definition in task_definitions:
            if len(definition) not in {3, 4}:
                raise ValueError("Each task definition must include name, task_type, payload, and optional depends_on")
            name, task_type, payload = definition[:3]
            depends_on = definition[3] if len(definition) == 4 else None
            task = self._prepare_task(name, task_type, payload, depends_on)
            if task.name in seen_names:
                raise ValueError(f"Duplicate task name: {task.name}")
            seen_names.add(task.name)
            prepared.append(task)
        last_file_task: Dict[str, str] = {}
        prepared_with_file_deps: List[_PreparedTask] = []
        for task in prepared:
            path = task.payload.get("path") if task.task_type in {TaskType.FILE_READ, TaskType.FILE_WRITE} else None
            depends_on = list(task.depends_on)
            if isinstance(path, str):
                previous = last_file_task.get(path)
                if previous is not None and previous not in depends_on:
                    depends_on.append(previous)
                last_file_task[path] = task.name
            prepared_with_file_deps.append(replace(task, depends_on=tuple(depends_on)))
        self._validate_dependency_graph(prepared_with_file_deps)
        return prepared_with_file_deps

    @staticmethod
    def _execute_task(task: _PreparedTask) -> Dict[str, Any]:
        started_at = time.time()
        started_perf = time.perf_counter()
        result: Any = None
        error: Optional[str] = None
        status = "completed"
        try:
            result = TASK_SPECS[task.task_type].executor(dict(task.payload))
        except Exception as exc:
            error, status = str(exc), "failed"
        completed_at = time.time()
        return {
            "id": task.id,
            "name": task.name,
            "task_type": task.task_type.value,
            "status": status,
            "result": result,
            "error": error,
            "started_at": datetime.fromtimestamp(started_at).isoformat(),
            "completed_at": datetime.fromtimestamp(completed_at).isoformat(),
            "duration_seconds": round(time.perf_counter() - started_perf, 3),
        }

    @staticmethod
    def _failed_task(task: _PreparedTask, error: str) -> Dict[str, Any]:
        timestamp = _now_iso()
        return {
            "id": task.id,
            "name": task.name,
            "task_type": task.task_type.value,
            "status": "failed",
            "result": None,
            "error": error,
            "started_at": timestamp,
            "completed_at": timestamp,
            "duration_seconds": None,
        }

    def execute_tasks(self, task_definitions: List[tuple[str, TaskType, Dict[str, Any]]]) -> Dict[str, Any]:
        prepared = self._prepare_tasks(task_definitions)
        if not prepared:
            return {"total": 0, "completed": 0, "failed": 0, "message": "No tasks to run", "results": []}
        ordered: List[Optional[Dict[str, Any]]] = [None] * len(prepared)
        by_name = {task.name: task for task in prepared}
        name_to_index = {task.name: index for index, task in enumerate(prepared)}
        pending_counts = {task.name: len(task.depends_on) for task in prepared}
        blocked_by = {task.name: [] for task in prepared}
        dependents = {task.name: [] for task in prepared}
        for task in prepared:
            for dependency in task.depends_on:
                dependents[dependency].append(task.name)
        futures: Dict[Any, str] = {}
        results: Dict[str, Any] = {"total": len(prepared), "completed": 0, "failed": 0, "started_at": _now_iso(), "results": []}

        def submit(task_name: str) -> None:
            future = self.executor.submit(self._execute_task, by_name[task_name])
            futures[future] = task_name

        def resolve(resolved_name: str, task_data: Dict[str, Any]) -> None:
            queue = deque([(resolved_name, task_data)])
            while queue:
                current_name, current_data = queue.popleft()
                current_index = name_to_index[current_name]
                if ordered[current_index] is not None:
                    continue
                ordered[current_index] = current_data
                if current_data.get("status") == "completed":
                    results["completed"] += 1
                else:
                    results["failed"] += 1
                for child_name in dependents[current_name]:
                    pending_counts[child_name] -= 1
                    if current_data.get("status") != "completed":
                        blocked_by[child_name].append(current_name)
                    if pending_counts[child_name] == 0:
                        if blocked_by[child_name]:
                            queue.append(
                                (
                                    child_name,
                                    self._failed_task(
                                        by_name[child_name],
                                        f"Blocked by failed dependencies: {', '.join(blocked_by[child_name])}",
                                    ),
                                )
                            )
                        else:
                            submit(child_name)

        for task in prepared:
            if pending_counts[task.name] == 0:
                submit(task.name)

        while futures:
            done, _pending = wait(list(futures), return_when=FIRST_COMPLETED)
            for future in done:
                task_name = futures.pop(future)
                try:
                    task_data = future.result()
                except Exception as exc:
                    task_data = self._failed_task(by_name[task_name], f"Internal task execution error: {exc}")
                resolve(task_name, task_data)
        results["completed_at"] = _now_iso()
        results["results"] = [item for item in ordered if item is not None]
        return results


def _task_name(name: Any, task_type: TaskType, index: int) -> str:
    if name is None or (isinstance(name, str) and not name.strip()):
        return f"{task_type.value}_{index + 1}"
    return validate_name(name)


def _task_definition(source: Dict[str, Any], index: int) -> tuple[str, TaskType, Dict[str, Any], List[str]]:
    if not isinstance(source, dict):
        raise ValueError("Each task definition must be an object")
    try:
        task_type = TaskType(source["task_type"])
    except KeyError as exc:
        raise ValueError("'task_type' is required") from exc
    except ValueError as exc:
        raise ValueError(f"Unsupported task_type: {source.get('task_type')}") from exc
    depends_on = source.get("depends_on")
    if depends_on is not None and not isinstance(depends_on, list):
        raise ValueError("'depends_on' must be an array of task names")
    return _task_name(source.get("name"), task_type, index), task_type, build_payload(task_type, source), depends_on or []


def _batch_definitions(arguments: Dict[str, Any]) -> List[tuple[str, TaskType, Dict[str, Any], List[str]]]:
    tasks = arguments.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("'tasks' must be a non-empty array")
    return [_task_definition(task, index) for index, task in enumerate(tasks)]


def _single_definition(arguments: Dict[str, Any]) -> tuple[str, TaskType, Dict[str, Any]]:
    return _task_definition(arguments, 0)


def _output_mode(arguments: Dict[str, Any], *, default: str) -> str:
    mode = arguments.get("output_mode", default)
    return mode if isinstance(mode, str) and mode in {"full", "compact"} else default


def _format_execution(raw: Dict[str, Any], *, output_mode: str) -> Dict[str, Any]:
    return {**apply_output_mode(raw, output_mode), "output_mode": output_mode}


def _format_single_execution(raw: Dict[str, Any], *, output_mode: str) -> Dict[str, Any]:
    formatted = _format_execution(raw, output_mode=output_mode)
    return {"output_mode": formatted["output_mode"], "task": formatted["results"][0] if formatted["results"] else None}


_PUBLIC_TOOL_SPECS = (
    ("execute", "Run one task and return its result.", execute_schema),
    ("execute_batch", "Run many tasks in parallel and return ordered results.", execute_batch_schema),
)


def _tool_catalog() -> List[tuple[str, str, Dict[str, Any]]]:
    return [(name, description, schema()) for name, description, schema in _PUBLIC_TOOL_SPECS]


class MCPServer:
    """Very small MCP stdio server for tools-only usage."""

    def __init__(self, max_workers: int = 4):
        self.tasker = AgentTasker(
            max_workers=max_workers,
            max_tasks=_env_int("AGENT_TASKER_MAX_TASKS", DEFAULT_MAX_TASKS),
            max_payload_bytes=_env_int("AGENT_TASKER_MAX_PAYLOAD_BYTES", DEFAULT_MAX_PAYLOAD_BYTES),
            max_memory_mb=_env_int("AGENT_TASKER_MAX_MEMORY_MB", 0),
        )
        self._initialize_sent = False
        self._ready = False
        self.handlers = {
            "execute": self._execute,
            "execute_batch": self._execute_batch,
        }

    def close(self) -> None:
        self.tasker.close()

    def _list_tools(self) -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": name,
                    "description": description,
                    "inputSchema": schema,
                }
                for name, description, schema in _tool_catalog()
            ]
        }

    def _execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = self.tasker.execute_tasks([_single_definition(arguments)])
        return _format_single_execution(raw, output_mode=_output_mode(arguments, default="compact"))

    def _execute_batch(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = self.tasker.execute_tasks(_batch_definitions(arguments))
        return _format_execution(raw, output_mode=_output_mode(arguments, default="compact"))

    def _require_ready(self) -> None:
        if not self._initialize_sent or not self._ready:
            raise _LifecycleError("Server not initialized")

    def _handle_notification(self, method: str, params: Dict[str, Any]) -> None:
        if method == "notifications/initialized" and self._initialize_sent:
            self._ready = True

    def _handle_method(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "initialize":
            if self._initialize_sent:
                raise ValueError("initialize may only be called once per session")
            requested = params.get("protocolVersion")
            if not isinstance(requested, str) or not requested:
                raise ValueError("'protocolVersion' is required and must be a string")
            self._initialize_sent = True
            self._ready = False
            protocol_version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
            return {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Use execute for one task and execute_batch for parallel work.",
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            self._require_ready()
            return self._list_tools()
        if method == "tools/call":
            self._require_ready()
            name = params.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("'name' must be a non-empty string")
            arguments = params.get("arguments")
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                raise ValueError("'arguments' must be an object")
            handler = self.handlers.get(name)
            if handler is None:
                raise ValueError(f"Unknown tool: {name}")
            try:
                payload = handler(arguments)
                return _tool_result(payload, is_error=_tool_payload_failed(payload))
            except Exception as exc:
                return _tool_result({"error": str(exc)}, is_error=True)
        raise KeyError(method)

    def handle_message(self, message: Any) -> Any:
        if isinstance(message, list):
            if not message:
                return _jsonrpc_error(None, -32600, "Invalid request")
            responses = [response for item in message for response in [self.handle_message(item)] if response is not None]
            return responses or None
        if not isinstance(message, dict):
            return _jsonrpc_error(None, -32600, "Invalid request")
        if message.get("jsonrpc") != "2.0":
            return _jsonrpc_error(message.get("id"), -32600, "Invalid request")
        method = message.get("method")
        if not isinstance(method, str):
            return _jsonrpc_error(message.get("id"), -32600, "Invalid request")
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _jsonrpc_error(message.get("id"), -32602, "Invalid params")
        if "id" not in message:
            self._handle_notification(method, params)
            return None
        request_id = message["id"]
        try:
            return _jsonrpc_result(request_id, self._handle_method(method, params))
        except KeyError:
            return _jsonrpc_error(request_id, -32601, f"Method not found: {method}")
        except _LifecycleError as exc:
            return _jsonrpc_error(request_id, -32002, str(exc))
        except ValueError as exc:
            return _jsonrpc_error(request_id, -32602, str(exc))
        except Exception as exc:
            return _jsonrpc_error(request_id, -32603, str(exc))

    def serve_stdio(self, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
        try:
            for raw_line in stdin:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    response = self.handle_message(json.loads(line))
                except json.JSONDecodeError:
                    response = _jsonrpc_error(None, -32700, "Parse error")
                if response is not None:
                    stdout.write(json.dumps(response, default=str, separators=(",", ":")) + "\n")
                    stdout.flush()
        finally:
            self.close()


def create_server(max_workers: int = 4) -> MCPServer:
    return MCPServer(max_workers=max_workers)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AgentTasker MCP Server - Parallel task execution for AI agents")
    parser.add_argument("--workers", "-w", type=int, default=4, help="Maximum number of parallel workers (default: 4)")
    args = parser.parse_args(argv)
    create_server(max_workers=args.workers).serve_stdio()
    return 0


def cli() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
