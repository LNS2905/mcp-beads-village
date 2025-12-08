"""Debug tool schema generation."""
import asyncio
import json
from beads_village.server import mcp


async def main():
    tools = await mcp._tool_manager.get_tools()
    print(f"Found {len(tools)} tools")
    
    for name, tool in tools.items():
        print(f"\n=== {name} ===")
        print(f"Attributes: {[a for a in dir(tool) if not a.startswith('_')]}")
        
        # Get MCP schema
        mcp_tool = tool.to_mcp_tool()
        schema = mcp_tool.inputSchema
        print(json.dumps(schema, indent=2, default=str))
        
        # Check for problematic types
        if schema:
            props = schema.get("properties", {})
            for prop_name, prop_def in props.items():
                if prop_def.get("type") == "":
                    print(f"  WARNING: Empty type for {prop_name}")
                if "anyOf" in prop_def:
                    print(f"  INFO: anyOf for {prop_name}: {prop_def['anyOf']}")


if __name__ == "__main__":
    asyncio.run(main())
