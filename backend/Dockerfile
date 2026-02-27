FROM python:3.12-slim

# Install uv for fast dependency installation
RUN pip install uv --no-cache-dir

# Set working directory
WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install production dependencies
RUN uv sync --no-dev --frozen

# Copy application source
COPY app/ ./app/

# Expose the API port
EXPOSE 8000

# Run the application using uvicorn
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
