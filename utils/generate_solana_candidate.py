#!/usr/bin/env python3
"""Build isolated Solana fixtures without modifying production config snapshots."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from generate_app_configs import CoinConfig
from solana_registry import validate_registry_coins, scan_solana

REPO_PATH = Path(__file__).resolve().parents[1]
CURATED_UTXO_TICKERS = ("MARTY",)


def candidate_catalog(verify_nodes=False):
    with (REPO_PATH / "coins").open() as handle:
        coins = validate_registry_coins(json.load(handle))
    report = scan_solana(REPO_PATH) if verify_nodes else {}
    configs = {}
    for coin in coins:
        config = CoinConfig(coin, report, allow_unverified_solana=not verify_nodes)
        configs[coin["coin"]] = config.generate()
        if verify_nodes and configs[coin["coin"]].get("delisted"):
            raise ValueError("Solana candidate node validation failed for " + coin["coin"])
    return coins, configs


def curated_utxo_catalog():
    """Reuse reviewed UTXO testnet configs without inventing node health evidence."""
    with (REPO_PATH / "coins").open() as handle:
        registry = {coin["coin"]: coin for coin in json.load(handle)}
    with (REPO_PATH / "utils/coins_config.json").open() as handle:
        generated = json.load(handle)
    coins, configs = [], {}
    for ticker in CURATED_UTXO_TICKERS:
        coin, config = registry.get(ticker), generated.get(ticker)
        if coin is None or config is None:
            raise ValueError("Curated UTXO testnet is missing from registry/config: " + ticker)
        if (coin.get("is_testnet") is not True or config.get("is_testnet") is not True
                or coin.get("protocol", {}).get("type") != "UTXO"
                or config.get("protocol") != coin["protocol"]
                or coin.get("wallet_only", False) is not False
                or config.get("wallet_only") is not False or config.get("delisted", False)):
            raise ValueError("Curated swap counterasset must be an enabled UTXO testnet: " + ticker)
        if any(config.get(key) != value for key, value in coin.items()):
            raise ValueError("Curated UTXO config does not match registry metadata: " + ticker)
        with (REPO_PATH / "electrums" / ticker).open() as handle:
            source_nodes = json.load(handle)
        allowed = set()
        for node in source_nodes:
            disabled = {protocol.upper() for protocol in node.get("disabled", [])}
            protocol = node.get("protocol", "TCP").upper()
            if protocol not in disabled:
                allowed.add((node["url"], protocol))
            if "ws_url" in node and "WSS" not in disabled:
                allowed.add((node["ws_url"], "WSS"))
        nodes = config.get("electrum", [])
        if (not nodes or any((node.get("url"), node.get("protocol")) not in allowed for node in nodes)
                or not {"SSL", "WSS"}.issubset({node.get("protocol") for node in nodes})):
            raise ValueError("Curated UTXO requires configured native SSL and browser WSS nodes: " + ticker)
        coins.append(deepcopy(coin))
        configs[ticker] = deepcopy(config)
    return coins, configs


def write_candidate(output_dir, verify_nodes=False):
    coins, configs = candidate_catalog(verify_nodes)
    swap_coins = deepcopy([coin for coin in coins if coin["is_testnet"]])
    swap_configs = deepcopy({key: value for key, value in configs.items()
                             if value["is_testnet"]})
    for coin in swap_coins:
        coin["wallet_only"] = False
    for coin in swap_configs.values():
        coin["wallet_only"] = False
    utxo_coins, utxo_configs = curated_utxo_catalog()
    swap_coins.extend(utxo_coins)
    swap_configs.update(utxo_configs)
    outputs = {"coins.json": coins, "coins_config.json": configs,
               "swap_coins.json": swap_coins, "swap_coins_config.json": swap_configs}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, payload in outputs.items():
        encoded = (json.dumps(payload, indent=2) + "\n").encode()
        (output_dir / name).write_bytes(encoded)
        hashes[name] = hashlib.sha256(encoded).hexdigest()
    manifest = {
        "purpose": "isolated Solana integration candidate; not a production registry release",
        "nodes_verified_during_generation": False,
        "solana_nodes_verified_during_generation": verify_nodes,
        "utxo_nodes_verified_during_generation": False,
        "curated_utxo_tickers": list(CURATED_UTXO_TICKERS),
        "curated_utxo_config_source": "utils/coins_config.json",
        "runtime_updates_enabled": False,
        "requires_explicit_enable_auto_update_false": True,
        "requires_isolated_storage_namespace": True,
        "sha256": hashes,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_PATH / "utils/fixtures/solana")
    parser.add_argument("--verify-nodes", action="store_true",
                        help="Require live Solana health, finalized slot and cluster-identity checks")
    args = parser.parse_args()
    write_candidate(args.output, args.verify_nodes)
