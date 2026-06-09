import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def fetch_correction_via_mcp(command: str, step_type: str, error_output: str) -> str:
    """
    Connects to the local mcp_server.py to fetch a corrected command.
    Returns the corrected command string.
    """
    # Define the path to the mcp server script
    server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
    
    server_params = StdioServerParameters(
        command=sys.executable, # Use the current python interpreter (venv)
        args=[server_path],
        env=None
    )

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                
                # Call the suggest_correction tool
                result = await session.call_tool(
                    "suggest_correction",
                    arguments={
                        "command": command,
                        "step_type": step_type,
                        "error_output": error_output
                    }
                )
                
                if result and result.content:
                    # Parse the JSON response from the tool
                    response_data = json.loads(result.content[0].text)
                    return response_data.get("corrected_command", command)
                
    except Exception as e:
        print(f"MCP Client Error: {e}")
        
    return command

def get_corrected_command_sync(command: str, step_type: str, error_output: str) -> str:
    """Synchronous wrapper for Flask."""
    return asyncio.run(fetch_correction_via_mcp(command, step_type, error_output))
