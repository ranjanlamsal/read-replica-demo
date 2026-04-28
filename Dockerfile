FROM python:3.11-slim

WORKDIR /app

# postgresql-client  → pg_isready (used in init-replica.sh)
# curl               → uv installer
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --python 3.11

COPY . .
