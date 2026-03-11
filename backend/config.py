"""Monolith configuration — all settings from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Database
    database_path: str = "monolith.db"

    # EVE Frontier World API (stillness environment — only live gateway)
    world_api_base: str = "https://blockchain-gateway-stillness.live.tech.evefrontier.com"
    world_api_timeout: int = 30

    # Chain RPC — currently OP Sepolia (chain ID 11155420), will migrate to Sui
    chain_rpc_url: str = "https://op-sepolia-ext-sync-node-rpc.live.tech.evefrontier.com"
    chain_rpc_timeout: int = 30

    # World contract address (OP Sepolia MUD)
    world_contract: str = "0x1dacc0b64b7da0cc6e2b2fe1bd72f58ebd37363c"

    # GraphQL indexer (MUD state queries)
    graphql_url: str = "https://graphql-stillness-internal.live.evefrontier.tech/v1/graphql"

    # Sui RPC (for when migration happens)
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
