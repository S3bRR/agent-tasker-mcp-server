from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent_tasker_mcp.models import TaskType
from agent_tasker_mcp.server import AgentTasker, _tool_catalog


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/json":
            self._json({"ok": True, "path": parsed.path})
            return
        if parsed.path == "/search":
            query = parse_qs(parsed.query)
            q = query.get("q", [""])[0]
            self._json({"items": [{"title": f"Result for {q}", "url": f"http://{self.headers['Host']}/page", "snippet": "Local result"}]})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<html><head><title>Local Page</title><meta name='description' content='Local page'></head><body><h1>Hello</h1><p>Local body text.</p></body></html>")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class SmokeTests(unittest.TestCase):
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

    def test_core_tasks(self) -> None:
        root = f"http://127.0.0.1:{self.port}"
        tmpdir = Path(tempfile.mkdtemp(prefix="agent_tasker_test_"))
        tasker = AgentTasker(max_workers=4)
        providers = [{
            "name": "local",
            "url_template": f"{root}/search?q={{query_encoded}}&limit={{limit}}",
            "items_path": "items",
            "title_path": "title",
            "url_path": "url",
            "snippet_path": "snippet",
        }]
        result = tasker.execute_tasks([
            ("calc", TaskType.PYTHON_CODE, {"code": "result = 21 * 2"}),
            ("write", TaskType.FILE_WRITE, {"path": str(tmpdir / "hello.txt"), "content": "hello", "mode": "w"}),
            ("http", TaskType.HTTP_REQUEST, {"url": f"{root}/json", "method": "GET", "timeout": 5}),
            ("scrape", TaskType.WEB_SCRAPE, {"url": f"{root}/page", "timeout": 5, "max_text_chars": 200}),
            ("discover", TaskType.DISCOVERY_SEARCH, {"query": "agent tasker", "providers": providers, "max_results": 1, "timeout": 5}),
            ("read", TaskType.FILE_READ, {"path": str(tmpdir / "hello.txt")}),
        ])
        ordered = {task["name"]: task for task in result["results"]}
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["completed"], len(result["results"]))
        self.assertEqual(ordered["calc"]["result"], 42)
        self.assertEqual(ordered["read"]["result"]["content"], "hello")
        self.assertEqual(ordered["http"]["result"]["status_code"], 200)
        self.assertEqual(ordered["scrape"]["result"]["title"], "Local Page")
        self.assertEqual(ordered["discover"]["result"]["returned_count"], 1)

    def test_execute_tasks_default_is_ephemeral(self) -> None:
        tasker = AgentTasker(max_workers=2)
        result = tasker.execute_tasks([("calc", TaskType.PYTHON_CODE, {"code": "result = 40 + 2"})])
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["results"][0]["result"], 42)

    def test_public_tool_surface(self) -> None:
        self.assertEqual([name for name, _description, _schema in _tool_catalog()], ["execute", "execute_batch"])
        execute_batch_schema = {name: schema for name, _description, schema in _tool_catalog()}["execute_batch"]
        task_properties = execute_batch_schema["properties"]["tasks"]["items"]["properties"]
        self.assertIn("depends_on", task_properties)

    def test_stdio_mcp_protocol(self) -> None:
        root = Path(__file__).resolve().parents[1]
        env = {**dict(os.environ), "PYTHONDONTWRITEBYTECODE": "1"}
        process = subprocess.Popen(
            [sys.executable, "-m", "agent_tasker_mcp.server", "--workers", "1"],
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())
        self.addCleanup(lambda: process.stdin and process.stdin.close())
        self.addCleanup(lambda: process.stdout and process.stdout.close())
        self.addCleanup(lambda: process.stderr and process.stderr.close())

        def exchange(message: dict) -> dict:
            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            self.assertTrue(line)
            return json.loads(line)

        initialize = exchange(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            }
        )
        self.assertEqual(initialize["result"]["serverInfo"]["name"], "agent-tasker")

        assert process.stdin is not None
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        process.stdin.flush()

        tools = exchange({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        self.assertEqual([tool["name"] for tool in tools["result"]["tools"]], ["execute", "execute_batch"])

        called = exchange(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "execute",
                    "arguments": {"task_type": "python_code", "code": "result = 6 * 7"},
                },
            }
        )
        payload = called["result"]["structuredContent"]
        self.assertFalse(called["result"]["isError"])
        self.assertEqual(payload["task"]["result"], 42)

        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
