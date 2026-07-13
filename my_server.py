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

@mcp.tool()
def get_schema(table_name: str = "") -> str:
    """Discover the column names, data types, and nullability for tables in the public schema. Use this first to understand what columns and data types are available before writing queries."""
    if not DB_URL:
        return "Error: DATABASE_URL environment variable is not set."

    schema_query = (
        "SELECT table_name, column_name, data_type, is_nullable, character_maximum_length\n"
        "FROM information_schema.columns\n"
        "WHERE table_schema = 'public'"
    )
    if table_name:
        schema_query += f" AND table_name = '{table_name}'"
    schema_query += "\nORDER BY table_name, ordinal_position;"

    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(schema_query)
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]

                # Group by table_name for readability
                tables = {}
                for row in rows:
                    tbl = row["table_name"]
                    tables.setdefault(tbl, []).append(
                        {
                            "column": row["column_name"],
                            "type": row["data_type"],
                            "nullable": row["is_nullable"],
                            "max_length": row["character_maximum_length"],
                        }
                    )

                output_lines = []
                for tbl, cols in tables.items():
                    output_lines.append(f"\n=== {tbl} ===")
                    for col in cols:
                        max_len = col["max_length"]
                        type_str = f"{col['type']}({max_len})" if max_len else col["type"]
                        null_str = "NULL" if col["nullable"] == "YES" else "NOT NULL"
                        output_lines.append(f"  {col['column']:30s} {type_str:20s} {null_str}")

                return "\n".join(output_lines) if output_lines else "No tables found in public schema."
    except Exception as e:
        return f"Database error: {str(e)}"

@mcp.tool()
def search_db(keywords: str, table_name: str = "", limit: int = 10) -> str:
    """Search all text/character columns across the database for records matching the given keywords. Use this when you need to find records by topic or description, not for structured lookups (use query_db for those)."""
    if not DB_URL:
        return "Error: DATABASE_URL environment variable is not set."
    if not keywords.strip():
        return "Error: keywords parameter is required."

    # Step 1: discover all text columns in public schema
    schema_query = (
        "SELECT table_name, column_name\n"
        "FROM information_schema.columns\n"
        "WHERE table_schema = 'public'\n"
        "  AND data_type IN ('character varying', 'varchar', 'text', 'character', 'char', 'name', 'citext')"
    )
    if table_name:
        schema_query += f" AND table_name = '{table_name}'"
    schema_query += "\nORDER BY table_name, ordinal_position;"

    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(schema_query)
                text_columns = cur.fetchall()  # list of (table_name, column_name)

                if not text_columns:
                    return "No text columns found to search."

                # Step 2: build a UNION query searching each column
                like_pattern = f"%{keywords}%"
                union_parts = []
                for tbl, col in text_columns:
                    safe_tbl = tbl.replace("'", "''")
                    safe_col = col.replace("'", "''")
                    union_parts.append(
                        f"SELECT '{safe_tbl}' AS table_name, '{safe_col}' AS column_name, "
                        f'"{safe_col}"::text AS matched_value, '
                        f"'{safe_tbl}.{safe_col}' AS location\n"
                        f"FROM \"{safe_tbl}\"\n"
                        f"WHERE \"{safe_col}\"::text ILIKE '{like_pattern}'\n"
                    )

                if not union_parts:
                    return "No searchable columns found."

                full_query = " UNION ALL ".join(union_parts) + f"\nLIMIT {limit};"

                cur.execute(full_query)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]

                if not results:
                    return f"No records found matching '{keywords}'."

                return json.dumps(results, indent=2, default=str)
    except Exception as e:
        return f"Database error: {str(e)}"

@mcp.prompt
def housing_units_owner_occupied() -> str:
    """Show top 5 housing units where owner_occupied is true."""
    return "query the following  information 'Show top 5 housing units where owner_occupied is true.'using mcp tool query_db"

@mcp.prompt
def geoheader_area_type_is_OA() -> str:
    """Show top 10 geoheader records where area_type is OA."""
    return "query the following  information 'Show top 10 geoheader records where area_type is OA.'using mcp tool query_db"

# Add the transform - creates list_prompts and get_prompt tools
mcp.add_transform(PromptsAsTools(mcp))

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)