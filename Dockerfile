# Use Python 3.12 slim image for smaller size
FROM python:3.12-slim

# Install git and other system dependencies
RUN apt-get update && \
    apt-get install -y git curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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

# Copy Node.js package files from root directory
COPY package.json package-lock.json tsconfig.json ./

# Install Node.js dependencies (including dev dependencies for build)
RUN npm ci

# Copy all application files
COPY . .

# Build TypeScript to JavaScript
RUN npm run build

# Copy the rest of the application
COPY tools/ ./tools/
COPY mcp.json ./

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

# Command to run the application
CMD ["npm", "start"]
