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
def housing_units_query() -> str:
    """Show top 5 housing units where owner_occupied is true."""
    return "SELECT * FROM housing_units WHERE owner_occupied = TRUE LIMIT 5;"

@mcp.prompt
def geoheader_query() -> str:
    """Show top 10 geoheader records where area_type is OA."""
    return "SELECT * FROM geoheader WHERE area_type = 'OA' LIMIT 10;"

# Add the transform - creates list_prompts and get_prompt tools
mcp.add_transform(PromptsAsTools(mcp))

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)