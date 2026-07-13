import json
import os

import psycopg
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.prompts import Message
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

# Basic prompt returning a string (converted to user message automatically)
@mcp.prompt
def ask_about_topic(topic: str) -> str:
    """Generates a user message asking for an explanation of a topic."""
    return f"Can you please explain the concept of '{topic}'?"

# Prompt returning multiple messages
@mcp.prompt
def generate_code_request(language: str, task_description: str) -> list[Message]:
    """Generates a conversation for code generation."""
    return [
        Message(f"Write a {language} function that performs the following task: {task_description}"),
        Message("I'll help you write that function.", role="assistant"),
    ]

# Basic dynamic resource returning a string
@mcp.resource("resource://greeting")
def get_greeting() -> str:
    """Provides a simple greeting message."""
    return "Hello from FastMCP Resources!"

# Resource returning JSON data
@mcp.resource("data://config")
def get_config() -> str:
    """Provides application configuration as JSON."""
    return json.dumps({
        "theme": "dark",
        "version": "1.2.0",
        "features": ["tools", "resources"],
    })

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)