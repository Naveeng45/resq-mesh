"""Runtime configuration, loaded from environment variables and a local .env.

Values are read (in order of precedence) from real environment variables, then
from a ``.env`` file in the project root. The ``.env`` file is git-ignored — put
secrets like authenticated Carto endpoint tokens there.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

# Standard OpenStreetMap raster tiles: keyless, and clear enough to read the
# simulated meal-site geography under the markers. Carto's basemaps.cartocdn.com
# CDN now stamps unauthenticated tiles with "API KEY REQUIRED", so it can no
# longer be the default; set CARTO_TILE_URL to a Carto style if you hold a key.
DEFAULT_CARTO_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_ATTRIBUTION = "© OpenStreetMap contributors · positions simulated"
FREE_CARTO_HOST = "basemaps.cartocdn.com"
_AUTH_QUERY_KEYS = frozenset({"api_key", "apikey", "access_token", "token", "key"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Optional. Only used when CARTO_TILE_URL contains an ``{apiKey}`` placeholder
    # (authenticated Carto Maps / custom tile endpoints). Free basemaps ignore this.
    carto_api_key: str = ""
    carto_tile_url: str = DEFAULT_CARTO_TILE_URL
    carto_attribution: str = DEFAULT_ATTRIBUTION


settings = Settings()


def _strip_auth_query_params(url: str) -> str:
    """Remove api_key / access_token query params that break free Carto tiles."""

    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _AUTH_QUERY_KEYS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def carto_tile_config() -> dict:
    """Build the tile-layer config the frontend consumes.

    Free Carto basemaps on ``basemaps.cartocdn.com`` are keyless. Appending an
    ``api_key`` / JWT query param makes Carto serve tiles stamped
    **"API Key Required"** — which looks like a broken key even when ``.env``
    has a valid token. We therefore:

    1. Inject the key ONLY when the URL explicitly contains ``{apiKey}``.
    2. Strip any auth query params from free basemap CDN URLs.
    """

    url = (settings.carto_tile_url or "").strip() or DEFAULT_CARTO_TILE_URL
    key = settings.carto_api_key.strip().strip('"').strip("'")

    if key and "{apiKey}" in url:
        url = url.replace("{apiKey}", key)

    if FREE_CARTO_HOST in url:
        url = _strip_auth_query_params(url)
        # Placeholder left unresolved on a free basemap would also break tiles.
        url = url.replace("{apiKey}", "")

    style = "voyager" if "voyager" in url else "osm" if "openstreetmap.org" in url else "custom"
    return {
        "tileUrl": url,
        "attribution": settings.carto_attribution,
        "style": style,
        "requiresKey": "{apiKey}" in (settings.carto_tile_url or ""),
    }
