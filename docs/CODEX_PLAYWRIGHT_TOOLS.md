# Codex Playwright Tools

This is currently a WSL2 machine-local setup for Alex's main workstation. It
is not yet guaranteed on other servers.

The goal is to keep browser automation as a shared Codex tool on each machine
instead of reinstalling Playwright per project. Other servers should add their
own Playwright MCP registration and browser cache/tool path before relying on
this workflow.

## Playwright MCP

Official Playwright MCP server entry:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

Use MCP for browser interaction through accessibility snapshots. Use normal
Chromium screenshots for pixel-level visual QA.

Useful variants:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--headless"]
    }
  }
}
```

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--caps=vision,pdf,devtools"]
    }
  }
}
```

## Local Browser Binary

On this WSL2 machine only, Playwright browsers are already cached under:

```bash
~/.cache/ms-playwright/
```

Known working Chromium screenshot command on this WSL2 machine:

```bash
/home/alex_mercer/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome \
  --headless=new \
  --no-sandbox \
  --disable-gpu \
  --hide-scrollbars \
  --window-size=2667,1500 \
  --screenshot=/absolute/output.png \
  file:///absolute/index.html
```

Prefer this direct Chromium path when the Playwright CLI fails inside Codex
sandboxing with `sandbox_host_linux.cc` errors.

## Codex Tools Environment

`~/.venvs/codex-tools` is the shared Python environment for Codex helper
scripts. Put reusable image QA and browser helper scripts here or in this
`agent-tools` repo, then call them from project-local workflows.

Project-local repos should not vendor Playwright just to take screenshots.
They should call the shared browser/MCP entry and keep only their task-specific
QA thresholds and crop definitions locally.
