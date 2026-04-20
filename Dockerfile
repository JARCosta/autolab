FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# Repo root so `app.backend.*` and top-level webapp, paths, logging_config resolve.
ENV PYTHONPATH=/app

# System deps for numpy/matplotlib/requests/websocket-client
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        libjpeg-dev \
        libpng-dev \
        zlib1g-dev \
        libfreetype6-dev \
        curl \
        util-linux \
        ca-certificates && \
    curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
        -o /etc/apt/trusted.gpg.d/ngrok.asc && \
    echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
        > /etc/apt/sources.list.d/ngrok.list && \
    apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends ngrok && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN python -m venv /venv && \
    /venv/bin/pip install --upgrade pip && \
    /venv/bin/pip install -r requirements.txt

# Make the venv interpreter the default `python` for any service command.
ENV PATH="/venv/bin:${PATH}"

# Copy app code (excluding .git etc via .dockerignore if present)
COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Optional: run as this UID/GID so files in ./data are owned by your user (default 1000:1000)
ENV AUTOLAB_UID=1000 AUTOLAB_GID=1000

# Expose Flask/ngrok webapp port (only the web service publishes it via compose)
EXPOSE 5000

# Default to the web service; per-service compose entries override this.
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "app.runtime.entrypoint", "web"]

