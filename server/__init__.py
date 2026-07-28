import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.transforms import ResourcesAsTools

# Load database environment credentials
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

mcp = FastMCP("Simple-PostgreSQL")

mcp.add_transform(ResourcesAsTools(mcp))


def run():
    """Start the MCP server."""
    mcp.run(transport="http", host="0.0.0.0", port=8000)