# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

# Install git and other system dependencies
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy Python requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir uv

# Copy all application files
COPY . .

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

# Ensure the .cache/uv directory exists for the app user
RUN mkdir -p /home/app/.cache/uv && \
    chown -R app:app /home/app/.cache

# Switch to non-root user
USER app

# Expose port 8080 (main proxy port)
EXPOSE 8080

# Command to run the Python MCP server with split subdirectories
CMD ["python", "server/start_mcp.py", "--split-subdirs"]
