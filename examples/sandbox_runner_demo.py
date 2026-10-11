#!/usr/bin/env python3
"""
Sandbox Runner Demo
-------------------
A clean, runnable Python script demonstrating the core principles of a 
Remote Code Execution Engine:
  1. Timeouts (Watchdog timer against infinite loops)
  2. Memory Caps (Protecting against Out-Of-Memory attacks)
  3. Output Truncation (Protecting against infinite printing)
  4. Isolation metrics (CPU execution time and memory peak)

Run this file locally:
  python3 sandbox_runner_demo.py
"""

import sys
import time
import subprocess
import json

MAX_OUTPUT_BYTES = 10 * 1024  # 10 KB output limit to avoid terminal flood
DEFAULT_TIMEOUT_SEC = 2.0     # 2 seconds max execution time


def run_sandboxed_code(code_string: str, stdin_data: str = "", timeout_sec: float = DEFAULT_TIMEOUT_SEC):
    """
    Executes a snippet of Python code in an isolated subprocess with 
    strict timeout, output truncation and exit code trapping.
    """
    start_time = time.perf_counter()

    # Pre-execution limits wrapper for the child process:
    # On Linux/macOS, we can set memory limits via python's `resource` module inside preexec_fn
    def set_child_resource_limits():
        try:
            import resource
            # Limit Virtual Memory (address space) to 128 MB (128 * 1024 * 1024 bytes)
            max_memory_bytes = 128 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))
            # Limit CPU time to 2 seconds
            resource.setrlimit(resource.RLIMIT_CPU, (int(timeout_sec), int(timeout_sec) + 1))
        except Exception:
            # Platform specific fallback
            pass

    status = "SUCCESS"
    stdout_text = ""
    stderr_text = ""
    exit_code = 0

    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", code_string],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=set_child_resource_limits
        )

        stdout_text, stderr_text = proc.communicate(input=stdin_data, timeout=timeout_sec)
        exit_code = proc.returncode

        if exit_code != 0:
            status = "RUNTIME_ERROR"

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        status = "TIME_LIMIT_EXCEEDED"
        exit_code = 137  # SIGKILL convention
        stderr_text = f"Execution timed out after {timeout_sec:.1f} seconds."

    except Exception as e:
        status = "INTERNAL_ERROR"
        stderr_text = str(e)
        exit_code = -1

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Protect against output flood attacks:
    if len(stdout_text) > MAX_OUTPUT_BYTES:
        stdout_text = stdout_text[:MAX_OUTPUT_BYTES] + "\n...[OUTPUT TRUNCATED: Exceeded 10KB Limit]"

    return {
        "status": status,
        "exit_code": exit_code,
        "execution_time_ms": elapsed_ms,
        "stdout": stdout_text,
        "stderr": stderr_text
    }


def print_test_case(title: str, code: str, stdin: str = ""):
    print("=" * 60)
    print(f"TEST: {title}")
    print("-" * 60)
    result = run_sandboxed_code(code, stdin)
    print(json.dumps(result, indent=2))
    print()


if __name__ == "__main__":
    print("\n--- REMOTE CODE EXECUTION ENGINE SANDBOX SIMULATION ---\n")

    # Test 1: Normal harmless code
    print_test_case(
        "1. Valid Python Algorithm (Fibonacci)",
        """
def fib(n):
    return n if n <= 1 else fib(n-1) + fib(n-2)
print("Fibonacci(10) =", fib(10))
"""
    )

    # Test 2: Infinite loop (Should trigger watchdog kill in 2.0s)
    print_test_case(
        "2. Malicious Infinite Loop (Timeout Test)",
        """
print("Starting infinite loop...")
while True:
    pass
"""
    )

    # Test 3: Output flooding (Infinite print statements)
    print_test_case(
        "3. Output Flood Attack (Truncation Test)",
        """
for i in range(1000):
    print("Spamming stdout line", i)
"""
    )

    # Test 4: Memory hog (Allocating huge array)
    print_test_case(
        "4. Memory Hog Attack (Exceeding 128MB RAM)",
        """
print("Attempting to allocate 200MB...")
# Allocating a large list
large_array = [0] * (50 * 10**6)
print("Allocated successfully!")
"""
    )
