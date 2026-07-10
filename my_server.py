import json
import os

import psycopg
from dotenv import load_dotenv
from fastmcp import FastMCP

# Load database environment credentials
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

mcp = FastMCP("Simple-PostgreSQL")


@mcp.tool(
    name="select_records",
    description="""This tool lets you run SQL queries on a connected PostgreSQL database.

Use it for:
- Looking up records by ID, status, date ranges, or specific column values
- Running calculations like COUNT, SUM, AVG, or GROUP BY
- Joining multiple tables
- Sorting or filtering data
- Accessing transaction data, user records, system logs

Do NOT use it for:
- Natural language / semantic search — use similarity_search instead
- Finding topics, themes, or concepts in text — use similarity_search instead

Good examples:
- "How many orders were placed last week?"
- "Show all users with status = 'active'"
- "Average order value grouped by region"

Bad examples:
- "Find documents about database performance" → use similarity_search
- "Show tickets related to connection issues" → use similarity_search

Important: Results are capped. Use LIMIT parameter (default 100, start with 10 when exploring).""",
)
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


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)