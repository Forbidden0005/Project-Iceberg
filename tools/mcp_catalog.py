"""
MCP Server Catalog — curated list of useful MCP servers for Penguin.

Each entry includes:
- name: Server identifier
- display_name: Human-readable name
- description: What it does
- command: Executable to run
- args: Command-line arguments
- env: Environment variables needed (with placeholders)
- requires_api_key: Whether user must provide an API key
- api_key_field: Name of the env var that needs the key
- api_key_label: Human-readable label for the key input
"""

MCP_CATALOG = [
    {
        "name": "filesystem",
        "display_name": "📁 Filesystem",
        "description": "Local file operations — read, write, list directories",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:\\"],
        "env": {},
        "requires_api_key": False,
    },
    {
        "name": "memory",
        "display_name": "🧠 Memory",
        "description": "Knowledge graph — persistent memory across sessions",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": {},
        "requires_api_key": False,
    },
    {
        "name": "fetch",
        "display_name": "🌐 Fetch",
        "description": "Web content fetching and conversion for efficient LLM usage",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-fetch"],
        "env": {},
        "requires_api_key": False,
    },
    {
        "name": "github",
        "display_name": "🐙 GitHub",
        "description": "GitHub repo management — search code, create issues, manage PRs",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "your-github-token"},
        "requires_api_key": True,
        "api_key_field": "GITHUB_PERSONAL_ACCESS_TOKEN",
        "api_key_label": "GitHub Personal Access Token",
    },
    {
        "name": "postgres",
        "display_name": "🐘 PostgreSQL",
        "description": "Read-only database access with schema inspection",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
        "env": {},
        "requires_api_key": True,
        "api_key_field": "CONNECTION_STRING",
        "api_key_label": "PostgreSQL Connection String (postgresql://user:pass@host/db)",
    },
    {
        "name": "sqlite",
        "display_name": "💾 SQLite",
        "description": "Local database — lightweight SQL database for local storage",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sqlite", "./data.db"],
        "env": {},
        "requires_api_key": False,
    },
    {
        "name": "puppeteer",
        "display_name": "🤖 Puppeteer",
        "description": "Browser automation — headless Chrome for web scraping",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "env": {},
        "requires_api_key": False,
    },
    {
        "name": "sequential-thinking",
        "display_name": "🧩 Sequential Thinking",
        "description": "Reasoning augmentation — extended chain-of-thought for complex problems",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "env": {},
        "requires_api_key": False,
    },
    {
        "name": "time",
        "display_name": "⏰ Time",
        "description": "Time and timezone conversion capabilities",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-time"],
        "env": {},
        "requires_api_key": False,
    },
    {
        "name": "slack",
        "display_name": "💬 Slack",
        "description": "Slack workspace integration — send messages, read channels",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "xoxb-your-bot-token", "SLACK_TEAM_ID": "your-team-id"},
        "requires_api_key": True,
        "api_key_field": "SLACK_BOT_TOKEN",
        "api_key_label": "Slack Bot Token (xoxb-...)",
    },
    {
        "name": "google-drive",
        "display_name": "📂 Google Drive",
        "description": "Cloud storage — access and manage Google Drive files",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gdrive"],
        "env": {},
        "requires_api_key": False,  # Uses OAuth
    },
]


def get_catalog():
    """Return the full MCP catalog."""
    return MCP_CATALOG


def get_server_config(server_name: str):
    """Get config for a specific server by name."""
    for entry in MCP_CATALOG:
        if entry["name"] == server_name:
            return entry
    return None
