import os
import sys
import argparse
import importlib.util
import inspect
import asyncio

from agency_swarm import BaseTool
from agency_swarm.integrations.mcp_server import run_mcp
from starlette.applications import Starlette
from starlette.routing import Mount
from stdio_utils import load_stdio_mcp_tools

# Default configuration
DEFAULT_TOOLS_DIR = "./tools"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080
DEFAULT_INSTANCE_NAME = "mcp-server"
DEFAULT_MCP_INCLUDE_SUBDIRS = "false"
DEFAULT_MCP_SPLIT_SUBDIRS = "false"


def get_config():
    """Get configuration from environment variables with CLI argument overrides"""
    # Read from environment variables first
    tools_dir = os.getenv("MCP_TOOLS_DIR", DEFAULT_TOOLS_DIR)
    host = os.getenv("MCP_HOST", DEFAULT_HOST)
    port = int(os.getenv("MCP_PORT", str(DEFAULT_PORT)))
    instance_name = os.getenv("MCP_INSTANCE_NAME", DEFAULT_INSTANCE_NAME)
    include_subdirs = os.getenv(
        "MCP_INCLUDE_SUBDIRS", DEFAULT_MCP_INCLUDE_SUBDIRS
    ).lower() in ("1", "true", "yes", "y", "on")
    split_subdirs = os.getenv(
        "MCP_SPLIT_SUBDIRS", DEFAULT_MCP_SPLIT_SUBDIRS
    ).lower() in ("1", "true", "yes", "y", "on")

    # Parse command line arguments to override env vars
    parser = argparse.ArgumentParser(
        description="Start MCP server with ALL tools from subdirectories"
    )
    parser.add_argument(
        "--tools-dir",
        "-t",
        default=tools_dir,
        help=f"Path to tools directory (env: MCP_TOOLS_DIR, default: {DEFAULT_TOOLS_DIR})",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=port,
        help=f"Port to run server on (env: MCP_PORT, default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--host",
        default=host,
        help=f"Host to bind server to (env: MCP_HOST, default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--name",
        "-n",
        default=instance_name,
        help="Instance name (env: MCP_INSTANCE_NAME, used for logging/identification)",
    )
    parser.add_argument(
        "--include-subdirs",
        action="store_true",
        default=include_subdirs,
        help="Include tools from subdirectories into the base path (default: false)",
    )
    parser.add_argument(
        "--split-subdirs",
        action="store_true",
        default=split_subdirs,
        help="Serve subdirectories in separate endpoints (default: false)",
    )

    return parser.parse_args()


def setup_python_path():
    """Add the tools directory to Python path for imports"""
    tools_dir = os.path.abspath(DEFAULT_TOOLS_DIR)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)


def load_tools_from_directory(directory, parent_only=False):
    """Load all tool classes from a directory

    Args:
        directory: Directory to load tools from
        parent_only: If True, only load tools from the parent directory, not subdirectories
    """
    tools = []
    loaded_count = 0

    # Ensure directory exists
    if not os.path.exists(directory):
        print(f"Directory does not exist: {directory}")
        return tools

    # Get Python files in the directory
    if parent_only:
        # Only get files in the parent directory
        files = [
            f
            for f in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, f))
            and f.endswith(".py")
            and not f.startswith("__")
        ]

        for file in files:
            file_path = os.path.join(directory, file)
            try:
                # Load the module
                module_name = os.path.splitext(file)[0]
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Find all BaseTool subclasses in the module
                    for name, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, BaseTool)
                            and obj.__module__ == module.__name__
                        ):
                            tools.append(obj)
                            loaded_count += 1
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
    else:
        # Walk through the directory and subdirectories
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    file_path = os.path.join(root, file)
                    try:
                        # Load the module
                        module_name = os.path.splitext(file)[0]
                        spec = importlib.util.spec_from_file_location(
                            module_name, file_path
                        )
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)

                            # Find all BaseTool subclasses in the module
                            for name, obj in inspect.getmembers(module):
                                if (
                                    inspect.isclass(obj)
                                    and issubclass(obj, BaseTool)
                                    and obj.__module__ == module.__name__
                                ):
                                    tools.append(obj)
                                    loaded_count += 1
                    except Exception as e:
                        print(f"Error loading {file_path}: {e}")

    print(f"Loaded {loaded_count} tools from {directory}")
    return tools


def get_tool_subdirectories(tools_dir):
    """Get all subdirectories in the tools directory"""
    subdirs = []
    if os.path.exists(tools_dir):
        for item in os.listdir(tools_dir):
            item_path = os.path.join(tools_dir, item)
            if (
                os.path.isdir(item_path)
                and not item.startswith("__")
                and not item.startswith(".")
            ):
                subdirs.append(item)
    return subdirs


def setup_uvicorn_app():
    """Set up multiple FastMCP apps - one for each subdirectory"""
    setup_python_path()
    config = get_config()

    # List to store all mount routes
    routes = []

    # Prepare base app, but defer mounting to avoid shadowing sub-mounts
    base_app = None
    base_tools = load_tools_from_directory(
        config.tools_dir, parent_only=not (config.include_subdirs)
    )

    if config.include_subdirs or config.split_subdirs:
        stdio_tools = asyncio.run(load_stdio_mcp_tools(group_by_server=config.split_subdirs))
    else:
        stdio_tools = []

    # Add stdio MCP tools to base path
    if config.include_subdirs:
        if config.split_subdirs:
            stdio_tools_list = []
            for server_name, server_tools in stdio_tools.items():
                stdio_tools_list.extend(server_tools)
            base_tools = base_tools + stdio_tools_list
        else:
            base_tools = base_tools + stdio_tools

    if base_tools:
        print(f"Creating base path with {len(base_tools)} tools")
        base_fastmcp = run_mcp(tools=base_tools, return_app=True)
        base_app = base_fastmcp.http_app(stateless_http=True, transport="sse")

    if config.split_subdirs:
        # Create separate apps for each MCP server
        for server_name, server_tools in stdio_tools.items():
            if server_tools:
                print(
                    f"Creating endpoint for stdio MCP server '/{server_name}' with {len(server_tools)} tools"
                )
                server_fastmcp = run_mcp(tools=server_tools, return_app=True)
                server_app = server_fastmcp.http_app(
                    stateless_http=True, transport="sse"
                )
                routes.append(Mount(f"/{server_name}", app=server_app))

        # Get all tool subdirectories
        subdirs = get_tool_subdirectories(config.tools_dir)
        print(f"Found {len(subdirs)} tool subdirectories: {subdirs}")

        # Create separate app for each subdirectory (mount these BEFORE root mount)
        for subdir in subdirs:
            subdir_path = os.path.join(config.tools_dir, subdir)
            subdir_tools = load_tools_from_directory(subdir_path)

            if subdir_tools:
                # Create FastMCP instance for this subdirectory
                subdir_fastmcp = run_mcp(tools=subdir_tools, return_app=True)
                # Create the Starlette app for this subdirectory
                subdir_app = subdir_fastmcp.http_app(
                    stateless_http=True, transport="sse"
                )
                # Mount at the subdirectory path
                routes.append(Mount(f"/{subdir}", app=subdir_app))

    # Finally mount the base app at root to avoid swallowing subpaths
    if base_app is not None:
        routes.append(Mount("/", app=base_app))

    # Create the main Starlette application with all mounted apps
    main_app = Starlette(routes=routes)
    print(
        f"Setup an app with following routes: \n{'\n'.join([mount.path if mount.path != '' else '/' for mount in routes])}"
    )
    return main_app


def main():
    """Main entry point"""
    import uvicorn

    config = get_config()

    # Use PORT environment variable for deployment (Railway, Heroku, etc.)
    deployment_port = int(os.getenv("PORT", str(config.port)))

    print("Starting multi-endpoint MCP server")
    print(f"  Tools directory: {config.tools_dir}")
    print(f"  Host: {config.host}")
    print(f"  Port: {config.port}")
    print(f"  Deployment port (PORT env): {deployment_port}")
    print(f"  Instance name: {config.name}")
    print("  Configuration source: ENV vars + CLI args")

    # Set up the application with multiple endpoints (including stdio MCP tools)
    app = setup_uvicorn_app()

    print(f"\nStarting server on {config.host}:{deployment_port}")

    # Start the server with uvicorn
    uvicorn.run(
        app,
        host=config.host,
        port=deployment_port,  # Use deployment_port, not config.port
        log_level="info",
    )


if __name__ == "__main__":
    main()
