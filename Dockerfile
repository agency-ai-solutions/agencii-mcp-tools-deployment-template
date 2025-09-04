# Use Python base image
FROM python:3.12-slim

# Install Node.js and npm (use LTS version)
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application
COPY . .

# Expose port
EXPOSE 8080

# Start the server
CMD ["python", "server/start_mcp.py"]