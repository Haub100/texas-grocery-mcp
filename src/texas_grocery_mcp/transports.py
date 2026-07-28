"""Optional HTTP+OAuth transport for remote MCP clients (e.g. claude.ai custom
connectors), on top of fastmcp's native ``auth=`` support.

Disabled by default — the server runs over stdio for local MCP clients
(Claude Desktop, Claude Code) unless ``MCP_HTTP_MODE=true``. When enabled, a
single pre-configured OAuth 2.1 client (static client_id/secret you hand to
claude.ai's "Add custom connector" dialog) is auto-approved with no consent
screen, matching the single-user/homelab deployment model. Tokens are stored
in-memory only — they reset on restart, which is fine since claude.ai will
just re-run the OAuth flow.

This intentionally does NOT manage TLS, public exposure, or dynamic client
registration. Pair it with a reverse proxy / ``tailscale serve|funnel`` in
front of the plaintext HTTP port for the public HTTPS endpoint.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from dataclasses import dataclass

import structlog
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, OAuthProvider
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

logger = structlog.get_logger()

ACCESS_TOKEN_TTL_SECONDS = 3600
AUTH_CODE_TTL_SECONDS = 600

DEFAULT_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
]


class SimpleOAuthProvider(OAuthProvider):
    """Single pre-configured OAuth client, auto-approved, in-memory tokens.

    Not a general-purpose OAuth server: there's exactly one registered
    client (the one you configure in claude.ai), and every authorization
    request from it is approved without a consent screen. That's
    appropriate here because the *server itself* is already gated by
    Tailscale network access — this OAuth layer exists to satisfy the MCP
    remote-server auth handshake, not to protect a multi-tenant service.
    """

    def __init__(
        self,
        *,
        server_url: str,
        client_id: str,
        client_secret: str,
        redirect_uris: list[str],
    ) -> None:
        super().__init__(base_url=server_url, issuer_url=server_url)
        self._client_id = client_id
        self.client = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=redirect_uris,  # type: ignore[arg-type]
            client_name="Claude",
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="client_secret_post",
            scope="mcp",
        )
        self._authorization_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.client if client_id == self.client.client_id else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise NotImplementedError("Dynamic client registration not supported")

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        code = secrets.token_urlsafe(32)
        self._authorization_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or ["mcp"],
            expires_at=time.time() + AUTH_CODE_TTL_SECONDS,
            client_id=self._client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self._authorization_codes.get(authorization_code)
        if code and code.client_id == client.client_id and time.time() < code.expires_at:
            return code
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self._authorization_codes.pop(authorization_code.code, None)
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        self._access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=self._client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time() + ACCESS_TOKEN_TTL_SECONDS),
            resource=authorization_code.resource,
        )
        self._refresh_tokens[refresh_token] = RefreshToken(
            token=refresh_token,
            client_id=self._client_id,
            scopes=authorization_code.scopes,
            expires_at=None,
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=refresh_token,
            scope=" ".join(authorization_code.scopes),
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        token = self._refresh_tokens.get(refresh_token)
        return token if token and token.client_id == client.client_id else None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        self._refresh_tokens.pop(refresh_token.token, None)
        new_access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        token_scopes = scopes or refresh_token.scopes
        self._access_tokens[new_access] = AccessToken(
            token=new_access,
            client_id=self._client_id,
            scopes=token_scopes,
            expires_at=int(time.time() + ACCESS_TOKEN_TTL_SECONDS),
        )
        self._refresh_tokens[new_refresh] = RefreshToken(
            token=new_refresh,
            client_id=self._client_id,
            scopes=token_scopes,
            expires_at=None,
        )
        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=new_refresh,
            scope=" ".join(token_scopes),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        access_token = self._access_tokens.get(token)
        if access_token and (
            access_token.expires_at is None or time.time() < access_token.expires_at
        ):
            return access_token
        return None

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        else:
            self._refresh_tokens.pop(token.token, None)


@dataclass(frozen=True)
class HttpModeConfig:
    host: str
    port: int
    server_url: str


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def is_http_mode_enabled() -> bool:
    return _env("MCP_HTTP_MODE", "false").lower() == "true"


def build_auth_provider() -> tuple[SimpleOAuthProvider, HttpModeConfig]:
    """Build the OAuth provider + HTTP config from MCP_* env vars.

    Exits the process with a clear message if required config is missing —
    this runs at server startup, before anything else can go wrong.
    """
    server_url = _env("MCP_SERVER_URL").rstrip("/")
    client_secret = _env("MCP_OAUTH_CLIENT_SECRET")

    if not server_url:
        print(
            "ERROR: MCP_SERVER_URL is required when MCP_HTTP_MODE=true "
            "(e.g. https://homelab.your-tailnet.ts.net)",
            file=sys.stderr,
        )
        sys.exit(1)
    if not client_secret:
        print(
            "ERROR: MCP_OAUTH_CLIENT_SECRET is required when MCP_HTTP_MODE=true. "
            "Generate one with: openssl rand -base64 32",
            file=sys.stderr,
        )
        sys.exit(1)

    client_id = _env("MCP_OAUTH_CLIENT_ID", "texas-grocery-mcp")
    raw_uris = _env("MCP_OAUTH_REDIRECT_URIS")
    redirect_uris = (
        [u.strip() for u in raw_uris.split(",") if u.strip()]
        if raw_uris
        else DEFAULT_REDIRECT_URIS
    )

    provider = SimpleOAuthProvider(
        server_url=server_url,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uris=redirect_uris,
    )
    config = HttpModeConfig(
        host=_env("MCP_HTTP_HOST", "127.0.0.1"),
        port=int(_env("MCP_HTTP_PORT", "8000")),
        server_url=server_url,
    )
    logger.info(
        "HTTP+OAuth mode configured",
        server_url=server_url,
        client_id=client_id,
        redirect_uris=redirect_uris,
        host=config.host,
        port=config.port,
    )
    return provider, config


def register_openid_configuration_route(mcp: FastMCP, server_url: str) -> None:
    """Claude.ai probes OIDC discovery in addition to RFC 8414
    oauth-authorization-server metadata; fastmcp's OAuthProvider only
    registers the latter, so add the former by hand.
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    @mcp.custom_route("/.well-known/openid-configuration", methods=["GET"])
    async def openid_configuration(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "issuer": server_url,
                "authorization_endpoint": f"{server_url}/authorize",
                "token_endpoint": f"{server_url}/token",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["client_secret_post"],
            }
        )
