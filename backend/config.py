"""Monolith configuration — all settings from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Database
    database_path: str = "monolith.db"

    # EVE Frontier World API
    world_api_base: str = "https://blockchain-gateway-nova.nursery.reitnorf.com"
    world_api_timeout: int = 30

    # Sui RPC
    sui_rpc_url: str = "https://fullnode.mainnet.sui.io:443"
    sui_rpc_timeout: int = 30

    # Polling intervals (seconds)
    world_poll_interval: int = 300  # 5 minutes
    snapshot_interval: int = 900  # 15 minutes
    detection_interval: int = 300  # 5 minutes

    # Anthropic API (for LLM narration only)
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5-20250514"

    # Discord webhooks
    discord_webhook_url: str = ""
    discord_rate_limit: int = 5  # max messages per minute

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    model_config = {"env_prefix": "MONOLITH_", "env_file": ".env"}


def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
