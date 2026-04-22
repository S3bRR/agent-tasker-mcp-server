from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Optional


class MCPProcess:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        self.process = subprocess.Popen(
            [sys.executable, "-m", "agent_tasker_mcp.server", "--workers", "1"],
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

    def close(self) -> None:
        for handle_name in ("stdin", "stdout", "stderr"):
            handle = getattr(self.process, handle_name)
            if handle:
                handle.close()
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)

    def send_raw(self, payload: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(payload + "\n")
        self.process.stdin.flush()

    def send(self, payload: Any) -> None:
        self.send_raw(json.dumps(payload, separators=(",", ":")))

    def read(self, timeout: float = 1.0) -> Optional[Any]:
        assert self.process.stdout is not None
        ready, _unused_write, _unused_error = select.select([self.process.stdout], [], [], timeout)
        if not ready:
            return None
        line = self.process.stdout.readline()
        return json.loads(line) if line else None

    def request(self, payload: Any, timeout: float = 1.0) -> Any:
        self.send(payload)
        response = self.read(timeout=timeout)
        if response is None:
            raise AssertionError("Expected response but received none")
        return response

    def initialize(self) -> Any:
        response = self.request(
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
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return response


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = MCPProcess()

    def tearDown(self) -> None:
        self.server.close()

    def test_parse_error_on_invalid_json(self) -> None:
        self.server.send_raw("{")
        response = self.server.read()
        self.assertEqual(response["error"]["code"], -32700)

    def test_rejects_requests_before_initialize(self) -> None:
        response = self.server.request({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        self.assertEqual(response["error"]["code"], -32002)

    def test_rejects_requests_before_initialized_notification(self) -> None:
        self.server.request(
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
        response = self.server.request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        self.assertEqual(response["error"]["code"], -32002)

    def test_notification_initialized_has_no_response(self) -> None:
        self.server.initialize()
        self.assertIsNone(self.server.read(timeout=0.2))

    def test_rejects_invalid_jsonrpc_version(self) -> None:
        response = self.server.request({"id": 1, "method": "ping"})
        self.assertEqual(response["error"]["code"], -32600)

    def test_empty_batch_is_invalid_request(self) -> None:
        response = self.server.request([])
        self.assertEqual(response["error"]["code"], -32600)

    def test_batch_request_returns_multiple_responses(self) -> None:
        self.server.initialize()
        self.server.send(
            [
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "execute",
                        "arguments": {"task_type": "python_code", "code": "result = 6 * 7"},
                    },
                },
            ]
        )
        response = self.server.read()
        self.assertIsInstance(response, list)
        self.assertEqual([item["id"] for item in response], [2, 3])
        self.assertEqual(response[1]["result"]["structuredContent"]["task"]["result"], 42)

    def test_unknown_method_returns_method_not_found(self) -> None:
        self.server.initialize()
        response = self.server.request({"jsonrpc": "2.0", "id": 2, "method": "bogus/method", "params": {}})
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool_returns_invalid_params(self) -> None:
        self.server.initialize()
        response = self.server.request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "bogus_tool", "arguments": {}},
            }
        )
        self.assertEqual(response["error"]["code"], -32602)

    def test_ping_allowed_before_initialize(self) -> None:
        response = self.server.request({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
        self.assertEqual(response["result"], {})

    def test_execute_batch_dependency_blocking_via_mcp(self) -> None:
        self.server.initialize()
        response = self.server.request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "execute_batch",
                    "arguments": {
                        "tasks": [
                            {"name": "fail", "task_type": "python_code", "code": "raise RuntimeError('boom')"},
                            {"name": "blocked", "task_type": "python_code", "code": "result = 'never'", "depends_on": ["fail"]},
                        ]
                    },
                },
            }
        )
        payload = response["result"]["structuredContent"]
        tasks = {task["name"]: task for task in payload["results"]}
        self.assertEqual(tasks["fail"]["status"], "failed")
        self.assertEqual(tasks["blocked"]["status"], "failed")
        self.assertIn("Blocked by failed dependencies: fail", tasks["blocked"]["error"])
