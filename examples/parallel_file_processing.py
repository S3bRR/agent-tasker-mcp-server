#!/usr/bin/env python3
"""
Example: Parallel File Processing

Demonstrates processing multiple files in parallel using AgentTasker.
This example shows how to process many files concurrently.
"""

import os
import json
from agent_tasker import AgentTasker


def process_file(filepath):
    """Process a file and return statistics."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        return {
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "size_bytes": len(content),
            "lines": content.count('\n') + 1,
            "words": len(content.split())
        }
    except Exception as e:
        raise Exception(f"Failed to process {filepath}: {str(e)}")


def create_sample_files():
    """Create sample files for processing."""
    sample_dir = "/tmp/sample_files"
    os.makedirs(sample_dir, exist_ok=True)

    # Create 5 sample text files
    for i in range(1, 6):
        filepath = os.path.join(sample_dir, f"file_{i}.txt")
        with open(filepath, 'w') as f:
            f.write(f"Sample content for file {i}\n" * 100)

    return sample_dir


def main():
    print("Parallel File Processing Example")
    print("=" * 50)

    # Create sample files
    print("Creating sample files...")
    sample_dir = create_sample_files()
    files = [
        os.path.join(sample_dir, f)
        for f in os.listdir(sample_dir)
        if f.endswith('.txt')
    ]

    print(f"Found {len(files)} files to process\n")

    # Create task executor
    tasker = AgentTasker(max_workers=4)

    # Create tasks for each file
    for filepath in files:
        task_name = os.path.basename(filepath)
        tasker.create_task(f"process_{task_name}", process_file, filepath)

    # Execute all tasks in parallel
    print("Processing files in parallel...")
    results = tasker.run_tasks()

    # Display results
    print(f"\nResults:")
    print(f"  Total: {results['total']}")
    print(f"  Completed: {results['completed']}")
    print(f"  Failed: {results['failed']}")

    # Collect and display file statistics
    stats = []
    for task_id, task_result in results["tasks"].items():
        if task_result["status"] == "completed":
            stats.append(task_result["result"])

    # Print table
    print("\nFile Statistics:")
    print("-" * 70)
    print(f"{'Filename':<20} {'Size (bytes)':<15} {'Lines':<10} {'Words':<10}")
    print("-" * 70)

    for stat in sorted(stats, key=lambda x: x['filename']):
        print(f"{stat['filename']:<20} {stat['size_bytes']:<15} {stat['lines']:<10} {stat['words']:<10}")

    # Summary
    summary = tasker.summary()
    print(f"\nSummary:")
    print(f"  Success Rate: {summary['success_rate']}")
    print(f"  Total Duration: {summary['total_duration_seconds']}s")
    print(f"  Total Size: {sum(s['size_bytes'] for s in stats)} bytes")


if __name__ == "__main__":
    main()
