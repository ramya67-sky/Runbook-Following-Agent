import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from command_classifier import suggest_corrected_command

app = Server("runbook-remediation-server")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="suggest_correction",
            description="Suggests a corrected command for a failed shell or SQL operation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "step_type": {"type": "string"},
                    "error_output": {"type": "string"}
                },
                "required": ["command", "step_type", "error_output"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "suggest_correction":
        command = arguments.get("command")
        step_type = arguments.get("step_type")
        error_output = arguments.get("error_output")
        
        # Call the existing logic to get the correction
        correction = suggest_corrected_command(command, step_type, error_output)
        
        # We need to extract just the command from the correction format if it has backticks
        import re
        cmd_match = re.search(r'`([^`]+)`', correction)
        clean_command = cmd_match.group(1) if cmd_match else correction.split('\n')[0]
        
        return [TextContent(type="text", text=json.dumps({
            "corrected_command": clean_command,
            "raw_correction": correction
        }))]
    
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
