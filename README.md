# MCP Tools Deployment Template 

A template for quickly creating and deploying your own MCP servers. It allows you to:

1. Quickly create completely custom MCP server just by chatting with AI IDEs.
2. Add pre-built open source MCP servers to your project from MCP marketplaces.
3. Create multiple MCP instances in separate directories with shared tools.

This template deploys all of them at once on railway in just a few clicks! 

## 🚀 Step-by-Step Guide

### Prerequisites
- Python 3.12+
- Git

## Step 0: Copy Template

Copy this GitHub template by clicking the "Use this template" button on the top right of the page.

## Step 1: Create a Virtual Environment

**In Cursor, Windsur, or VS Code:**

1. Open the Command Palette:
   - On Mac: `Cmd + Shift + P`
   - On Windows: `Ctrl + Shift + P`
2. Type and select: **Python: Select Interpreter**
3. Click: **+ Create Virtual Environment**
4. Choose: **Venv** as the environment type

**In Terminal:**
```bash
python -m venv venv
source venv/bin/activate
```

## Step 2: Create Your Tools 

### 2.1 Create Custom Tools Just by Chatting With AI

Prompt your AI IDE to create the tools for you in chat. **Make sure to include `./.cursor/rules/workflow.mdc`** in the context. (Included by default only in Cursor). 

For example:

```
Please create a tool that fetches the transcripts from a YouTube video. @workflow.mdc
```

Answer the clarifying questions and keep iterating until the tools are created and working as expected.

Make sure to add any requested env variables to the `./.env` file.

### 2.2 Add Pre Build Open Source Stdio MCP Servers

Add other pre-built Open Source Stdio MCP servers to the `mcp.json` file, similarly to Cursor and other clients.

```json
{
  "mcpServers": {
    "notionapi": {
      "command": "npx",
      "args": [
        "-y",
        "@notionhq/notion-mcp-server"
      ],
      "env": {
        "OPENAPI_MCP_HEADERS": "{\"Authorization\":\"Bearer ntn_****\",\"Notion-Version\":\"2022-06-28\"}"
      }
    }
    # ... add more servers here
}
```

**Only `Stdio` servers are supported by this method. This repo will automatically convert them to SSE with [supergateway](https://github.com/supercorp-ai/supergateway).**

You can use both npx and uv to run these servers.

### 2.3 Test the MCP Servers (Optional)

Run the following command to test the MCP servers and ensure all of them are running.

This step is not necessary, since if your tools are working, there should be no issues when deploying.

```bash
npm run start
```

You can't connect local servers to Agencii, but you can test them by adding the SSE URL to Cursor's "MCP Servers" tab.

This step is not necessary. As long as there are no issues in your tools,

## Step 3: Using Multiple MCP Instances

This template supports creating multiple MCP instances in separate directories, with shared tools in the main tools directory.

### Directory Structure

By convention, we recommend using the "_mcp" suffix for MCP instance directories, but any directory name can be used:

```
tools/
├── SharedTool1.py         # Shared across all MCP instances
├── SharedTool2.py         # Shared across all MCP instances
├── marketing_mcp/         # Marketing MCP instance
│   ├── MarketingTool1.py
│   └── MarketingTool2.py
└── analytics_mcp/         # Analytics MCP instance
    ├── AnalyticsTool1.py
    └── AnalyticsTool2.py
```

### Running Specific MCP Instances

To run a specific MCP instance, use the `MCP_TOOLS_DIR` environment variable:

```bash
# Run the marketing MCP instance
MCP_TOOLS_DIR="./tools/marketing_mcp" MCP_INSTANCE_NAME="marketing-mcp" npm run start

# Run the analytics MCP instance
MCP_TOOLS_DIR="./tools/analytics_mcp" MCP_INSTANCE_NAME="analytics-mcp" npm run start
```

This will load all tools from the specified directory AND all tools from the parent tools directory.

### Configuration Options

The MCP server can be configured using environment variables:

- `MCP_TOOLS_DIR`: Path to the tools directory (default: "./tools")
- `MCP_HOST`: Host to bind server to (default: "0.0.0.0")
- `MCP_PORT`: Port to run server on (default: 8000)
- `MCP_INSTANCE_NAME`: Instance name for logging/identification (default: "mcp-server")

These can also be set as command line arguments:

```bash
python server/start_mcp.py --tools-dir ./tools/marketing --port 8001 --name marketing-mcp
```

## Step 4: Deploy to Production

1. Visit [railway.com](https://railway.com).
2. Create a new project and select Deploy from GitHub.
3. Connect and select the GitHub repository you created in step 1.
4. Set the required environment variables (e.g., `MCP_TOOLS_DIR`, `MCP_INSTANCE_NAME`).
5. Click Deploy.

To deploy multiple MCP instances, create multiple services in Railway, each with different environment variables.

In case of issues, you can check logs on railway by clicking on the latest deployment and then clicking on the "Logs" tab.

This template will keep your servers cold, so you are not paying for anything when not using them!


## Step 5: Copy Your Railway Deployment URL

1. Go to Settings > Networking
2. Click "Generate Domain"
3. Select port 8080 if needed
4. Copy the generated URL.

**Your MCP tools from the `tools/` folder will be accessible at:**

```
https://<railway-domain>/sse
```

**Other MCP servers from the `mcp.json` file will be accessible at URLs like:**

```
https://<railway-domain>/notionapi/sse
https://<railway-domain>/example-mcp-server/sse
```

## Step 6: Connect MCP Servers to Agencii

1. Navigate to [Agencii tools page](https://agencii.ai/tools/). 
2. Click "New Tool"
3. Select "MCP"
4. Enter the URLs of your MCP servers
5. Click "Sync Tools"
6. Click "Save"
7. Add your tool to an agent.


We recommend copying this template again and repeating the process for each new project/client.

---

**Happy building! 🚀**

