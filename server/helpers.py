"""Shared utility functions used across the MCP server tools and resources."""


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
    import json

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