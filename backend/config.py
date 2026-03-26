"""Monolith configuration — all settings from environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings

# World API base URLs by chain environment
CHAIN_URLS: dict[str, dict[str, str]] = {
    "stillness": {
        "world_api": "https://world-api-stillness.live.tech.evefrontier.com",
        # EVE Frontier "Stillness" runs on Sui testnet despite being the live server
        "sui_rpc": "https://fullnode.testnet.sui.io:443",
    },
    "nova": {
        "world_api": "https://world-api-nova.live.tech.evefrontier.com",
        "sui_rpc": "https://fullnode.testnet.sui.io:443",
    },
}


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Database
    database_path: str = "monolith.db"

    # Chain environment — "stillness" (mainnet/live) or "nova" (testnet/sandbox)
    chain: Literal["stillness", "nova"] = "stillness"

    # World API (static data: solarsystems, types, tribes, /config)
    # Defaults resolved from chain setting if not explicitly set
    world_api_url: str = ""
    world_api_timeout: int = 30

    # Sui chain RPC — defaults resolved from chain setting if not explicitly set
    sui_rpc_url: str = ""
    sui_rpc_timeout: int = 30

    # Sui Move package ID — auto-fetched from /config if not set
    sui_package_id: str = ""

    # Polling intervals (seconds)
    chain_poll_interval: int = 30  # Sui has fast finality
    snapshot_interval: int = 900  # 15 minutes
    detection_interval: int = 300  # 5 minutes
    static_data_interval: int = 3600  # 1 hour for reference data refresh

    # Anthropic API (for LLM narration only)
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5-20250514"

    # Discord webhooks
    discord_webhook_url: str = ""
    discord_rate_limit: int = 5  # max messages per minute

    # GitHub issue auto-filing (CRITICAL anomalies only)
    github_repo: str = ""  # e.g., "AreteDriver/monolith"
    github_token: str = ""

    # NEXUS webhook (WatchTower enriched events)
    nexus_secret: str = ""

    # WatchTower API (intelligence overlay for map)
    watchtower_api_url: str = "https://watchtower-evefrontier.fly.dev/api"
    watchtower_api_timeout: int = 10

    # Admin
    admin_key: str = ""  # Set MONOLITH_ADMIN_KEY for /api/admin/* endpoints

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    model_config = {"env_prefix": "MONOLITH_", "env_file": ".env"}

    def resolve_urls(self) -> None:
        """Fill in default URLs from chain setting if not explicitly provided."""
        chain_defaults = CHAIN_URLS.get(self.chain, CHAIN_URLS["stillness"])
        if not self.world_api_url:
            self.world_api_url = chain_defaults["world_api"]
        if not self.sui_rpc_url:
            self.sui_rpc_url = chain_defaults["sui_rpc"]


def get_settings() -> Settings:
    """Get cached settings instance with resolved URLs."""
    settings = Settings()
    settings.resolve_urls()
    return settings
