# AgentTasker - Parallel Task Execution Engine

A production-grade Python library for executing multiple independent tasks in parallel with automatic worker management, real-time progress tracking, and comprehensive result aggregation.

## Overview

AgentTasker enables efficient parallel task execution by distributing work across multiple worker threads. Transform sequential operations into concurrent execution to dramatically improve throughput.

### What It Does

- Execute any Python function in parallel
- Automatic worker pool management
- Real-time task status tracking
- Comprehensive error handling
- Result aggregation and reporting
- Performance metrics and timing

### Why You Need It

Sequential task execution is slow:
```
100 tasks × 1 second each = 100 seconds
```

Parallel execution with AgentTasker is fast:
```
100 tasks ÷ 8 workers = 12-15 seconds (8x faster)
```

## Installation

### Via ClawdHub

```bash
clawdhub install task-executor
```

### Manual

```bash
cp -r task-executor ~/.clawdbot/skills/
cd ~/.clawdbot/skills/task-executor
pip install -r requirements.txt
```

### Requirements

- Python 3.7 or higher
- No external dependencies (uses standard library only)

## Quick Start

### Basic Usage

```python
from agent_tasker import AgentTasker

# Create task executor with 4 workers
tasker = AgentTasker(max_workers=4)

# Define a task function
def process_item(item_id):
    return item_id * 2

# Create tasks
for i in range(10):
    tasker.create_task(f"process_{i}", process_item, i)

# Execute all tasks in parallel
results = tasker.run_tasks()

# Process results
for task_id, task_result in results["tasks"].items():
    print(f"Task {task_id}: {task_result['result']}")
```

### Real-World Example: API Requests

```python
from agent_tasker import AgentTasker
import requests

def fetch_user(user_id):
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()

tasker = AgentTasker(max_workers=8)

# Queue 100 API requests
for user_id in range(1, 101):
    tasker.create_task(f"fetch_user_{user_id}", fetch_user, user_id)

# Execute all in parallel
results = tasker.run_tasks()

# Collect successful results
users = []
for task_id, task_result in results["tasks"].items():
    if task_result["status"] == "completed":
        users.append(task_result["result"])

print(f"Retrieved {len(users)} users")
```

## Features

### Task Management

- Create tasks with arbitrary function arguments
- Automatic task ID generation
- Task naming for easy identification
- Support for positional and keyword arguments

### Worker Management

- Configurable worker count (1-32+)
- Automatic thread pool lifecycle management
- Efficient workload distribution
- Graceful shutdown handling

### Progress Tracking

- Real-time task status monitoring
- Per-task timing information
- Aggregate statistics
- Success/failure reporting

### Error Handling

- Task-level exception capture
- Error messages preserved
- Non-blocking failure (other tasks continue)
- Comprehensive error reporting

### Result Aggregation

- All results returned in structured format
- Timing information for each task
- Execution statistics
- Easy result filtering and processing

## Use Cases

### Web Scraping

Scrape multiple websites simultaneously:

```python
from agent_tasker import AgentTasker
from web_scraper import PowerScraper

scraper = PowerScraper()
tasker = AgentTasker(max_workers=10)

websites = [
    "https://site1.com",
    "https://site2.com",
    "https://site3.com",
]

for website in websites:
    tasker.create_task(f"scrape_{website}", scraper.fetch, website)

results = tasker.run_tasks()
```

### Data Processing

Process multiple files in parallel:

```python
def process_file(filename):
    with open(filename) as f:
        return len(f.readlines())

tasker = AgentTasker(max_workers=8)

for filename in files:
    tasker.create_task(f"process_{filename}", process_file, filename)

results = tasker.run_tasks()
```

### API Integration

Call multiple API endpoints simultaneously:

```python
def call_endpoint(endpoint):
    import requests
    return requests.get(f"https://api.example.com{endpoint}").json()

tasker = AgentTasker(max_workers=10)

endpoints = ["/users", "/posts", "/comments", "/products"]

for endpoint in endpoints:
    tasker.create_task(f"call_{endpoint}", call_endpoint, endpoint)

results = tasker.run_tasks()
```

### Batch Email Sending

Send emails to thousands of recipients in parallel:

```python
def send_email(recipient, subject, body):
    import smtplib
    # Email sending implementation
    return True

tasker = AgentTasker(max_workers=20)

for recipient in recipients:
    tasker.create_task(
        f"email_{recipient}",
        send_email,
        recipient,
        "Newsletter",
        "Content..."
    )

results = tasker.run_tasks()
```

### Load Testing

Stress test your API with concurrent requests:

```python
def make_request(request_num):
    import requests
    return requests.get("https://yourapi.com/endpoint").status_code

tasker = AgentTasker(max_workers=50)

for i in range(1000):
    tasker.create_task(f"request_{i}", make_request, i)

results = tasker.run_tasks()
```

## Performance Guide

### Optimal Worker Count

Adjust based on task type:

```python
# I/O-bound tasks (network, file operations)
tasker = AgentTasker(max_workers=16)

# CPU-bound tasks (computation)
tasker = AgentTasker(max_workers=4)

# Mixed workload (recommended default)
tasker = AgentTasker(max_workers=8)
```

### Performance Metrics

```
Task Count | Sequential | Parallel(8) | Speedup
-----------|-----------|------------|--------
10         | 10s       | 2s         | 5x
50         | 50s       | 7s         | 7x
100        | 100s      | 13s        | 8x
1000       | 1000s     | 125s       | 8x
```

### Memory Considerations

- Each worker consumes minimal memory
- Task results stored in memory until cleared
- For large result sets, process incrementally
- Call tasker.clear() to free memory

## API Reference

### AgentTasker

Main class for task management and execution.

#### __init__(max_workers: int = 4)

Initialize the task executor.

**Parameters:**
- max_workers (int): Number of parallel worker threads. Default: 4

**Example:**
```python
tasker = AgentTasker(max_workers=8)
```

#### create_task(name: str, function: Callable, *args, **kwargs) -> str

Create a task for later execution.

**Parameters:**
- name (str): Unique task identifier
- function (Callable): Function to execute
- args (tuple): Positional arguments
- kwargs (dict): Keyword arguments

**Returns:**
- str: Task ID

**Example:**
```python
task_id = tasker.create_task("my_task", my_function, arg1, kwarg1=value1)
```

#### run_tasks(task_ids: Optional[List[str]] = None, wait: bool = True) -> Dict

Execute tasks in parallel.

**Parameters:**
- task_ids (List[str], optional): Specific tasks to run. Default: all
- wait (bool): Block until completion. Default: True

**Returns:**
- Dict: Execution results and statistics

**Example:**
```python
results = tasker.run_tasks([task1_id, task2_id], wait=True)
```

#### get_task_status(task_id: str) -> Dict

Get status of a specific task.

**Parameters:**
- task_id (str): Task identifier

**Returns:**
- Dict: Task status information

**Example:**
```python
status = tasker.get_task_status(task_id)
print(status["status"])  # "completed", "failed", etc.
```

#### get_all_status() -> Dict[str, Dict]

Get status of all tasks.

**Returns:**
- Dict: Mapping of task IDs to status dictionaries

**Example:**
```python
all_statuses = tasker.get_all_status()
```

#### summary() -> Dict

Get aggregate statistics.

**Returns:**
- Dict: Summary metrics including total, completed, failed counts

**Example:**
```python
summary = tasker.summary()
print(f"Completed: {summary['completed']}/{summary['total_tasks']}")
```

#### clear()

Clear all tasks from memory.

**Example:**
```python
tasker.clear()
```

## Response Format

### Task Status

```json
{
  "id": "task_123",
  "name": "fetch_user_1",
  "status": "completed",
  "result": {
    "id": 1,
    "name": "John Doe"
  },
  "error": null,
  "started_at": "2026-01-22T14:00:00",
  "completed_at": "2026-01-22T14:00:01",
  "duration": 1.234
}
```

### Execution Results

```json
{
  "total": 10,
  "completed": 9,
  "failed": 1,
  "started_at": "2026-01-22T14:00:00",
  "completed_at": "2026-01-22T14:00:10",
  "tasks": {
    "task_1": {...},
    "task_2": {...}
  }
}
```

### Summary Statistics

```json
{
  "total_tasks": 100,
  "completed": 98,
  "failed": 2,
  "running": 0,
  "pending": 0,
  "success_rate": "98.0%",
  "total_duration_seconds": "12.45"
}
```

## Error Handling

Tasks that raise exceptions are captured without affecting other tasks:

```python
def may_fail(value):
    if value < 0:
        raise ValueError("Negative value not allowed")
    return value * 2

tasker = AgentTasker()
tasker.create_task("fail", may_fail, -5)
results = tasker.run_tasks()

# Check result
task_result = results["tasks"]["fail"]
if task_result["status"] == "failed":
    print(f"Error: {task_result['error']}")
```

## Best Practices

1. Use clear task names for debugging
2. Keep tasks independent (avoid shared state)
3. Handle exceptions within task functions when appropriate
4. Monitor results before processing
5. Use appropriate worker count for workload
6. Clear tasks after processing to free memory
7. Test with small task counts before scaling

## Troubleshooting

### Tasks not executing

Ensure max_workers is greater than number of tasks:
```python
tasker = AgentTasker(max_workers=10)
# Good for 1-100 tasks
```

### High memory usage

Process results in batches:
```python
results = tasker.run_tasks()
process_results(results)
tasker.clear()
```

### Function not found errors

Ensure functions are defined at module level, not inside other functions.

### Tasks timing out

Implement timeout logic inside task functions:
```python
def task_with_timeout(url, timeout=10):
    import requests
    return requests.get(url, timeout=timeout)
```

## Integration with Clawdbot Skills

AgentTasker works seamlessly with other Clawdbot skills:

- data-scraper: Scrape multiple URLs in parallel
- data-pipeline: Orchestrate complex workflows
- Notion: Write results to databases in parallel
- GitHub: Create issues/PRs in parallel

## Examples

See the `examples/` directory for complete working examples:

- `concurrent_api_calls.py` - Make multiple API requests
- `parallel_file_processing.py` - Process multiple files
- `web_scraping_parallel.py` - Scrape multiple websites
- `email_broadcast.py` - Send emails in parallel

## License

MIT License - See LICENSE file

## Support

For issues or questions, refer to Clawdbot documentation or repository.

## Version History

### 1.0.0 (2026-01-22)
- Initial release
- Full task execution capabilities
- Worker pool management
- Result aggregation
- Error handling
