# AgentTasker MCP Server

<!-- mcp-name: io.github.s3brr/agent-tasker-mcp -->

AgentTasker is a minimal stdio MCP server for AI agents that need to run tasks in parallel and get structured results back in one call.

Repository: `https://github.com/S3bRR/agent-tasker-mcp`

## What It Exposes

- `execute`: run one task immediately
- `execute_batch`: run one or more tasks concurrently, with optional `depends_on`

Supported task types:

- `python_code`
- `http_request`
- `discovery_search`
- `web_scrape`
- `shell_command`
- `file_read`
- `file_write`

## Install

### Recommended: `uvx`

After publishing to PyPI, this is the standard client path:

```bash
uvx agent-tasker-mcp-server --workers 8
```

If you are running directly from source before a PyPI release:

```bash
uvx --from git+https://github.com/S3bRR/agent-tasker-mcp.git agent-tasker-mcp-server --workers 8
```

### `pipx`

After publishing to PyPI:

```bash
pipx install agent-tasker-mcp-server
```

From source today:

```bash
pipx install git+https://github.com/S3bRR/agent-tasker-mcp.git
```

### Local clone

```bash
git clone https://github.com/S3bRR/agent-tasker-mcp.git
cd agent-tasker-mcp
./setup.sh
```

`setup.sh` creates a local `.venv` and installs the package with no third-party runtime dependencies.

## MCP Client Config

### Standard published package

```json
{
  "command": "uvx",
  "args": ["agent-tasker-mcp-server", "--workers", "8"]
}
```

### Source checkout via `uvx`

```json
{
  "command": "uvx",
  "args": [
    "--from",
    "git+https://github.com/S3bRR/agent-tasker-mcp.git",
    "agent-tasker-mcp-server",
    "--workers",
    "8"
  ]
}
```

### Local clone

```json
{
  "command": "/absolute/path/to/agent-tasker-mcp/.venv/bin/agent-tasker-mcp-server",
  "args": ["--workers", "8"]
}
```

## Quick Sanity Check

After connecting the server, ask your model:

```text
Use the agent-tasker MCP. Call execute_batch with two python_code tasks returning 1 and 2, then show the results.
```

## Minimal `execute` Example

```json
{
  "task_type": "python_code",
  "code": "result = 6 * 7"
}
```

## Minimal `execute_batch` Example

```json
{
  "tasks": [
    {"name": "fetch_users", "task_type": "http_request", "url": "https://api.example.com/users"},
    {"name": "calc", "task_type": "python_code", "code": "result = 6 * 7"},
    {"name": "read_after_write", "task_type": "file_read", "path": "/tmp/example.txt", "depends_on": ["calc"]}
  ],
  "output_mode": "compact"
}
```

`output_mode` defaults to `compact`. Use `full` only when the model needs full HTTP bodies or full extracted page text.

## MCP Registry Metadata

This repo includes [server.json](./server.json) for MCP Registry publication. To publish cleanly:

1. Publish `agent-tasker-mcp-server` to PyPI.
2. Keep the PyPI package version and `server.json` version identical.
3. Keep the README `mcp-name` marker aligned with `server.json`.

## Environment Limits

- `AGENT_TASKER_MAX_TASKS`: max tasks per `execute_batch`
- `AGENT_TASKER_MAX_PAYLOAD_BYTES`: max payload size per task
- `AGENT_TASKER_MAX_MEMORY_MB`: process memory guard

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
agent-tasker-mcp-server --workers 4
```

Run tests:

```bash
.venv/bin/python -m unittest discover -s tests
```

## License

MIT (`LICENSE`)
