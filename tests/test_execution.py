from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent_tasker_mcp.executors.http import request_headers
from agent_tasker_mcp.models import TaskType
from agent_tasker_mcp.server import AgentTasker
from agent_tasker_mcp.version import package_version


class _Handler(BaseHTTPRequestHandler):
    retry_count = 0

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/json":
            self._json({"ok": True, "path": parsed.path})
            return
        if parsed.path == "/retry":
            type(self).retry_count += 1
            if type(self).retry_count < 3:
                self._json({"ok": False, "attempt": type(self).retry_count}, status=500)
                return
            self._json({"ok": True, "attempt": type(self).retry_count})
            return
        if parsed.path == "/large":
            body = "x" * 64
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if parsed.path == "/search":
            query = parse_qs(parsed.query)
            q = query.get("q", [""])[0]
            self._json({"items": [{"title": f"Result for {q}", "url": f"http://{self.headers['Host']}/page", "snippet": "Local result"}]})
            return
        if parsed.path == "/malformed":
            encoded = b"<html><head><title>Broken<title></head><body><a href='/target'>Open link"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        encoded = b"<html><head><title>Local Page</title><meta name='description' content='Local page'></head><body><h1>Hello</h1><p>Local body text.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.thread.join(timeout=5)
        cls.httpd.server_close()

    def setUp(self) -> None:
        _Handler.retry_count = 0

    def test_execute_batch_preserves_input_order(self) -> None:
        tasker = AgentTasker(max_workers=2)
        result = tasker.execute_tasks(
            [
                ("slow", TaskType.PYTHON_CODE, {"code": "time.sleep(0.2)\nresult = 'slow'"}),
                ("fast", TaskType.PYTHON_CODE, {"code": "result = 'fast'"}),
            ]
        )
        self.assertEqual([task["name"] for task in result["results"]], ["slow", "fast"])

    def test_http_request_retry_succeeds(self) -> None:
        root = f"http://127.0.0.1:{self.port}"
        tasker = AgentTasker(max_workers=1)
        result = tasker.execute_tasks([("retry", TaskType.HTTP_REQUEST, {"url": f"{root}/retry", "method": "GET", "timeout": 5})])
        task = result["results"][0]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"]["status_code"], 200)
        self.assertEqual(task["result"]["attempts"], 3)

    def test_default_http_user_agent_uses_package_version(self) -> None:
        self.assertEqual(request_headers(None)["User-Agent"], f"agent-tasker-mcp-server/{package_version()}")

    def test_http_request_body_limit_truncates(self) -> None:
        root = f"http://127.0.0.1:{self.port}"
        tasker = AgentTasker(max_workers=1)
        result = tasker.execute_tasks([("large", TaskType.HTTP_REQUEST, {"url": f"{root}/large", "max_body_bytes": 10, "timeout": 5})])
        body = result["results"][0]["result"]["body"]
        self.assertEqual(len(body), 10)
        self.assertTrue(result["results"][0]["result"]["body_truncated"])

    def test_compact_output_for_http_request(self) -> None:
        root = f"http://127.0.0.1:{self.port}"
        tasker = AgentTasker(max_workers=1)
        raw = tasker.execute_tasks([("http", TaskType.HTTP_REQUEST, {"url": f"{root}/json", "timeout": 5})])
        compact = raw["results"][0]
        from agent_tasker_mcp.common import apply_output_mode

        formatted = apply_output_mode(raw, "compact")["results"][0]["result"]
        self.assertIn("body_preview", formatted)
        self.assertNotIn("body", formatted)
        self.assertEqual(compact["result"]["status_code"], 200)

    def test_full_output_for_http_request_keeps_body(self) -> None:
        root = f"http://127.0.0.1:{self.port}"
        tasker = AgentTasker(max_workers=1)
        raw = tasker.execute_tasks([("http", TaskType.HTTP_REQUEST, {"url": f"{root}/json", "timeout": 5})])
        from agent_tasker_mcp.common import apply_output_mode

        formatted = apply_output_mode(raw, "full")["results"][0]["result"]
        self.assertIn("body", formatted)

    def test_discovery_search_mixed_provider_statuses(self) -> None:
        root = f"http://127.0.0.1:{self.port}"
        tasker = AgentTasker(max_workers=1)
        providers = [
            {
                "name": "good",
                "url_template": f"{root}/search?q={{query_encoded}}&limit={{limit}}",
                "items_path": "items",
                "title_path": "title",
                "url_path": "url",
                "snippet_path": "snippet",
            },
            {
                "name": "bad",
                "url_template": f"{root}/json",
                "items_path": "missing.items",
                "title_path": "title",
                "url_path": "url",
            },
        ]
        result = tasker.execute_tasks([("discover", TaskType.DISCOVERY_SEARCH, {"query": "agent tasker", "providers": providers, "max_results": 5, "timeout": 5})])
        statuses = {status["provider"]: status["status"] for status in result["results"][0]["result"]["provider_statuses"]}
        self.assertEqual(statuses["good"], "ok")
        self.assertEqual(statuses["bad"], "failed")
        self.assertEqual(result["results"][0]["result"]["returned_count"], 1)

    def test_discovery_search_all_fail_marks_task_failed(self) -> None:
        root = f"http://127.0.0.1:{self.port}"
        tasker = AgentTasker(max_workers=1)
        providers = [
            {
                "name": "bad1",
                "url_template": f"{root}/json",
                "items_path": "missing.items",
                "title_path": "title",
                "url_path": "url",
            },
            {
                "name": "bad2",
                "url_template": f"{root}/json",
                "items_path": "missing.items",
                "title_path": "title",
                "url_path": "url",
            },
        ]
        result = tasker.execute_tasks([("discover", TaskType.DISCOVERY_SEARCH, {"query": "agent tasker", "providers": providers, "timeout": 5})])
        self.assertEqual(result["results"][0]["status"], "failed")
        self.assertIn("failed across all providers", result["results"][0]["error"])

    def test_task_limit_raises(self) -> None:
        tasker = AgentTasker(max_workers=1, max_tasks=1)
        with self.assertRaises(RuntimeError):
            tasker.execute_tasks(
                [
                    ("one", TaskType.PYTHON_CODE, {"code": "result = 1"}),
                    ("two", TaskType.PYTHON_CODE, {"code": "result = 2"}),
                ]
            )

    def test_payload_size_limit_raises(self) -> None:
        tasker = AgentTasker(max_workers=1, max_payload_bytes=32)
        with self.assertRaises(RuntimeError):
            tasker.execute_tasks([("big", TaskType.PYTHON_CODE, {"code": "result = '" + ("x" * 100) + "'"})])

    def test_web_scrape_handles_unclosed_link_at_eof(self) -> None:
        root = f"http://127.0.0.1:{self.port}"
        tasker = AgentTasker(max_workers=1)
        result = tasker.execute_tasks([("scrape", TaskType.WEB_SCRAPE, {"url": f"{root}/malformed", "timeout": 5})])
        task = result["results"][0]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"]["title"], "Broken")
        self.assertEqual(task["result"]["links"][0]["url"], f"{root}/target")

    def test_invalid_web_scrape_regex_fails_validation(self) -> None:
        tasker = AgentTasker(max_workers=1)
        with self.assertRaises(ValueError):
            tasker.execute_tasks([("scrape", TaskType.WEB_SCRAPE, {"url": "http://example.com", "link_include_pattern": "(", "timeout": 5})])

    def test_file_write_append_mode(self) -> None:
        tmpdir = Path(tempfile.mkdtemp(prefix="agent_tasker_append_"))
        target = tmpdir / "log.txt"
        tasker = AgentTasker(max_workers=1)
        tasker.execute_tasks([("write1", TaskType.FILE_WRITE, {"path": str(target), "content": "a", "mode": "w"})])
        tasker.execute_tasks([("write2", TaskType.FILE_WRITE, {"path": str(target), "content": "b", "mode": "a"})])
        result = tasker.execute_tasks([("read", TaskType.FILE_READ, {"path": str(target)})])
        self.assertEqual(result["results"][0]["result"]["content"], "ab")

    def test_same_batch_file_write_then_read_same_path_succeeds(self) -> None:
        tmpdir = Path(tempfile.mkdtemp(prefix="agent_tasker_batch_file_"))
        target = tmpdir / "data.txt"
        tasker = AgentTasker(max_workers=4)
        result = tasker.execute_tasks(
            [
                ("write", TaskType.FILE_WRITE, {"path": str(target), "content": "hello", "mode": "w"}),
                ("read", TaskType.FILE_READ, {"path": str(target)}),
            ]
        )
        ordered = {task["name"]: task for task in result["results"]}
        self.assertEqual(ordered["write"]["status"], "completed")
        self.assertEqual(ordered["read"]["status"], "completed")
        self.assertEqual(ordered["read"]["result"]["content"], "hello")

    def test_explicit_dependency_allows_cross_task_ordering(self) -> None:
        tmpdir = Path(tempfile.mkdtemp(prefix="agent_tasker_dep_"))
        target = tmpdir / "dep.txt"
        tasker = AgentTasker(max_workers=4)
        result = tasker.execute_tasks(
            [
                (
                    "prepare",
                    TaskType.PYTHON_CODE,
                    {"code": f"from pathlib import Path\nPath({str(target)!r}).write_text('ready', encoding='utf-8')\nresult = 'ok'"},
                ),
                ("read", TaskType.FILE_READ, {"path": str(target)}, ["prepare"]),
            ]
        )
        ordered = {task["name"]: task for task in result["results"]}
        self.assertEqual(ordered["prepare"]["status"], "completed")
        self.assertEqual(ordered["read"]["status"], "completed")
        self.assertEqual(ordered["read"]["result"]["content"], "ready")

    def test_unknown_dependency_raises(self) -> None:
        tasker = AgentTasker(max_workers=1)
        with self.assertRaises(ValueError):
            tasker.execute_tasks([("read", TaskType.FILE_READ, {"path": "/tmp/missing"}, ["missing_task"])])

    def test_cyclic_dependencies_raise(self) -> None:
        tasker = AgentTasker(max_workers=1)
        with self.assertRaises(ValueError):
            tasker.execute_tasks(
                [
                    ("one", TaskType.PYTHON_CODE, {"code": "result = 1"}, ["two"]),
                    ("two", TaskType.PYTHON_CODE, {"code": "result = 2"}, ["one"]),
                ]
            )

    def test_failed_dependency_blocks_downstream(self) -> None:
        tasker = AgentTasker(max_workers=4)
        result = tasker.execute_tasks(
            [
                ("fail", TaskType.PYTHON_CODE, {"code": "raise RuntimeError('boom')"}),
                ("downstream", TaskType.PYTHON_CODE, {"code": "result = 'never'"}, ["fail"]),
            ]
        )
        ordered = {task["name"]: task for task in result["results"]}
        self.assertEqual(ordered["fail"]["status"], "failed")
        self.assertEqual(ordered["downstream"]["status"], "failed")
        self.assertIn("Blocked by failed dependencies: fail", ordered["downstream"]["error"])

    def test_shell_command_nonzero_exit_marks_task_failed(self) -> None:
        tasker = AgentTasker(max_workers=1)
        result = tasker.execute_tasks(
            [
                (
                    "shell_fail",
                    TaskType.SHELL_COMMAND,
                    {"command": "printf 'bad output' >&2; exit 7", "timeout": 5},
                )
            ]
        )
        task = result["results"][0]
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(task["status"], "failed")
        self.assertIsNone(task["result"])
        self.assertIn("exit code 7", task["error"])
        self.assertIn("bad output", task["error"])

    def test_failed_shell_command_blocks_downstream_dependency(self) -> None:
        tasker = AgentTasker(max_workers=4)
        result = tasker.execute_tasks(
            [
                ("shell_fail", TaskType.SHELL_COMMAND, {"command": "exit 7", "timeout": 5}),
                ("dependent", TaskType.PYTHON_CODE, {"code": "result = 'ran'"}, ["shell_fail"]),
            ]
        )
        ordered = {task["name"]: task for task in result["results"]}
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["failed"], 2)
        self.assertEqual(ordered["shell_fail"]["status"], "failed")
        self.assertEqual(ordered["dependent"]["status"], "failed")
        self.assertIsNone(ordered["dependent"]["result"])
        self.assertIn("Blocked by failed dependencies: shell_fail", ordered["dependent"]["error"])
