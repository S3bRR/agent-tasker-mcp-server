# AgentTasker MCP Server

<!-- mcp-name: io.github.S3bRR/agent-tasker-mcp -->

AgentTasker is a small, stdio-only MCP server for AI agents that need to run multiple tasks quickly and get structured results back in one call.

It is intentionally narrow:

- two tools: `execute` and `execute_batch`
- local stdio transport only
- zero third-party runtime dependencies
- explicit dependency control with `depends_on`
- compact, model-friendly JSON responses

Repository: `https://github.com/S3bRR/agent-tasker-mcp`

## Why This Exists

Most agent orchestration layers are heavier than they need to be. This project is designed for the common case:

- run a few tasks in parallel
- let one task wait on another when needed
- keep the MCP surface small enough for models to use reliably

There is no queue service, no persistence layer, no background worker system, and no SDK dependency required at runtime.

## What It Supports

Task types:

- `python_code`
- `http_request`
- `discovery_search`
- `web_scrape`
- `shell_command`
- `file_read`
- `file_write`

Public MCP tools:

- `execute`
- `execute_batch`

## Install

Requirements:

- Python 3.10+
- A local MCP client that can run stdio servers

### Recommended: `uvx`

Run directly from GitHub:

```bash
uvx --from git+https://github.com/S3bRR/agent-tasker-mcp.git agent-tasker-mcp-server --workers 8
```

Once the package is live on PyPI, the command becomes:

```bash
uvx agent-tasker-mcp-server --workers 8
```

### `pipx`

Install directly from GitHub:

```bash
pipx install git+https://github.com/S3bRR/agent-tasker-mcp.git
```

Once the package is live on PyPI, the command becomes:

```bash
pipx install agent-tasker-mcp-server
```

### Local clone

```bash
git clone https://github.com/S3bRR/agent-tasker-mcp.git
cd agent-tasker-mcp
./setup.sh
```

`setup.sh` creates a local `.venv`, installs this package into it, and prints an
absolute MCP config snippet. If `python3 -m venv` is not available, it falls back
to `virtualenv` when installed.

## MCP Client Configuration

### GitHub Source

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

### Installed Package

```json
{
  "command": "agent-tasker-mcp-server",
  "args": ["--workers", "8"]
}
```

### Local checkout

```json
{
  "command": "/absolute/path/to/agent-tasker-mcp/.venv/bin/agent-tasker-mcp-server",
  "args": ["--workers", "8"]
}
```

Use the exact absolute path printed by `./setup.sh` for local checkouts.

## Usage

### `execute`

Run one task immediately.

```json
{
  "task_type": "python_code",
  "code": "result = 6 * 7"
}
```

### `execute_batch`

Run multiple tasks concurrently.

```json
{
  "tasks": [
    {
      "name": "fetch_users",
      "task_type": "http_request",
      "url": "https://api.example.com/users"
    },
    {
      "name": "calc",
      "task_type": "python_code",
      "code": "result = 6 * 7"
    }
  ],
  "output_mode": "compact"
}
```

### `depends_on`

If one task must wait for another, make it explicit.

```json
{
  "tasks": [
    {
      "name": "write_file",
      "task_type": "file_write",
      "path": "/tmp/example.txt",
      "content": "hello"
    },
    {
      "name": "read_file",
      "task_type": "file_read",
      "path": "/tmp/example.txt",
      "depends_on": ["write_file"]
    }
  ]
}
```

If an upstream dependency fails, downstream tasks are marked failed and do not run.

## Output Shape

`output_mode` supports:

- `compact` (default)
- `full`

The response is ordered to match the input task list, which makes it easier for models to consume without extra reconciliation logic.

## Release Process

Releases are tag-driven.

1. update `pyproject.toml` and `server.json` to the same version
2. commit and push to `main`
3. create and push a matching tag such as `v1.0.0`
4. GitHub Actions runs tests, builds the package, publishes to PyPI through Trusted Publishing, and then publishes `server.json` to the MCP Registry

The release workflow rejects version drift: the pushed tag, `pyproject.toml`, and `server.json` must match exactly.

## Limits

Optional environment variables:

- `AGENT_TASKER_MAX_TASKS`: maximum tasks per `execute_batch`
- `AGENT_TASKER_MAX_PAYLOAD_BYTES`: maximum payload size per task
- `AGENT_TASKER_MAX_MEMORY_MB`: soft process memory guard

## Security Notes

This server is intended for trusted environments.

- `python_code` executes Python code
- `shell_command` executes shell commands
- `file_read` and `file_write` operate on the local filesystem

Do not expose this server directly to untrusted users.

## Development

Create a local environment:

```bash
./setup.sh
source .venv/bin/activate
```

Run the server:

```bash
agent-tasker-mcp-server --workers 4
```

Run tests:

```bash
.venv/bin/python -m unittest discover -s tests
```

## Packaging

This repo includes [server.json](./server.json) for MCP Registry publication and a GitHub Actions workflow that publishes both the PyPI package and MCP metadata from a version tag.

## License

MIT
