import json
import os

import psycopg
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.prompts import Message
from fastmcp.server.transforms import PromptsAsTools
# Load database environment credentials
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

mcp = FastMCP("Simple-PostgreSQL")


@mcp.tool()
def query_db(sql_query: str) -> str:
    """Run a safe SELECT SQL query on the PostgreSQL database."""
    # Validate connection string is configured
    if not DB_URL:
        return "Error: DATABASE_URL environment variable is not set."

    # Safety check: block write/structural queries
    forbidden = {"insert", "update", "delete", "drop", "alter", "truncate", "create"}
    first_word = sql_query.strip().split(None, 1)[0].lower() if sql_query.strip() else ""
    if first_word in forbidden:
        return "Error: Only read-only SELECT queries are allowed."

    # Connect, run query, and format output
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_query)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]
                return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return f"Database error: {str(e)}"

@mcp.prompt
def analyze_schema() -> str:
    """Generate a prompt to explore the current database schema."""
    return (
        "You are connected to a PostgreSQL database. "
        "List all tables and their columns by running:\n\n"
        "SELECT table_name, column_name, data_type\n"
        "FROM information_schema.columns\n"
        "WHERE table_schema = 'public'\n"
        "ORDER BY table_name, ordinal_position;"
    )

@mcp.prompt
def explain_query(task: str) -> str:
    """Generate a prompt that guides the LLM to write a safe SELECT query for a given task."""
    return (
        f"Write a safe read-only SELECT query for the following task:\n\n{task}\n\n"
        "Rules:\n"
        "- Use only SELECT statements (no INSERT, UPDATE, DELETE, DROP, ALTER)\n"
        "- Use the analyze_schema prompt first to discover available tables and columns\n"
        "- Use LIMIT to cap results (default 100, start with 10 when exploring)\n"
        "- If you need to search text content, use similarity_search instead of WHERE with LIKE"
    )

# Add the transform - creates list_prompts and get_prompt tools
mcp.add_transform(PromptsAsTools(mcp))

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)