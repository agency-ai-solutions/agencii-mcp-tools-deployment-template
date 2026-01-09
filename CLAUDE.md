# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## MCP Tools Deployment Template

This is a template for deploying MCP (Model Context Protocol) tools and servers. It enables quick creation of custom MCP tools using Agency Swarm framework and deployment to Railway.

## Key Commands

### Development
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Test a specific tool
python tools/ToolName.py

# Start local MCP server (for testing)
npm run start
```

### Deployment
The project auto-deploys to Railway when pushed to GitHub. Local URLs:
- Custom tools: `http://localhost:8080/sse`
- Other MCP servers: `http://localhost:8080/<server-name>/sse`

## Architecture

### Tool Development Framework
- Uses Agency Swarm's `BaseTool` pattern
- All tools go in `tools/` directory with exact class name as filename
- Environment variables loaded via `python-dotenv`
- Each tool must have a test case in `if __name__ == "__main__":`

### MCP Server Structure
- Custom Python tools served via Agency Swarm MCP implementation
- External stdio MCP servers configured in `mcp.json`
- Supergateway converts stdio to SSE format
- Express server proxies requests to appropriate handlers

### Key Files
- `.cursor/rules/workflow.mdc`: Step-by-step tool creation workflow
- `.cursor/rules/PRD.md`: Product Requirements Document (create when building new tools)
- `server/start_mcp.py`: Starts Agency Swarm MCP server for Python tools
- `server/index.js`: Express server handling routing and proxying

## Tool Creation Workflow

When creating new tools, follow the workflow in `.cursor/rules/workflow.mdc`:
1. Create to-do list
2. Gather requirements from user
3. Research APIs and create PRD
4. Setup environment variables in `.env`
5. Develop tools following Agency Swarm pattern
6. Test each tool individually

## Important Conventions

- Never hardcode API keys - use environment variables
- Tools must inherit from `BaseTool` and implement `run()` method
- Always call `load_dotenv()` at module level
- Test tools with `python tools/ToolName.py` before deployment
- Add new dependencies to `requirements.txt`