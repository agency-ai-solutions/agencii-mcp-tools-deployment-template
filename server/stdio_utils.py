import os
import json
import asyncio
import subprocess

from pydantic import Field
from agency_swarm import BaseTool

# Global registry for stdio MCP processes
mcp_processes = []


def create_stdio_mcp_tool(
    name: str, description: str, input_schema: dict, mcp_process_name: str
):
    """Create a dynamic BaseTool class for stdio MCP tools"""
    # Create the async run method
    async def run_method(self, **kwargs) -> str:
        """Execute the tool by sending JSON-RPC to the stdio MCP process"""

        # FastMCP passes field values as instance attributes, not in kwargs
        call_args = {}
        for field_name in input_schema.get("properties", {}):
            if hasattr(self, field_name):
                field_value = getattr(self, field_name)
                if field_value is not None:
                    call_args[field_name] = field_value

        # Also include any kwargs passed directly (backup)
        call_args.update(kwargs)

        # Find the MCP process
        mcp_process = None
        for proc_info in mcp_processes:
            if proc_info["name"] == mcp_process_name:
                mcp_process = proc_info["process"]
                break

        if not mcp_process:
            return f"Error: MCP process '{mcp_process_name}' not found"

        # Prepare JSON-RPC request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": call_args},
        }

        try:
            # Send request
            request_str = json.dumps(request) + "\n"
            mcp_process.stdin.write(request_str.encode())
            mcp_process.stdin.flush()

            # Read response with timeout
            response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, mcp_process.stdout.readline
                ),
                timeout=30.0,
            )

            response = json.loads(response_line.decode().strip())

            if "error" in response:
                return f"Error: {response['error']}"

            # Extract result
            result = response.get("result", {})
            if isinstance(result, dict):
                return result.get("content", str(result))
            return str(result)

        except asyncio.TimeoutError:
            return "Error: Tool execution timed out"
        except Exception as e:
            return f"Error executing tool: {str(e)}"

    # Create tool class attributes from input schema
    tool_attrs = {"run": run_method, "__doc__": description}
    annotations = {}

    # Add fields from input schema
    if input_schema and "properties" in input_schema:
        from typing import Optional

        for field_name, field_def in input_schema["properties"].items():
            # Determine field type from schema
            field_type_str = field_def.get("type", "string")
            if field_type_str == "integer":
                field_type = int
            elif field_type_str == "number":
                field_type = float
            elif field_type_str == "boolean":
                field_type = bool
            else:
                field_type = str

            field_description = field_def.get("description", "")
            is_required = field_name in input_schema.get("required", [])

            # Create the field with proper type annotation
            if is_required:
                annotations[field_name] = field_type
                tool_attrs[field_name] = Field(..., description=field_description)
            else:
                annotations[field_name] = Optional[field_type]
                tool_attrs[field_name] = Field(None, description=field_description)

    # Add type annotations
    tool_attrs["__annotations__"] = annotations

    # Create the dynamic class
    return type(name, (BaseTool,), tool_attrs)


async def load_stdio_mcp_tools(group_by_server=False):
    """Load stdio MCP tools from mcp config file and start their processes"""
    mcp_config_path = os.getenv("MCP_CONFIG_PATH", None)

    if not mcp_config_path:
        return {} if group_by_server else []

    if not os.path.exists(mcp_config_path):
        print(f"No mcp config file found at {mcp_config_path}")
        return {} if group_by_server else []

    try:
        with open(mcp_config_path, "r") as f:
            mcp_config = json.load(f)
    except Exception as e:
        print(f"Error reading mcp config file: {e}")
        return {} if group_by_server else []

    stdio_tools = []
    tools_by_server = {}

    for server_name, server_config in mcp_config.get("mcpServers", {}).items():
        command = server_config.get("command")
        args = server_config.get("args", [])
        env = server_config.get("env", {})

        if not command:
            print(f"No command specified for MCP server '{server_name}'")
            continue

        try:
            # Start the MCP process
            process = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                shell=True if os.name == "nt" else False,  # Use shell on Windows
                env={**os.environ, **env},
            )

            # Check if process started successfully
            if process.poll() is not None:
                stderr_output = process.stderr.read().decode()
                raise Exception(
                    f"Process failed to start. Exit code: {process.returncode}. Stderr: {stderr_output}"
                )

            # Store process info
            mcp_processes.append(
                {
                    "name": server_name,
                    "process": process,
                    "command": command,
                    "args": args,
                }
            )

            # Initialize the MCP server
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "fastmcp-bridge", "version": "1.0.0"},
                },
            }

            init_str = json.dumps(init_request) + "\n"
            process.stdin.write(init_str.encode())
            process.stdin.flush()

            # Read initialization response
            init_response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, process.stdout.readline),
                timeout=10.0,
            )
            init_response_raw = init_response_line.decode().strip()

            if not init_response_raw:
                # Check stderr for error messages
                stderr_data = (
                    process.stderr.read(1024).decode()
                    if process.stderr.readable()
                    else "No stderr data"
                )
                raise Exception(
                    f"Empty response from MCP server. Stderr: {stderr_data}"
                )

            # Send notifications/initialized
            notif_request = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            notif_str = json.dumps(notif_request) + "\n"
            process.stdin.write(notif_str.encode())
            process.stdin.flush()

            # Get available tools
            tools_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
            tools_str = json.dumps(tools_request) + "\n"
            process.stdin.write(tools_str.encode())
            process.stdin.flush()

            # Read tools response
            tools_response_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, process.stdout.readline),
                timeout=10.0,
            )
            tools_response = json.loads(tools_response_line.decode().strip())

            server_tools = []
            if "result" in tools_response and "tools" in tools_response["result"]:
                tools_list = tools_response["result"]["tools"]
                print(
                    f"Found {len(tools_list)} tools in '{server_name}': {[t['name'] for t in tools_list]}"
                )

                # Create StdioMCPTool instances
                for tool_def in tools_list:
                    tool_class = create_stdio_mcp_tool(
                        name=tool_def["name"],
                        description=tool_def.get("description", ""),
                        input_schema=tool_def.get("inputSchema", {}),
                        mcp_process_name=server_name,
                    )
                    stdio_tools.append(tool_class)
                    server_tools.append(tool_class)
            else:
                print(
                    f"[ERROR] No tools found in '{server_name}' response: {tools_response}"
                )

            if group_by_server:
                tools_by_server[server_name] = server_tools

        except Exception as e:
            print(f"Error starting MCP server '{server_name}': {e}")
            if group_by_server:
                tools_by_server[server_name] = []
            continue

    print(
        f"Loaded {len(stdio_tools)} stdio MCP tools from {len(mcp_processes)} processes"
    )
    return tools_by_server if group_by_server else stdio_tools