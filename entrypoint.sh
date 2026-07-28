#!/bin/sh
# When TS_AUTHKEY is set, brings up Tailscale (userspace networking — no
# NET_ADMIN/--privileged needed) inside this same container, registers it
# under TS_HOSTNAME, and (in HTTP mode) enables Funnel on MCP_HTTP_PORT so
# the container is reachable at its own https://<TS_HOSTNAME>.<tailnet>.ts.net
# — a distinct node identity from the host, not exposed via the host's
# network or Tailscale at all. Skipped entirely if TS_AUTHKEY is unset (the
# default stdio/local-only deployment doesn't need any of this).
set -e

if [ -n "${TS_AUTHKEY}" ]; then
  echo "Starting Tailscale (userspace networking)..."
  mkdir -p /var/run/tailscale /var/lib/tailscale

  tailscaled \
    --state=/var/lib/tailscale/tailscaled.state \
    --socket=/var/run/tailscale/tailscaled.sock \
    --tun=userspace-networking &

  TRIES=0
  while [ ! -S /var/run/tailscale/tailscaled.sock ]; do
    sleep 0.2
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -gt 50 ]; then
      echo "ERROR: tailscaled did not start within 10 seconds" >&2
      exit 1
    fi
  done

  echo "Tailscale daemon ready, authenticating..."
  TS_ARGS="--authkey=${TS_AUTHKEY}"
  if [ -n "${TS_HOSTNAME}" ]; then
    TS_ARGS="${TS_ARGS} --hostname=${TS_HOSTNAME}"
  fi
  tailscale --socket=/var/run/tailscale/tailscaled.sock up ${TS_ARGS}

  if [ "${MCP_HTTP_MODE}" = "true" ]; then
    echo "Tailscale connected, enabling Funnel on port ${MCP_HTTP_PORT:-8002}..."
    tailscale --socket=/var/run/tailscale/tailscaled.sock funnel --bg "${MCP_HTTP_PORT:-8002}"
    echo ""
    echo "=========================================="
    tailscale --socket=/var/run/tailscale/tailscaled.sock funnel status 2>/dev/null || true
    echo "=========================================="
    echo ""
  fi
else
  echo "TS_AUTHKEY not set — skipping Tailscale."
fi

exec texas-grocery-mcp
