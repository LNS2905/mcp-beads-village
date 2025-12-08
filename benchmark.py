"""Benchmark Beads Village MCP performance (no bd CLI required)."""
import time
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from beads_village.server import (
    tool_reserve, tool_release, tool_reservations,
    tool_msg, tool_inbox,
    handle_request, normalize_path, to_posix_path
)


async def run_benchmark():
    print("=" * 60)
    print("BEADS VILLAGE - PERFORMANCE BENCHMARK")
    print("=" * 60)
    print()
    
    results = []
    
    # Test 1: Path normalization (CPU bound)
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        normalize_path("src/components/auth/login.py")
    elapsed = (time.perf_counter() - start) * 1000
    results.append(("normalize_path", iterations, elapsed))
    print(f"normalize_path x{iterations}: {elapsed:.2f}ms total, {elapsed/iterations:.4f}ms each")
    
    # Test 2: to_posix_path
    iterations = 10000
    start = time.perf_counter()
    for _ in range(iterations):
        to_posix_path("src\\components\\auth\\login.py")
    elapsed = (time.perf_counter() - start) * 1000
    results.append(("to_posix_path", iterations, elapsed))
    print(f"to_posix_path x{iterations}: {elapsed:.2f}ms total, {elapsed/iterations:.4f}ms each")
    
    # Test 3: Reserve files (I/O bound - atomic file creation)
    iterations = 20
    start = time.perf_counter()
    for i in range(iterations):
        await tool_reserve({"paths": [f"benchmark/file_{i}.py"], "ttl": 60})
    elapsed = (time.perf_counter() - start) * 1000
    results.append(("reserve", iterations, elapsed))
    print(f"reserve x{iterations}: {elapsed:.2f}ms total, {elapsed/iterations:.2f}ms each")
    
    # Cleanup reservations
    await tool_release({})
    
    # Test 4: Send messages (I/O bound)
    iterations = 20
    start = time.perf_counter()
    for i in range(iterations):
        await tool_msg({"subj": f"benchmark_{i}", "body": "test message body"})
    elapsed = (time.perf_counter() - start) * 1000
    results.append(("msg", iterations, elapsed))
    print(f"msg x{iterations}: {elapsed:.2f}ms total, {elapsed/iterations:.2f}ms each")
    
    # Test 5: Read inbox (I/O bound - file listing + JSON parsing)
    iterations = 20
    start = time.perf_counter()
    for _ in range(iterations):
        await tool_inbox({"n": 10})
    elapsed = (time.perf_counter() - start) * 1000
    results.append(("inbox", iterations, elapsed))
    print(f"inbox x{iterations}: {elapsed:.2f}ms total, {elapsed/iterations:.2f}ms each")
    
    # Test 6: List reservations
    iterations = 50
    start = time.perf_counter()
    for _ in range(iterations):
        await tool_reservations({})
    elapsed = (time.perf_counter() - start) * 1000
    results.append(("reservations", iterations, elapsed))
    print(f"reservations x{iterations}: {elapsed:.2f}ms total, {elapsed/iterations:.2f}ms each")
    
    # Test 7: MCP protocol - tools/list
    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        await handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    elapsed = (time.perf_counter() - start) * 1000
    results.append(("tools/list", iterations, elapsed))
    print(f"tools/list x{iterations}: {elapsed:.2f}ms total, {elapsed/iterations:.2f}ms each")
    
    # Test 8: MCP protocol - initialize
    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        await handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    elapsed = (time.perf_counter() - start) * 1000
    results.append(("initialize", iterations, elapsed))
    print(f"initialize x{iterations}: {elapsed:.2f}ms total, {elapsed/iterations:.2f}ms each")
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for name, iters, elapsed in results:
        avg = elapsed / iters
        ops_per_sec = iters / (elapsed / 1000) if elapsed > 0 else float('inf')
        status = "OK" if avg < 50 else "SLOW"
        print(f"{name:20s}: {avg:8.3f}ms avg, {ops_per_sec:8.0f} ops/sec [{status}]")
    
    print()
    print("All benchmarks completed.")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
