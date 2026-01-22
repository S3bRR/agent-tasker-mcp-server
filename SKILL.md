---
name: task-executor
description: AgentTasker - Parallel task execution engine with concurrent workers, progress tracking, and result aggregation. Execute multiple independent tasks simultaneously for up to 16x performance improvement.
homepage: https://clawdhub.com/skills/task-executor
repository: https://github.com/clawdbot/skills
author: Clawdy
version: 1.0.0
license: MIT
compatibility: Python 3.7+
metadata:
  clawdbot:
    emoji: "🤖"
    requires:
      bins: ["python3"]
---

# AgentTasker - Parallel Task Execution Engine

A production-grade task execution system for running multiple independent operations concurrently with automatic worker management, progress tracking, and comprehensive result aggregation.

## Overview

AgentTasker enables you to execute any Python function in parallel across multiple workers. Instead of running tasks sequentially (100 tasks = 100 seconds), execute them concurrently (100 tasks = 12-15 seconds with 8 workers).

### Performance Metrics

- Sequential execution: 100 tasks × 1 second = 100 seconds
- Parallel execution (8 workers): 100 tasks ÷ 8 workers = ~12 seconds
- Performance improvement: 8x faster

## Installation

Copy the skill directory to your Clawdbot skills folder:

```bash
clawdhub install task-executor
```

Or manually:

```bash
cp -r task-executor ~/.clawdbot/skills/
```

## Quick Start

```python
from agent_tasker import AgentTasker

# Initialize with worker count
tasker = AgentTasker(max_workers=4)

# Define work function
def fetch_data(url):
    import requests
    response = requests.get(url, timeout=5)
    return {"url": url, "status": response.status_code}

# Create tasks
task1 = tasker.create_task("fetch_1", fetch_data, "https://api.example.com/1")
task2 = tasker.create_task("fetch_2", fetch_data, "https://api.example.com/2")
task3 = tasker.create_task("fetch_3", fetch_data, "https://api.example.com/3")

# Execute all tasks in parallel
results = tasker.run_tasks([task1, task2, task3])

# Process results
for task_id, task_result in results["tasks"].items():
    if task_result["status"] == "completed":
        print(f"Task {task_id}: {task_result['result']}")
    elif task_result["status"] == "failed":
        print(f"Task {task_id} failed: {task_result['error']}")
```

## Core Concepts

### Task

A unit of work containing:
- Task ID (auto-generated UUID)
- Name (descriptive identifier)
- Function (callable)
- Arguments (positional and keyword)
- Status (pending, running, completed, failed)
- Result (function return value or error)
- Timing information (start, end, duration)

### Worker

A thread pool worker that executes tasks. Default: 4 workers, configurable up to 16+.

### Status States

```
PENDING -> RUNNING -> COMPLETED
                  -> FAILED
```

## API Reference

### AgentTasker Class

```python
class AgentTasker:
    def __init__(self, max_workers: int = 4)
    def create_task(self, name: str, function: Callable, *args, **kwargs) -> str
    def run_tasks(self, task_ids: Optional[List[str]] = None, wait: bool = True) -> Dict
    def get_task_status(self, task_id: str) -> Dict
    def get_all_status(self) -> Dict
    def summary(self) -> Dict
    def clear(self)
```

### Methods

#### create_task(name, function, *args, **kwargs)

Create a task without executing it.

**Parameters:**
- name (str): Unique task identifier
- function (Callable): Function to execute
- args (tuple): Positional arguments for function
- kwargs (dict): Keyword arguments for function

**Returns:** str - Task ID

**Example:**
```python
task_id = tasker.create_task("process_file", process_csv, "data.csv", delimiter=",")
```

#### run_tasks(task_ids=None, wait=True)

Execute tasks in parallel.

**Parameters:**
- task_ids (List[str], optional): Specific tasks to run. Default: all tasks
- wait (bool): Block until completion. Default: True

**Returns:** Dict with execution results

**Example:**
```python
results = tasker.run_tasks([task1, task2, task3], wait=True)
```

**Response Format:**
```json
{
  "total": 3,
  "completed": 2,
  "failed": 1,
  "tasks": {
    "task_1": {
      "id": "task_1",
      "name": "fetch_1",
      "status": "completed",
      "result": {...},
      "error": null,
      "duration": 1.23
    }
  }
}
```

#### get_task_status(task_id)

Get status of a single task.

**Parameters:**
- task_id (str): Task identifier

**Returns:** Dict with task status

#### get_all_status()

Get status of all tasks.

**Returns:** Dict mapping task IDs to status objects

#### summary()

Get aggregate statistics.

**Returns:** Dict with summary metrics

**Response Format:**
```json
{
  "total_tasks": 10,
  "completed": 8,
  "failed": 0,
  "running": 2,
  "pending": 0,
  "success_rate": "100.0%",
  "total_duration_seconds": "12.45"
}
```

#### clear()

Clear all tasks from memory.

## Usage Examples

### Example 1: Parallel API Requests

```python
from agent_tasker import AgentTasker
import requests

tasker = AgentTasker(max_workers=8)

endpoints = [
    "https://api.example.com/users/1",
    "https://api.example.com/users/2",
    "https://api.example.com/users/3",
]

for endpoint in endpoints:
    tasker.create_task(f"fetch_{endpoint}", requests.get, endpoint)

results = tasker.run_tasks()
print(f"Completed: {results['completed']}/{results['total']}")
```

### Example 2: Parallel Data Processing

```python
import csv
from agent_tasker import AgentTasker

def process_csv(filename):
    with open(filename) as f:
        reader = csv.DictReader(f)
        return len(list(reader))

tasker = AgentTasker(max_workers=4)

files = ["data1.csv", "data2.csv", "data3.csv", "data4.csv"]

for filename in files:
    tasker.create_task(f"process_{filename}", process_csv, filename)

results = tasker.run_tasks()

for task_id, task in results["tasks"].items():
    if task["status"] == "completed":
        print(f"{task['name']}: {task['result']} rows")
```

### Example 3: Parallel Web Scraping

```python
from agent_tasker import AgentTasker
from web_scraper import PowerScraper

scraper = PowerScraper()
tasker = AgentTasker(max_workers=8)

urls = [
    "https://example.com/page1",
    "https://example.com/page2",
    "https://example.com/page3",
]

for url in urls:
    tasker.create_task(f"scrape_{url}", scraper.fetch, url)

results = tasker.run_tasks()
print(f"Scraped {results['completed']} URLs in {results['duration']}")
```

### Example 4: Parallel Email Sending

```python
from agent_tasker import AgentTasker

def send_email(recipient, subject, body):
    import smtplib
    # Email sending logic here
    return True

tasker = AgentTasker(max_workers=10)

recipients = ["user1@example.com", "user2@example.com", ...]

for recipient in recipients:
    tasker.create_task(
        f"email_{recipient}",
        send_email,
        recipient,
        "Newsletter",
        "Latest updates..."
    )

results = tasker.run_tasks()
print(f"Sent {results['completed']} emails successfully")
```

## Configuration

### Worker Count

Optimal worker count depends on task type:

- I/O-bound tasks (network, file I/O): 2x CPU count
- CPU-bound tasks (computation): CPU count
- Mixed workloads: 4-8 workers

```python
import os
optimal_workers = os.cpu_count() * 2
tasker = AgentTasker(max_workers=optimal_workers)
```

### Performance Tuning

```python
# For many short tasks
tasker = AgentTasker(max_workers=16)

# For few long tasks
tasker = AgentTasker(max_workers=2)

# Balanced
tasker = AgentTasker(max_workers=8)
```

## Error Handling

Tasks that raise exceptions are captured and reported:

```python
def risky_task():
    raise ValueError("Something went wrong")

tasker = AgentTasker()
task_id = tasker.create_task("risky", risky_task)
results = tasker.run_tasks([task_id])

task_result = results["tasks"][task_id]
if task_result["status"] == "failed":
    print(f"Error: {task_result['error']}")
```

## Integration with Other Skills

### With data-scraper

```python
from agent_tasker import AgentTasker
from web_scraper import PowerScraper

scraper = PowerScraper()
tasker = AgentTasker(max_workers=8)

for url in urls:
    tasker.create_task(f"scrape_{url}", scraper.fetch, url)

results = tasker.run_tasks()
```

### With data-pipeline

```python
from data_pipeline import DataPipeline

pipeline = DataPipeline("my_workflow", max_workers=8)
# Internally uses AgentTasker for parallel execution
results = pipeline.run()
```

## Best Practices

1. Define functions with clear return values
2. Handle exceptions within task functions when possible
3. Use descriptive task names for easier debugging
4. Monitor results before processing
5. Clear tasks when done to free memory
6. Use appropriate worker count for your workload

## Limitations

- Tasks must be independent (no shared mutable state)
- Functions must be picklable (work with ThreadPoolExecutor)
- No built-in timeout per task (implement in function if needed)
- Results kept in memory (clear() to free)

## Troubleshooting

### Tasks not completing

Check that max_workers is appropriate for your workload and that tasks are not blocking.

### High memory usage

Call clear() after processing results, or process results in batches.

### Tasks failing silently

Check task results for "failed" status and review error messages.

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or suggestions, please refer to the Clawdbot documentation or repository.

## Changelog

### Version 1.0.0
- Initial release
- Task creation and execution
- Parallel worker management
- Result aggregation
- Progress tracking
- Error handling
