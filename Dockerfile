# Dockerfile
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir hatch

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Build wheel
RUN hatch build -t wheel

# Production image
FROM python:3.11-slim

WORKDIR /app

# Optional Tailscale (userspace networking — no --privileged/NET_ADMIN needed).
# Only used when TS_AUTHKEY is set at runtime (see entrypoint.sh); harmless
# otherwise. Because tailscaled manages its own state/socket, this image runs
# as root rather than a non-root user — same tradeoff fitness-tracker-mcp
# makes for its Tailscale-sidecar-in-container MCP image on this homelab.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg \
       -o /usr/share/keyrings/tailscale-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/debian trixie main" \
       > /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends tailscale \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/lib/tailscale /var/run/tailscale

# Copy wheel from builder
COPY --from=builder /app/dist/*.whl ./

# Install the package
RUN pip install --no-cache-dir *.whl && rm *.whl

# One-time HEB OAuth login helper (docker compose exec texas-grocery-mcp
# python scripts/heb_oauth_login.py start) — no Playwright/Chromium needed.
COPY scripts/heb_oauth_login.py ./scripts/heb_oauth_login.py

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import texas_grocery_mcp; print('ok')" || exit 1

# Default environment
ENV LOG_LEVEL=INFO
ENV ENVIRONMENT=production

ENTRYPOINT ["/entrypoint.sh"]
