FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required by psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY my_server.py .
COPY .env .env

# Expose the MCP server port
EXPOSE 8000

# Run the MCP server
CMD ["python", "my_server.py"]