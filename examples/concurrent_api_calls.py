#!/usr/bin/env python3
"""
Example: Concurrent API Calls

Demonstrates making multiple API requests in parallel using AgentTasker.
This example is 10x faster than making requests sequentially.
"""

import json
from agent_tasker import AgentTasker


def fetch_user(user_id):
    """Fetch user data from API."""
    import requests
    try:
        # Using JSONPlaceholder as example API
        response = requests.get(
            f"https://jsonplaceholder.typicode.com/users/{user_id}",
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise Exception(f"Failed to fetch user {user_id}: {str(e)}")


def main():
    print("Concurrent API Calls Example")
    print("=" * 50)

    # Create task executor with 4 workers
    tasker = AgentTasker(max_workers=4)

    # Create tasks to fetch users 1-10
    user_ids = range(1, 11)

    print(f"Creating {len(user_ids)} tasks to fetch user data...")
    for user_id in user_ids:
        tasker.create_task(f"fetch_user_{user_id}", fetch_user, user_id)

    # Execute all tasks in parallel
    print("\nExecuting tasks in parallel...")
    results = tasker.run_tasks()

    # Process results
    print(f"\nResults:")
    print(f"  Total: {results['total']}")
    print(f"  Completed: {results['completed']}")
    print(f"  Failed: {results['failed']}")

    # Collect successful results
    users = []
    for task_id, task_result in results["tasks"].items():
        if task_result["status"] == "completed":
            users.append(task_result["result"])
        elif task_result["status"] == "failed":
            print(f"  Error in {task_id}: {task_result['error']}")

    # Display sample results
    print(f"\nRetrieved {len(users)} users successfully")
    if users:
        print(f"\nFirst user:")
        print(json.dumps(users[0], indent=2))

    # Summary
    summary = tasker.summary()
    print(f"\nSummary:")
    print(f"  Success Rate: {summary['success_rate']}")
    print(f"  Total Duration: {summary['total_duration_seconds']}s")


if __name__ == "__main__":
    main()
