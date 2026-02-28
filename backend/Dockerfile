# ── Stage 1: clone PathOfBuilding (api-stdio fork) ──────────────────────────
FROM debian:bookworm-slim AS pob-clone

# Install git for the shallow clone
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Shallow clone (depth 1) to keep the image small while still getting all
# the necessary Lua source files and data assets.
RUN git clone --depth=1 \
        --branch api-stdio \
        https://github.com/ianderse/PathOfBuilding.git \
        /pob


# ── Stage 2: application runtime ─────────────────────────────────────────────
FROM python:3.12-slim

# Install system dependencies:
#   luajit  — LuaJIT 2.1 runtime for the PoB headless engine
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        luajit \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python dependency installation
RUN pip install uv --no-cache-dir

# Copy PathOfBuilding source from the clone stage
COPY --from=pob-clone /pob /pob

# Apply local patches to the PoB source tree.
# BuildOps.lua is patched to expose minion DPS stats (MinionTotalDPS etc.)
# for summoner/minion builds where the player's own TotalDPS is always 0.
COPY patches/BuildOps.lua /pob/src/API/BuildOps.lua

# PoB engine environment — picked up by Settings.pob_src_dir
ENV POB_SRC_DIR=/pob/src

# Set working directory for the Python application
WORKDIR /app

# Copy dependency manifests first to maximise layer-cache reuse
COPY pyproject.toml uv.lock ./

# Install production dependencies
RUN uv sync --no-dev --frozen

# Copy application source
COPY app/ ./app/

# Expose the API port
EXPOSE 8000

# Health-check via the /health/ready readiness probe (checks DB + LuaJIT pool)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready')"

# Run the application using uvicorn
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
