#!/usr/bin/env python3
"""Chain exploration script — discovers event types, field names, and API shapes.

Run this FIRST before building the main ingestion loop.
Saves samples to docs/chain-samples/ for reference.

Current state (March 2026):
- World API: stillness environment on OP Sepolia (chain ID 11155420)
- Sui migration in progress but NOT live yet
- GraphQL indexer available for MUD state queries
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

WORLD_API = "https://blockchain-gateway-stillness.live.tech.evefrontier.com"
CHAIN_RPC = "https://op-sepolia-ext-sync-node-rpc.live.tech.evefrontier.com"
GRAPHQL = "https://graphql-stillness-internal.live.evefrontier.tech/v1/graphql"
WORLD_CONTRACT = "0x1dacc0b64b7da0cc6e2b2fe1bd72f58ebd37363c"
SAMPLE_DIR = Path("docs/chain-samples")


async def explore_world_api(client: httpx.AsyncClient) -> None:
    """Hit all known World API v2 endpoints and save responses."""
    # First check health
    print("\n=== EVE Frontier World API ===")
    print(f"Base: {WORLD_API}\n")

    try:
        resp = await client.get(f"{WORLD_API}/health", timeout=15)
        print(f"  Health: {resp.json()}")
    except Exception as e:
        print(f"  Health check failed: {e}")
        return

    # Get config for chain details
    try:
        resp = await client.get(f"{WORLD_API}/config", timeout=15)
        config = resp.json()
        sample_path = SAMPLE_DIR / "world_config.json"
        sample_path.write_text(json.dumps(config, indent=2))
        print(f"  Config saved: {sample_path}")
        if isinstance(config, dict):
            chain_id = config.get("chainId", config.get("chain_id", "unknown"))
            print(f"  Chain ID: {chain_id}")
    except Exception as e:
        print(f"  Config fetch failed: {e}")

    # V2 endpoints
    endpoints = {
        "smartassemblies": "/v2/smartassemblies",
        "smartcharacters": "/v2/smartcharacters",
        "solarsystems": "/v2/solarsystems",
        "types": "/v2/types",
        "killmails": "/v2/killmails",
        "tribes": "/v2/tribes",
        "fuels": "/v2/fuels",
    }

    for name, path in endpoints.items():
        url = f"{WORLD_API}{path}"
        try:
            resp = await client.get(url, timeout=30)
            print(f"\n  {name}: HTTP {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                sample_path = SAMPLE_DIR / f"world_{name}.json"

                if isinstance(data, dict) and "data" in data:
                    items = data["data"][:3]
                    metadata = data.get("metadata", {})
                    sample = {"data": items, "metadata": metadata}
                    total = metadata.get("total", len(data["data"]))
                    print(f"    Total: {total}, Metadata: {metadata}")
                    if items:
                        print(f"    Fields: {list(items[0].keys())}")
                elif isinstance(data, list):
                    items = data[:3]
                    sample = items
                    print(f"    Items: {len(data)}")
                    if items:
                        print(f"    Fields: {list(items[0].keys())}")
                else:
                    sample = data
                    print(f"    Type: {type(data).__name__}")

                sample_path.write_text(json.dumps(sample, indent=2))
                print(f"    Saved: {sample_path}")
            else:
                print(f"    Body: {resp.text[:200]}")
        except Exception as e:
            print(f"  {name}: ERROR — {e}")

    # Try fetching a single assembly detail
    try:
        resp = await client.get(f"{WORLD_API}/v2/smartassemblies", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            if items and len(items) > 0:
                first_id = items[0].get(
                    "id", items[0].get("address", items[0].get("smartAssemblyId", ""))
                )
                if first_id:
                    detail_resp = await client.get(
                        f"{WORLD_API}/v2/smartassemblies/{first_id}", timeout=30
                    )
                    if detail_resp.status_code == 200:
                        detail = detail_resp.json()
                        (SAMPLE_DIR / "world_assembly_detail.json").write_text(
                            json.dumps(detail, indent=2)
                        )
                        print(f"\n  Assembly detail saved (ID: {first_id})")
                        if isinstance(detail, dict):
                            print(f"    Detail fields: {list(detail.keys())}")
    except Exception as e:
        print(f"\n  Assembly detail fetch failed: {e}")


async def explore_chain_rpc(client: httpx.AsyncClient) -> None:
    """Check OP Sepolia RPC connectivity and get chain state."""
    print("\n\n=== Chain RPC (OP Sepolia) ===")
    print(f"URL: {CHAIN_RPC}\n")

    # eth_chainId
    try:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}
        resp = await client.post(CHAIN_RPC, json=payload, timeout=15)
        data = resp.json()
        chain_id = int(data.get("result", "0x0"), 16)
        print(f"  Chain ID: {chain_id}")
        (SAMPLE_DIR / "chain_id.json").write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"  eth_chainId failed: {e}")

    # eth_blockNumber
    try:
        payload = {"jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []}
        resp = await client.post(CHAIN_RPC, json=payload, timeout=15)
        data = resp.json()
        block_num = int(data.get("result", "0x0"), 16)
        print(f"  Latest block: {block_num}")
    except Exception as e:
        print(f"  eth_blockNumber failed: {e}")

    # Get recent logs from world contract
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "eth_getLogs",
            "params": [
                {
                    "address": WORLD_CONTRACT,
                    "fromBlock": "latest",
                    "toBlock": "latest",
                }
            ],
        }
        resp = await client.post(CHAIN_RPC, json=payload, timeout=30)
        data = resp.json()
        logs = data.get("result", [])
        print(f"  Logs in latest block: {len(logs)}")
        if logs:
            (SAMPLE_DIR / "chain_logs_sample.json").write_text(json.dumps(logs[:5], indent=2))
            print(f"    Saved: {SAMPLE_DIR / 'chain_logs_sample.json'}")
            # Show unique topics
            topics = set()
            for log_entry in logs:
                if log_entry.get("topics"):
                    topics.add(log_entry["topics"][0])
            print(f"    Unique event topics: {len(topics)}")
            for topic in list(topics)[:5]:
                print(f"      {topic}")
    except Exception as e:
        print(f"  eth_getLogs failed: {e}")


async def explore_graphql(client: httpx.AsyncClient) -> None:
    """Query the MUD GraphQL indexer for table schema."""
    print("\n\n=== GraphQL Indexer (MUD) ===")
    print(f"URL: {GRAPHQL}\n")

    # Introspection query — get available tables
    introspection = {
        "query": """
        {
          __schema {
            queryType {
              fields {
                name
                description
              }
            }
          }
        }
        """
    }
    try:
        resp = await client.post(GRAPHQL, json=introspection, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            fields = data.get("data", {}).get("__schema", {}).get("queryType", {}).get("fields", [])
            print(f"  Available query fields: {len(fields)}")
            (SAMPLE_DIR / "graphql_schema.json").write_text(json.dumps(fields, indent=2))
            print(f"    Saved: {SAMPLE_DIR / 'graphql_schema.json'}")
            for f in fields[:20]:
                print(f"    {f['name']}: {f.get('description', '')[:60]}")
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  GraphQL introspection failed: {e}")


async def main() -> None:
    """Run all chain exploration."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    print("MONOLITH — Chain Explorer")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        await explore_world_api(client)
        await explore_chain_rpc(client)
        await explore_graphql(client)

    print("\n" + "=" * 60)
    print(f"Samples saved to {SAMPLE_DIR}/")
    print("Review samples before building ingestion loop.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
