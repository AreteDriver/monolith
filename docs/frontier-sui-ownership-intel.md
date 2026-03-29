# EVE Frontier — Sui Ownership Transfer Intel
*Harvested from #builder-help / Thread: "Changing asset ownership with Sui" — March 12, 2026*

---

## Confirmed Facts

- **Smart Assembly ownership transfer is possible today via smart contract**, blocked only at UI level — confirmed by CCP Legolas (CCP dev)
- **CCP's intent is to eventually support UI-level transfers** — this is a current gap that third-party tooling could fill
- **Pre-Sui architecture used ERC-721 (NFTs)** for Smart Assemblies — ownership history may be indexable back to that era for Witness Protocol's reputation model

---

## Technical Findings

### The `store` ability is the unlock
`transfer::public_transfer(owner_cap, new_address)` can be called from any module **if** `OwnerCap<T>` has the `store` ability:
```move
struct OwnerCap<T: key> has key, store { ... }
```
The bytecode verifier restriction only applies to `transfer::receive`, which requires `T` to be defined in the calling module. `public_transfer` bypasses this because `store` signals the object is freely transferable.

**Action item:** Confirm `store` is present on `OwnerCap<T>` in the live `access_control.move` contracts before building on this assumption.

### Transfer flow
1. Holder has `OwnerCap<YourAssembly>` as an owned object in their wallet
2. Call `transfer::public_transfer(owner_cap, recipient_address)`
3. Recipient holds the cap and gains all gated permissions
4. The assembly itself doesn't move — only the capability object does

### `transfer::receive` bytecode constraint (documented behavior)
The Sui Move verifier explicitly enforces that `T` in `receive<T>` must be defined in the calling module. This is not a bug — it's canon. Any Witness Protocol / NEXUS module that needs to accept inbound objects must either:
- Own the type definition itself, or
- Rely on CCP exposing a public entry wrapper function

---

## Known Edge Cases / Attack Surface

- **Cross-player Smart Gate linking without mutual consent** was a known problem under ERC-721
- If `OwnerCap` transfer doesn't require acknowledgment from the recipient under Sui, that attack surface **may still exist** — a hostile actor could transfer a cap to an unwilling address and create unauthorized linkage
- Worth monitoring for CCP's mitigation approach; relevant to NEXUS custody model if asset handling is ever in scope

---

## Witness Protocol / Aegis Stack Relevance

- **Ownership transfer events are high-signal** — index them in the chain indexer
- A Storage that changes hands mid-campaign, or a Gate transferred to a hostile corp, is actionable intel
- Pre-Sui ERC-721 ownership history may extend the reputation timeline if CCP preserved that data on-chain
- UI transfer gap = potential future Aegis Stack feature surface

---

*Source: Discord #builder-help, participants: Dystroxic (OP), [TriEx] Hecate, ProtoDroidBot [VANG], CCP Legolas [FRNT]*
