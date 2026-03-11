#!/usr/bin/env python3
"""Chain exploration script — discovers event types, field names, and API shapes.

Run this FIRST before building the main ingestion loop.
Saves samples to docs/chain-samples/ for reference.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

WORLD_API = "https://blockchain-gateway-nova.nursery.reitnorf.com"
SUI_RPC = "https://fullnode.mainnet.sui.io:443"
SAMPLE_DIR = Path("docs/chain-samples")


async def explore_world_api(client: httpx.AsyncClient) -> None:
    """Hit all known World API endpoints and save responses."""
    endpoints = {
        "smartassemblies": "/smartassemblies",
        "characters": "/characters",
        "solarsystems": "/solarsystems",
        "types": "/types",
        "killmails": "/killmails",
    }

    print("\n=== EVE Frontier World API ===")
    print(f"Base: {WORLD_API}\n")

    for name, path in endpoints.items():
        url = f"{WORLD_API}{path}"
        try:
            resp = await client.get(url, timeout=30)
            print(f"  {name}: HTTP {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                sample_path = SAMPLE_DIR / f"world_{name}.json"

                # Save first few items as sample
                if isinstance(data, dict) and "data" in data:
                    items = data["data"][:3]
                    metadata = data.get("metadata", {})
                    sample = {"data": items, "metadata": metadata}
                    print(f"    Items: {len(data['data'])}, Metadata: {metadata}")
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


async def explore_sui_rpc(client: httpx.AsyncClient) -> None:
    """Attempt Sui RPC connection and discover capabilities."""
    print("\n=== Sui RPC ===")
    print(f"URL: {SUI_RPC}\n")

    # Check connectivity
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sui_getLatestCheckpointSequenceNumber",
        }
        resp = await client.post(SUI_RPC, json=payload, timeout=30)
        data = resp.json()
        print(f"  Latest checkpoint: {data.get('result')}")
        (SAMPLE_DIR / "sui_checkpoint.json").write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"  Checkpoint query failed: {e}")

    # Try querying recent events
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "suix_queryEvents",
            "params": [{"All": []}, None, 5, True],
        }
        resp = await client.post(SUI_RPC, json=payload, timeout=30)
        data = resp.json()
        events = data.get("result", {}).get("data", [])
        print(f"  Recent events: {len(events)}")
        if events:
            sample_path = SAMPLE_DIR / "sui_events_sample.json"
            sample_path.write_text(json.dumps(events[:3], indent=2))
            print(f"    Saved: {sample_path}")
            for evt in events[:3]:
                print(f"    Type: {evt.get('type', 'unknown')}")
                print(f"    Tx: {evt.get('id', {}).get('txDigest', 'unknown')}")
    except Exception as e:
        print(f"  Event query failed: {e}")

    # Get node info
    try:
        payload = {"jsonrpc": "2.0", "id": 3, "method": "rpc.discover"}
        resp = await client.post(SUI_RPC, json=payload, timeout=30)
        data = resp.json()
        methods = [m.get("name", "") for m in data.get("result", {}).get("methods", [])]
        print(f"  Available RPC methods: {len(methods)}")
        if methods:
            (SAMPLE_DIR / "sui_methods.json").write_text(json.dumps(sorted(methods), indent=2))
            print(f"    Saved: {SAMPLE_DIR / 'sui_methods.json'}")
    except Exception as e:
        print(f"  RPC discovery failed: {e}")


async def explore_pyrope(client: httpx.AsyncClient) -> None:
    """Check Pyrope Explorer API availability."""
    pyrope_base = "https://pyrope.nursery.reitnorf.com"
    print("\n=== Pyrope Explorer ===")
    print(f"URL: {pyrope_base}\n")

    try:
        resp = await client.get(pyrope_base, timeout=30, follow_redirects=True)
        print(f"  Status: {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('content-type', 'unknown')}")
    except Exception as e:
        print(f"  Connection failed: {e}")


async def main() -> None:
    """Run all chain exploration."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    print("MONOLITH — Chain Explorer")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        await explore_world_api(client)
        await explore_sui_rpc(client)
        await explore_pyrope(client)

    print("\n" + "=" * 60)
    print(f"Samples saved to {SAMPLE_DIR}/")
    print("Review samples before building ingestion loop.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
