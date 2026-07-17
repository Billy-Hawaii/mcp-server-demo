import json
import os
from statistics import mean, median, mode, stdev, StatisticsError

import aiofiles
import psycopg
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.prompts import Message
from fastmcp.server.transforms import PromptsAsTools
from fastmcp.server.transforms import ResourcesAsTools
# Load database environment credentials
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

mcp = FastMCP("Simple-PostgreSQL")


def _is_numeric(val):
    """Check if a value is numeric (int or float, including string representations)."""
    if isinstance(val, (int, float)):
        return True
    if isinstance(val, str):
        try:
            float(val)
            return True
        except (ValueError, TypeError):
            return False
    return False


def _parse_json_results(json_str: str) -> list:
    """Parse a JSON string into a list. Accepts arrays or single objects."""
    data = json.loads(json_str)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("Input must be a JSON array of objects or an array of numbers.")
    return data


def _extract_numeric_values(data: list, column: str = "") -> list:
    """Extract numeric values from the parsed data based on column specification."""
    if not data:
        return []

    if column:
        # Specific column requested
        values = []
        for row in data:
            if isinstance(row, dict) and column in row:
                val = row[column]
                if _is_numeric(val):
                    values.append(float(val))
        return values

    # No column specified — check if data is a flat list of numbers
    if not isinstance(data[0], dict):
        values = [float(x) for x in data if _is_numeric(x)]
        return values

    # Auto-detect: find all numeric columns from the first row
    # (the caller should use compute_stats if they want all columns)
    return None  # signal to caller that column is ambiguous


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


@mcp.tool()
def compute_stats(json_results: str, column: str = "") -> str:
    """Compute descriptive statistics (mean, median, mode, range, min, max, std dev, variance, count, sum) from a JSON array of objects (e.g. output of query_db) or a JSON array of numbers.

    - If column is provided, stats are computed on that numeric field from each object.
    - If column is empty and the data is an array of numbers, stats are computed directly.
    - If column is empty and the data is an array of objects, stats are computed on ALL numeric columns found.
    """
    try:
        data = _parse_json_results(json_results)
    except (json.JSONDecodeError, ValueError) as e:
        return f"Error parsing JSON input: {e}"

    if not data:
        return "Error: Input data is empty."

    # Determine if we are analyzing a single column, a flat list, or auto-detecting columns
    if column:
        columns_to_analyze = [column]
    elif not isinstance(data[0], dict):
        # Flat list of numbers
        columns_to_analyze = ["values"]
        # Wrap into a dict format for uniform processing
        data = [{"values": row} if not isinstance(row, dict) else row for row in data]
    else:
        # Auto-detect numeric columns from the first row
        columns_to_analyze = []
        for key in data[0]:
            if _is_numeric(data[0][key]):
                columns_to_analyze.append(key)
        if not columns_to_analyze:
            return "Error: No numeric columns found in the data. Use the 'column' parameter to specify which field to analyze."

    output_parts = []
    for col in columns_to_analyze:
        values = []
        for row in data:
            if isinstance(row, dict) and col in row:
                val = row[col]
                if _is_numeric(val):
                    values.append(float(val))

        if not values:
            output_parts.append(f"\n--- {col} ---\n  (no numeric values found)")
            continue

        n = len(values)
        min_val = min(values)
        max_val = max(values)
        range_val = max_val - min_val
        total = sum(values)
        avg = mean(values)
        med = median(values)

        try:
            mod = mode(values)
        except StatisticsError:
            mod = "N/A (no unique mode)"

        try:
            sd = stdev(values)
        except StatisticsError:
            sd = "N/A (need at least 2 values)"

        try:
            var = sd ** 2 if isinstance(sd, float) else "N/A"
        except TypeError:
            var = "N/A"

        output_parts.append(
            f"\n--- {col} (n={n}) ---\n"
            f"  Mean   : {avg:.6f}\n"
            f"  Median : {med:.6f}\n"
            f"  Mode   : {mod}\n"
            f"  Range  : {range_val:.6f}\n"
            f"  Min    : {min_val:.6f}\n"
            f"  Max    : {max_val:.6f}\n"
            f"  Std Dev: {sd}\n"
            f"  Variance: {var}\n"
            f"  Sum    : {total:.6f}\n"
            f"  Count  : {n}"
        )

    return "\n".join(output_parts)


@mcp.prompt
def housing_units_owner_occupied() -> str:
    """Show top x housing units where owner_occupied is true."""
    return "query the following  information 'Show top {{number}} housing units where owner_occupied is 1.'using mcp tool query_db"


@mcp.prompt
def geoheader_by_area_type() -> str:
    """Show top 10 geoheader records by area_type."""
    return "query the following  information 'Show top 10 geoheader records where area_type is {{type}}.'using mcp tool query_db"




# Add the transform - creates list_prompts and get_prompt tools
mcp.add_transform(PromptsAsTools(mcp))

# @mcp.resource("file:///app/data/census_data_dictionary.csv")
# async def get_census_data_dictionary() -> str:
#     """Provides the Census Data Dictionary in CSV format."""
#     try:
#         async with aiofiles.open("data/census_data_dictionary.csv", mode="r", encoding="utf-8") as f:
#             return await f.read()
#     except FileNotFoundError:
#         return "Error: File not found."

# @mcp.resource("config://app")
# def app_config() -> str:
#     """Application configuration."""
#     return '{"app_name": "My App", "version": "1.0.0"}'

# @mcp.resource("user://{user_id}/profile")
# def user_profile(user_id: str) -> str:
#     """Get a user's profile by ID."""
#     return f'{{"user_id": "{user_id}", "name": "User {user_id}"}}'


# # Add the transform - creates list_resources and read_resource tools
# mcp.add_transform(ResourcesAsTools(mcp))

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)