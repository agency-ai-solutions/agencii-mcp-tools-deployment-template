import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import express from "express";
import { createProxyMiddleware } from "http-proxy-middleware";
/* -------------------------------------------------
 *  Load mcp.json
 * -------------------------------------------------*/
const MCP_JSON_PATH = path.resolve(process.cwd(), "mcp.json");
if (!fs.existsSync(MCP_JSON_PATH)) {
    throw new Error(`mcp.json not found at ${MCP_JSON_PATH}. Create one with the format: 
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "mcp-server"],
      "env": { "API_KEY": "value" }
    }
  }
}`);
}
const rawJson = fs.readFileSync(MCP_JSON_PATH, "utf-8");
let config;
try {
    config = JSON.parse(rawJson);
}
catch (err) {
    throw new Error(`Invalid JSON in mcp.json: ${err.message}`);
}
if (!config.mcpServers || Object.keys(config.mcpServers).length === 0) {
    throw new Error("mcp.json contains no servers under `mcpServers`.");
}
/* -------------------------------------------------
 *  Prepare server definitions
 * -------------------------------------------------*/
const servers = Object.entries(config.mcpServers).map(([name, spec]) => {
    const cmdParts = [spec.command, ...(spec.args ?? [])];
    return {
        name: name.toLowerCase(),
        cmdString: cmdParts.join(" "),
        env: spec.env ?? {}
    };
});
/* -------------------------------------------------
 *  Config
 * -------------------------------------------------*/
const BASE_INTERNAL_PORT = parseInt(process.env.BASE_INTERNAL_PORT ?? "8100", 10);
const PORT = parseInt(process.env.PORT ?? "8080", 10);
const PYTHON_SERVER_PORT = parseInt(process.env.PYTHON_SERVER_PORT ?? "8000", 10);
const app = express();
/* -------------------------------------------------
 *  Detect and configure MCP instances
 * -------------------------------------------------*/
// Function to get MCP subdirectories in tools directory
// By convention, we use folders with "_mcp" suffix, but any folder name can be used
function getToolsSubdirectories() {
    const toolsDir = path.resolve(process.cwd(), "tools");
    if (!fs.existsSync(toolsDir)) {
        console.warn(`Tools directory not found at ${toolsDir}`);
        return [];
    }
    
    // In a real production environment, you might want to filter based on your naming convention
    // Here we're showing an example with "_mcp" suffix, but the code accepts any directory
    return fs.readdirSync(toolsDir, { withFileTypes: true })
        .filter(dirent => dirent.isDirectory())
        .map(dirent => dirent.name);
}

// Get all MCP instances to run
const mcpInstances = [];

// Check if we should run a specific MCP instance
const specificToolsDir = process.env.MCP_TOOLS_DIR;
const specificInstanceName = process.env.MCP_INSTANCE_NAME || "default";

if (specificToolsDir) {
    // Run only the specified instance
    mcpInstances.push({
        name: specificInstanceName,
        toolsDir: specificToolsDir,
        port: PYTHON_SERVER_PORT
    });
} else {
    // Default behavior: run the main tools directory
    mcpInstances.push({
        name: "default",
        toolsDir: "./tools",
        port: PYTHON_SERVER_PORT
    });
    
    // Auto-discover and add MCP instances from subdirectories
    const subDirs = getToolsSubdirectories();
    let portOffset = 1;
    
    subDirs.forEach(dir => {
        mcpInstances.push({
            name: dir,
            toolsDir: `./tools/${dir}`,
            port: PYTHON_SERVER_PORT + portOffset
        });
        portOffset++;
    });
}

/* -------------------------------------------------
 *  Launch Python MCP servers
 * -------------------------------------------------*/
const pythonChildren = mcpInstances.map(instance => {
    console.log(`Starting MCP instance: ${instance.name} (${instance.toolsDir}) on port ${instance.port}`);
    
    const child = spawn("python", ["server/start_mcp.py"], {
        stdio: "inherit",
        env: { 
            ...process.env,
            MCP_TOOLS_DIR: instance.toolsDir,
            MCP_INSTANCE_NAME: instance.name,
            MCP_PORT: instance.port.toString()
        },
        cwd: process.cwd()
    });
    
    child.on("exit", code => console.error(`Python MCP server (${instance.name}) exited with code ${code ?? "unknown"}`));
    child.on("error", err => console.error(`Failed to start Python MCP server (${instance.name}): ${err.message}`));
    
    return { child, instance };
});

/* -------------------------------------------------
 *  Track child processes for cleanup
 * -------------------------------------------------*/
const childProcesses = pythonChildren.map(pc => pc.child);

/* -------------------------------------------------
 *  Launch Supergateway for each server
 * -------------------------------------------------*/
servers.forEach((srv, idx) => {
    const gatewayPort = BASE_INTERNAL_PORT + idx;
    const sgArgs = [
        "-y",
        "supergateway",
        "--stdio",
        srv.cmdString,
        "--port",
        gatewayPort.toString(),
        "--baseUrl",
        `http://localhost:${gatewayPort}/${srv.name}`,
        "--ssePath",
        "/sse",
        "--messagePath",
        "/message",
        "--logLevel",
        "none"
    ];
    const childEnv = { ...process.env, ...srv.env };
    const child = spawn("npx", sgArgs, { stdio: "inherit", env: childEnv });
    childProcesses.push(child);
    child.on("exit", code => console.error(`Supergateway for ${srv.name} exited with code ${code ?? "unknown"}`));
    child.on("error", err => console.error(`Failed to start supergateway for ${srv.name}: ${err.message}`));
    /* Reverse proxy mapping */
    app.use(`/${srv.name}`, createProxyMiddleware({
        target: `http://localhost:${gatewayPort}`,
        changeOrigin: true,
        pathRewrite: p => p.replace(`/${srv.name}`, ""),
        ws: true
    }));
});

/* -------------------------------------------------
 *  Set up proxies for MCP instances
 * -------------------------------------------------*/
mcpInstances.forEach(instance => {
    if (instance.name === "default") {
        // Default instance gets root paths
        app.use(createProxyMiddleware({
            target: `http://localhost:${instance.port}`,
            changeOrigin: true,
            ws: true,
            context: (pathname) => pathname.startsWith('/sse')
        }));
        
        app.use(createProxyMiddleware({
            target: `http://localhost:${instance.port}`,
            changeOrigin: true,
            context: (pathname) => pathname.startsWith('/messages')
        }));
    } else {
        // Other instances get prefixed paths
        app.use(`/${instance.name}`, createProxyMiddleware({
            target: `http://localhost:${instance.port}`,
            changeOrigin: true,
            pathRewrite: p => p.replace(`/${instance.name}`, ""),
            ws: true
        }));
    }
});

/* -------------------------------------------------
 *  Cleanup on exit
 * -------------------------------------------------*/
process.on("SIGINT", () => {
    console.log("\nShutting down servers...");
    childProcesses.forEach(child => {
        if (child && !child.killed) {
            child.kill();
        }
    });
    process.exit(0);
});

process.on("SIGTERM", () => {
    childProcesses.forEach(child => {
        if (child && !child.killed) {
            child.kill();
        }
    });
    process.exit(0);
});

/* -------------------------------------------------
 *  Info endpoint
 * -------------------------------------------------*/
app.get("/", (_, res) => res.json({
    status: "ok",
    mcpInstances: mcpInstances.map(instance => {
        if (instance.name === "default") {
            return {
                name: instance.name,
                sse: "/sse",
                message: "/messages",
                description: "Default Python MCP server for local tools",
                toolsDir: instance.toolsDir
            };
        } else {
            return {
                name: instance.name,
                sse: `/${instance.name}/sse`,
                message: `/${instance.name}/messages`,
                description: `Python MCP server for ${instance.name} tools`,
                toolsDir: instance.toolsDir
            };
        }
    }),
    servers: servers.map(s => ({
        name: s.name,
        sse: `/${s.name}/sse`,
        message: `/${s.name}/message`
    }))
}));

app.listen(PORT, () => {
    console.log(`✅ Multi-MCP proxy running on :${PORT}`);
    
    // Log MCP instances
    mcpInstances.forEach(instance => {
        if (instance.name === "default") {
            console.log(`• Default MCP: /sse | /messages (${instance.toolsDir} on port ${instance.port})`);
        } else {
            console.log(`• ${instance.name} MCP: /${instance.name}/sse | /${instance.name}/messages (${instance.toolsDir} on port ${instance.port})`);
        }
    });
    
    // Log other servers
    servers.forEach(s => {
        console.log(`• ${s.name}: /${s.name}/sse | /${s.name}/message`);
    });
});
