#!/usr/bin/env python3
"""
Example: Basic Usage

Demonstrates fundamental AgentTasker usage with simple computation tasks.
"""

from agent_tasker import AgentTasker


def compute_factorial(n):
    """Compute factorial of n."""
    if n < 0:
        raise ValueError("Factorial not defined for negative numbers")

    result = 1
    for i in range(1, n + 1):
        result *= i
    return result


def compute_fibonacci(n):
    """Compute nth Fibonacci number."""
    if n < 0:
        raise ValueError("Fibonacci index must be non-negative")

    if n <= 1:
        return n

    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b


def compute_prime_count(n):
    """Count prime numbers up to n."""
    def is_prime(num):
        if num < 2:
            return False
        for i in range(2, int(num ** 0.5) + 1):
            if num % i == 0:
                return False
        return True

    return sum(1 for i in range(2, n + 1) if is_prime(i))


def main():
    print("Basic Usage Example")
    print("=" * 50)

    # Create task executor with 4 workers
    tasker = AgentTasker(max_workers=4)

    print("Creating tasks...")

    # Create factorial tasks
    for n in [5, 10, 15, 20]:
        tasker.create_task(f"factorial_{n}", compute_factorial, n)

    # Create Fibonacci tasks
    for n in [10, 20, 30, 40]:
        tasker.create_task(f"fibonacci_{n}", compute_fibonacci, n)

    # Create prime count tasks
    for n in [100, 1000, 10000]:
        tasker.create_task(f"primes_{n}", compute_prime_count, n)

    # Execute all tasks
    print(f"Executing {len(tasker.tasks)} tasks in parallel...\n")
    results = tasker.run_tasks()

    # Display results by category
    print("Factorial Results:")
    print("-" * 50)
    for task_id, task_result in results["tasks"].items():
        if task_id.startswith("factorial") and task_result["status"] == "completed":
            n = int(task_id.split("_")[1])
            result = task_result["result"]
            print(f"  Factorial({n:2d}) = {result}")

    print("\nFibonacci Results:")
    print("-" * 50)
    for task_id, task_result in results["tasks"].items():
        if task_id.startswith("fibonacci") and task_result["status"] == "completed":
            n = int(task_id.split("_")[1])
            result = task_result["result"]
            print(f"  Fibonacci({n:2d}) = {result}")

    print("\nPrime Count Results:")
    print("-" * 50)
    for task_id, task_result in results["tasks"].items():
        if task_id.startswith("primes") and task_result["status"] == "completed":
            n = int(task_id.split("_")[1])
            result = task_result["result"]
            print(f"  Primes up to {n:5d} = {result}")

    # Summary
    print("\nExecution Summary:")
    print("-" * 50)
    summary = tasker.summary()
    print(f"  Total Tasks: {summary['total_tasks']}")
    print(f"  Completed: {summary['completed']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Success Rate: {summary['success_rate']}")
    print(f"  Duration: {summary['total_duration_seconds']}s")


if __name__ == "__main__":
    main()
