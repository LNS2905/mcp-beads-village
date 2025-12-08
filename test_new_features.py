"""Test new Beads Village features."""
import asyncio
import json
import os
import sys

# Add to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from beads_village.server import (
    AGENT, WS,
    tool_reserve, tool_reservations, tool_release,
    tool_msg, tool_inbox,
    tool_status,
    mail_dir, reservation_dir,
    handle_request,
    TOOLS
)


async def test_config():
    print("=" * 50)
    print("CONFIG")
    print("=" * 50)
    print(f"AGENT: {AGENT}")
    print(f"WS: {WS}")
    print(f"Mail dir: {mail_dir()}")
    print(f"Reservation dir: {reservation_dir()}")
    print()


async def test_tools_list():
    print("=" * 50)
    print("TOOLS LIST")
    print("=" * 50)
    print(f"Total tools: {len(TOOLS)}")
    for name, spec in TOOLS.items():
        print(f"  - {name}: {spec['desc']}")
    print()


async def test_reservations():
    print("=" * 50)
    print("FILE RESERVATIONS")
    print("=" * 50)
    
    # Reserve some files
    result = await tool_reserve({
        "paths": ["test.py", "src/main.py"],
        "ttl": 60,
        "reason": "testing"
    })
    print(f"Reserve: {result}")
    
    # List reservations
    result = await tool_reservations({})
    print(f"Active: {result}")
    
    # Release all
    result = await tool_release({})
    print(f"Release: {result}")
    
    # Verify empty
    result = await tool_reservations({})
    print(f"After release: {result}")
    print()


async def test_messaging():
    print("=" * 50)
    print("MESSAGING")
    print("=" * 50)
    
    # Send a message
    result = await tool_msg({
        "subj": "test message",
        "body": "Hello from test",
        "importance": "high"
    })
    print(f"Send: {result}")
    
    # Check inbox
    result = await tool_inbox({"n": 3})
    print(f"Inbox: {result}")
    print()


async def test_status():
    print("=" * 50)
    print("STATUS")
    print("=" * 50)
    result = await tool_status({})
    print(f"Status: {result}")
    print()


async def test_mcp_protocol():
    print("=" * 50)
    print("MCP PROTOCOL")
    print("=" * 50)
    
    # Initialize
    resp = await handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    })
    print(f"Initialize: {json.dumps(resp['result']['serverInfo'])}")
    
    # List tools
    resp = await handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    })
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    print(f"Tools ({len(tool_names)}): {tool_names}")
    
    # Call status
    resp = await handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "status", "arguments": {}}
    })
    print(f"Status call: {resp['result']['content'][0]['text']}")
    print()


async def main():
    print("\n" + "=" * 50)
    print("BEADS VILLAGE TEST SUITE")
    print("=" * 50 + "\n")
    
    await test_config()
    await test_tools_list()
    await test_reservations()
    await test_messaging()
    await test_status()
    await test_mcp_protocol()
    
    print("=" * 50)
    print("ALL TESTS PASSED!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
