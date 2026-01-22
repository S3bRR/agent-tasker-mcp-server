#!/usr/bin/env python3
"""
AgentTasker - Parallel Task Execution System for Clawdy
Features:
  - Run tasks in parallel using threading
  - Task scheduling and queueing
  - Result aggregation
  - Progress tracking
  - JSON output for easy integration
"""

import json
import time
import uuid
from typing import Callable, Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """Represents a task to be executed."""
    id: str
    name: str
    function: Callable
    args: tuple = ()
    kwargs: dict = None
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}
    
    def to_dict(self):
        """Convert task to dictionary (excluding function)."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            "completed_at": datetime.fromtimestamp(self.completed_at).isoformat() if self.completed_at else None,
            "duration": (self.completed_at - self.started_at) if self.started_at and self.completed_at else None
        }


class AgentTasker:
    """Task executor for parallel task management."""
    
    def __init__(self, max_workers: int = 4):
        """
        Initialize tasker.
        
        Args:
            max_workers: Maximum number of parallel tasks
        """
        self.max_workers = max_workers
        self.tasks: Dict[str, Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def create_task(self, name: str, function: Callable, *args, **kwargs) -> str:
        """
        Create a task.
        
        Args:
            name: Task name
            function: Callable to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())[:8]
        task = Task(
            id=task_id,
            name=name,
            function=function,
            args=args,
            kwargs=kwargs
        )
        self.tasks[task_id] = task
        return task_id
    
    def _execute_task(self, task: Task) -> Task:
        """Execute a single task."""
        try:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            
            # Execute function
            result = task.function(*task.args, **task.kwargs)
            
            task.result = result
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED
        finally:
            task.completed_at = time.time()
        
        return task
    
    def run_tasks(self, task_ids: Optional[List[str]] = None, wait: bool = True) -> Dict[str, Any]:
        """
        Run tasks.
        
        Args:
            task_ids: Specific tasks to run (None = all)
            wait: Wait for completion
        
        Returns:
            Dictionary with results
        """
        if task_ids is None:
            task_ids = list(self.tasks.keys())
        
        # Submit tasks
        futures = {}
        for task_id in task_ids:
            task = self.tasks[task_id]
            future = self.executor.submit(self._execute_task, task)
            futures[future] = task_id
        
        results = {
            "total": len(task_ids),
            "tasks": {},
            "completed": 0,
            "failed": 0,
            "started_at": datetime.now().isoformat()
        }
        
        if wait:
            # Wait for completion
            for future in as_completed(futures):
                task_id = futures[future]
                task = future.result()
                self.tasks[task_id] = task
                results["tasks"][task_id] = task.to_dict()
                
                if task.status == TaskStatus.COMPLETED:
                    results["completed"] += 1
                elif task.status == TaskStatus.FAILED:
                    results["failed"] += 1
            
            results["completed_at"] = datetime.now().isoformat()
        
        return results
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get task status."""
        if task_id not in self.tasks:
            return {"error": f"Task {task_id} not found"}
        return self.tasks[task_id].to_dict()
    
    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all tasks."""
        return {
            task_id: task.to_dict()
            for task_id, task in self.tasks.items()
        }
    
    def summary(self) -> Dict[str, Any]:
        """Get summary of all tasks."""
        tasks = list(self.tasks.values())
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        running = sum(1 for t in tasks if t.status == TaskStatus.RUNNING)
        pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        
        total_duration = sum(
            (t.completed_at - t.started_at) for t in tasks
            if t.started_at and t.completed_at
        )
        
        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "pending": pending,
            "success_rate": f"{(completed/total*100):.1f}%" if total > 0 else "0%",
            "total_duration_seconds": f"{total_duration:.2f}"
        }
    
    def clear(self):
        """Clear all tasks."""
        self.tasks.clear()


# Example tasks
def sample_fetch_task(url: str) -> Dict[str, str]:
    """Example task: fetch URL."""
    import requests
    try:
        response = requests.get(url, timeout=5)
        return {
            "url": url,
            "status": response.status_code,
            "length": len(response.text)
        }
    except Exception as e:
        raise e


def sample_compute_task(n: int) -> Dict[str, int]:
    """Example task: compute something."""
    # Simulate computation
    time.sleep(1)
    result = sum(i**2 for i in range(n))
    return {
        "input": n,
        "result": result
    }


def main():
    """CLI interface and examples."""
    import sys
    
    print("🤖 AgentTasker - Parallel Task Execution")
    print("=" * 50)
    
    # Create tasker
    tasker = AgentTasker(max_workers=3)
    
    # Example tasks
    print("\n📝 Creating tasks...")
    
    task1 = tasker.create_task("compute_1", sample_compute_task, 1000)
    task2 = tasker.create_task("compute_2", sample_compute_task, 2000)
    task3 = tasker.create_task("compute_3", sample_compute_task, 3000)
    
    print(f"   Task 1: {task1}")
    print(f"   Task 2: {task2}")
    print(f"   Task 3: {task3}")
    
    # Run tasks
    print("\n⚡ Running tasks in parallel...")
    results = tasker.run_tasks([task1, task2, task3])
    
    print("\n✅ Results:")
    print(json.dumps(results, indent=2, default=str))
    
    print("\n📊 Summary:")
    print(json.dumps(tasker.summary(), indent=2))


if __name__ == "__main__":
    main()
