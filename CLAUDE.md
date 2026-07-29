# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP server (`fastmcp`) that lets an LLM shop H-E-B groceries: search products, manage cart, clip coupons, check curbside pickup slots and order history. It talks to HEB's unofficial GraphQL/Next.js APIs — there's no official public API, so most of the interesting code deals with authentication and anti-bot evasion, not grocery logic.

This is a maintained fork of `mgwalkerjr95/texas-grocery-mcp` (via `nick-pape/texas-grocery-mcp`); both upstreams are unmaintained. All repo metadata and links now point at `Haub100/texas-grocery-mcp` — keep it that way. There is deliberately no `upstream` git remote, and `gh` is pinned to this fork via `remote.origin.gh-resolved`, so PRs never target a parent repo by accident; don't re-add an upstream remote. The fork attribution in `README.md` and the historical release links in `CHANGELOG.md` are intentional and should stay.

## Commands

```bash
# Install
pip install -e ".[dev]"
playwright install chromium

# Tests
pytest tests/ -v
pytest tests/unit/test_cart_tools.py -v            # single file
pytest tests/unit/test_cart_tools.py::test_name -v # single test
pytest tests/ --cov=src/texas_grocery_mcp --cov-report=html

# Lint / typecheck (both must pass before a PR)
ruff check src/ tests/
ruff check src/ tests/ --fix
mypy src/        # strict mode

# Run the server directly
python -m texas_grocery_mcp.server   # or: texas-grocery-mcp (installed script)

# Docker
docker-compose up --build
```

`tests/integration/` hits the real HEB API and requires a live session — don't run it assuming it's hermetic like `tests/unit/`.

## Architecture

### Two parallel auth paths to the same GraphQL surface

This is the single most important thing to understand before touching `clients/graphql.py` or `auth/`.

1. **Legacy web-session path** (`auth/session.py`, `auth/browser_refresh.py`): cookies + a `reese84` Incapsula anti-bot token captured via a real/headless browser (Playwright), stored in `~/.texas-grocery-mcp/auth.json` (Playwright `storageState` format). Requests go to `www.heb.com` and are subject to Incapsula's WAF. The `reese84` token expires roughly every 11 minutes and must be kept warm; it's also bound to a specific browser User-Agent (`utils/config.get_browser_user_agent()` reads `<auth_dir>/browser_ua.txt` if present) — a UA mismatch silently kills renewal. `server.py`'s `_reese84_keepwarm_loop` proactively refreshes this in the background with exponential backoff on failure (refreshing on a fixed cadence into a "hot" flagged account prolongs the lockout — don't undo that backoff).

2. **Mobile OAuth/bearer path** (`auth/oauth.py`) — the preferred, durable path. One-time interactive OAuth2 PKCE login against `accounts.heb.com` (a separate host, not Incapsula-gated) yields a bearer access token + long-lived refresh token, stored as `tokens.json` next to `auth.json`. Bearer calls go to HEB's mobile GraphQL edge (`MOBILE_GRAPHQL_ENDPOINT` in `clients/graphql.py`) using hardcoded mobile persisted-query hashes (`MOBILE_OPS`) that are back-compat-stable because HEB can't break old app installs. Refreshing the access token is a cheap HTTP call (`oauth.ensure_access_token`), no browser needed.

`auth/session.is_authenticated()` checks bearer tokens *first* and treats their presence as authenticated regardless of cookie/reese84 state — bearer takes precedence over the legacy path everywhere (see also `auto_refresh_session_if_needed`, which short-circuits entirely when tokens.json exists). `clients/graphql.py` methods check `self._bearer_available()` and route to `_*_bearer()` variants when possible, falling back to the SSR/cookie path otherwise. When adding a new HEB operation, prefer wiring the bearer/mobile path if the operation exists there; only fall back to the web SSR path for things the mobile API doesn't expose.

The one-time OAuth login (needed to produce `tokens.json`) has no Playwright dependency — it's a copy/paste PKCE flow via `scripts/heb_oauth_login.py` (`start` prints an auth URL, `finish <redirect-url>` exchanges the code). Preferred on resource-constrained hosts since it avoids running headless Chromium for reese84 keep-warm entirely.

### Server transport (this MCP's own auth, not HEB's)

Don't confuse this with the HEB auth above — it's about how *clients connect to this server*, not how this server talks to HEB. `server.py` runs stdio by default (local MCP clients: Claude Desktop, Claude Code). Setting `MCP_HTTP_MODE=true` switches to streamable-HTTP with OAuth (`transports.py`), for remote clients like claude.ai custom connectors. `transports.SimpleOAuthProvider` is a single-pre-configured-client, auto-approved, in-memory-token OAuth provider (fastmcp's `auth=` mechanism) — appropriate because network access is already gated by Tailscale, not because it's a real multi-tenant OAuth server. This container only speaks plain HTTP; TLS termination and public exposure are handled outside it (e.g. `tailscale serve`/`funnel` in front of `MCP_HTTP_PORT`).

### Persisted-query hash self-healing

HEB's web GraphQL uses Apollo persisted queries (`DEFAULT_PERSISTED_QUERIES` in `clients/graphql.py`) identified by sha256 hash. HEB rotates these when they ship new frontend code, breaking hardcoded hashes. `HashStore` wraps the dict-like lookup and, on a `PersistedQueryNotFound` response, triggers `_try_self_heal()`: it drives a headless Playwright page load (or, for mutations like cart/coupon/store-change that don't fire passively, a scripted interaction — see `MUTATION_FLOWS` in `clients/hash_rediscover.py`) to observe the new hash, then persists the override to `hash_overrides.json` (sibling of `auth.json`) so future process starts don't need to rediscover it. This only applies to the legacy web path; mobile hashes are hardcoded and assumed stable.

### State and request flow

- `state.py`'s `StateManager` holds a process-wide singleton `HEBGraphQLClient` plus a default store ID. Store ID resolution: request-scoped override (`contextvars`) → shared default → error. `HEB_DEFAULT_STORE` env var seeds the shared default at startup (`server.py` lifespan) so bearer-only setups (no web session to infer a store from) work out of the box.
- `tools/*.py` are the MCP-registered functions (thin wrappers around `HEBGraphQLClient` methods + `StateManager`), registered in `server.py` with explicit `readOnlyHint`/`destructiveHint` annotations. Destructive tools (cart_add, coupon_clip, reserve_curbside_slot) require a `confirm=True` param for human-in-the-loop safety — preserve that pattern for new destructive tools.
- `reliability/` provides `CircuitBreaker`, `Throttler`, `TTLCache`, and `with_retry` — `HEBGraphQLClient` wraps essentially every outbound call in throttling + circuit breaker + retry. Product details are cached 24h via `TTLCache` since they rarely change.
- Product search tries authenticated SSR first (query variations, then typeahead-guided retries, then plain typeahead as a last resort), recording each attempt in `ProductSearchAttempt` for diagnostics — this attempt trail is surfaced back to the caller, not just logged, so preserve it when modifying search logic.

### Security-challenge detection

`_detect_security_challenge()` scans response HTML for Incapsula/WAF markers. When a challenge is detected mid-search, the code fails fast (stops trying more query variations) rather than burning retries against a blocked session, and returns Playwright-based manual-recovery instructions to the caller instead of raw data.

## Conventions

- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
- Full type hints everywhere; `mypy --strict` must pass.
- `ruff` line length 100; rule set `E, F, I, N, W, UP, B, C4, SIM`.
- Unit tests use `respx` to mock HTTP rather than hitting HEB; keep new tests hermetic and put anything needing a real session under `tests/integration/`.
