# Solana integration candidate

This branch adds native SOL and classic USDC on mainnet and devnet. All four Solana source
registry entries remain `wallet_only: true`. Token-2022 is represented by protocol
metadata validation but has no public catalog entry while KDF transfer/rent fixes
are pending. Mainnet uses `SOL` and `USDC-SOL`; devnet uses `TESTSOL` and
`TESTUSDC-TESTSOL`. Devnet pricing prefixes are separate from mainnet, and catalog
tickers contain at most one hyphen, following the KDF maintainer's requirement. The generator preserves
Solana tickers exactly, including the `-TESTSOL` platform suffix.

The Solana node source files in `solana/` keep `cluster` and `genesis_hash` scanner
metadata separate from `rpc_nodes`. Generated KDF activation nodes contain only
`url`. These public endpoints are development defaults, not a production provider
selection. Production still needs retained transaction history and browser CORS
validation.

The expected genesis identities are published by Solana Labs:
https://beta.docs.solanalabs.com/clusters/available (Devnet and Mainnet Beta).
The scanner requires matching `getGenesisHash`, `getHealth == "ok"`, and a valid
finalized `getSlot`. Redirects are refused so a configured HTTPS endpoint cannot
downgrade the scan to plain HTTP. Failed identity checks cannot inherit a previous successful
connection timestamp. A normal catalog build includes only verified recent nodes.
SPL tokens inherit their explicit platform's verified nodes. RPC source URLs must
use canonical lowercase `https://`, a valid port, and no userinfo, fragments,
whitespace, control characters or backslashes, so scanners and native/browser
outputs agree on the same endpoint.

## Isolated generated fixtures

From the repository root:

```sh
python3 -B utils/generate_solana_candidate.py
python3 -B -m unittest discover -s utils/tests -v
```

The first command generates only `utils/fixtures/solana/` using the same
`CoinConfig.generate()` path as the full catalog. It does not contact nodes,
refresh unrelated metadata, update production generated snapshots or publish
anything. The manifest explicitly records that nodes were not live-verified.
Use `--verify-nodes` to require live Solana identity/health checks before generating.
The manifest records Solana and UTXO verification separately; reusing the UTXO
snapshot does not claim fresh node validation.

`coins.json` and `coins_config.json` contain all four wallet-only entries.
`swap_coins.json` and `swap_coins_config.json` contain the two Solana devnet entries
with explicit `wallet_only: false`, plus the existing `MARTY` UTXO testnet for
SOL/SPL ↔ UTXO swap testing. MARTY is copied from the reviewed generated registry
config after checking its raw protocol/network metadata and every Electrum endpoint
against `electrums/MARTY`. Both existing SSL and WSS nodes are required so native
and browser fixtures retain a UTXO counterasset. No node, contract or node-health
result is invented. RICK is absent from this registry baseline and is not added.
No mainnet entry can be admitted by the fixture generator. The manifest hashes
every generated input; the four-asset wallet payloads remain unchanged.

Consumers must use isolated preview storage, explicit `enableAutoUpdate: false`,
and supported-engine capability gates. Setting `runtime_updates_enabled: false`
alone is insufficient in the current Flutter SDK. Do not overlay this candidate
onto an existing real wallet's cached catalog. Keep production registry publication
and seven-platform KDF artifact enablement separate from this branch's development.

## Generator integration

Full regeneration continues through `utils/generate_app_configs.py`; the regular
scanner now includes Solana independently from EVM and Tron. Solana HTTP polling
nodes also survive the browser/WSS output filter. Raw SPL protocol data (platform,
mint, program and decimals) is preserved, with explicit parent metadata and
cluster-specific explorer templates. The generator does not infer parentage from
ticker suffixes.

## Validation recorded

The 40 scanner/generator regression tests pass, including an offline requests
adapter that returns an HTTPS-to-HTTP 307 redirect and verifies it is never
followed. Fixture tests verify the committed snapshot bytes and hashes, four
assets surviving full generation with a verified parent, and unchanged EVM/Tron
protocol/node generation. Validation also rejects malformed or ambiguously parsed
RPC URLs and checks that the chain-ID scan locates this repository independently
of the caller's working directory. Ticker regressions check the KDF separator
limit, exact generated identities and absence of mainnet price identifiers on
devnet. The swap fixture tests also verify curated MARTY metadata,
SSL/WSS node preservation, rejected unreviewed/disabled nodes and testnet-only scope.

A separate read-only probe on 2026-11-08 passed both public development endpoints:
mainnet finalized slot `467016646`, devnet finalized slot `520111989`, with health
and the expected genesis identities. These probes do not establish browser CORS,
retained history, transfer construction or swap execution. The offline-generated
snapshot manifest remains `nodes_verified_during_generation: false`.
