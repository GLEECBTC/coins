"""Solana registry validation and HTTP node scanning.

Cluster identities come from the Solana validator documentation:
https://beta.docs.solanalabs.com/clusters/available
Scanner metadata is deliberately separate from KDF's {"url": ...} node input.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

SOLANA_PROTOCOLS = ("SOLANA", "SOLANATOKEN")
CLUSTER_GENESIS_HASHES = {
    "mainnet-beta": "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d",
    "devnet": "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG",
}
TOKEN_PROGRAMS = {
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
}
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def validate_pubkey(value):
    if not isinstance(value, str) or not 32 <= len(value) <= 44:
        raise ValueError("Solana public keys must encode 32 bytes in base58")
    decoded = 0
    for char in value:
        if char not in BASE58:
            raise ValueError("Solana public keys must encode 32 bytes in base58")
        decoded = decoded * 58 + BASE58.index(char)
    leading_zeroes = len(value) - len(value.lstrip("1"))
    byte_length = (decoded.bit_length() + 7) // 8
    if leading_zeroes + byte_length != 32:
        raise ValueError("Solana public keys must encode 32 bytes in base58")
    return value


def platform_for(coin):
    protocol = coin["protocol"]
    if protocol["type"] == "SOLANA":
        platform = coin["coin"]
    elif protocol["type"] == "SOLANATOKEN":
        data = protocol.get("protocol_data", {})
        platform = data.get("platform")
        validate_pubkey(data.get("mint_address"))
        if data.get("program_id") not in TOKEN_PROGRAMS:
            raise ValueError("Unsupported Solana token program")
        decimals = data.get("decimals")
        if type(decimals) is not int or not 0 <= decimals <= 255:
            raise ValueError("SPL decimals must be an unsigned byte")
    else:
        raise ValueError("Not a Solana protocol")
    if not isinstance(platform, str) or not platform or Path(platform).name != platform:
        raise ValueError("Solana platform must be a registry ticker")
    if platform in (".", "..") or "\\" in platform:
        raise ValueError("Solana platform must be a registry ticker")
    return platform


def validate_registry_coins(coins):
    solana_coins = [coin for coin in coins
                    if coin.get("protocol", {}).get("type") in SOLANA_PROTOCOLS]
    native = {coin["coin"]: coin for coin in solana_coins
              if coin["protocol"]["type"] == "SOLANA"}
    for coin in solana_coins:
        parent = native.get(platform_for(coin))
        if parent is None:
            raise ValueError("SPL token parent must exist as a native Solana registry entry")
        if type(coin.get("is_testnet", False)) is not bool:
            raise ValueError("Solana is_testnet must be a boolean")
        if coin.get("is_testnet", False) != parent.get("is_testnet", False):
            raise ValueError("Solana token and parent must use the same network")
        if type(parent.get("decimals")) is not int or parent["decimals"] != 9:
            raise ValueError("Native SOL precision must be nine decimals")
    return solana_coins


def validate_node_config(config):
    if not isinstance(config, dict):
        raise ValueError("Solana node configuration must be an object")
    cluster = config.get("cluster")
    expected = CLUSTER_GENESIS_HASHES.get(cluster)
    if expected is None or config.get("genesis_hash") != expected:
        raise ValueError("Solana cluster/genesis identity is not recognized")
    nodes = config.get("rpc_nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("Solana requires at least one HTTPS RPC node")
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"url"}:
            raise ValueError("Solana RPC node entries contain only url")
        url = urlparse(node["url"]) if isinstance(node["url"], str) else None
        if (url is None or url.scheme != "https" or not url.hostname
                or url.username or url.password or url.fragment):
            raise ValueError("Solana requires HTTPS RPC URLs without userinfo/fragments")
    return config


def load_node_config(repo_path, platform):
    # Avoid letting protocol metadata escape the registry's node directory.
    if Path(platform).name != platform or platform in (".", "..") or "\\" in platform:
        raise ValueError("Invalid Solana platform ticker")
    with (Path(repo_path) / "solana" / platform).open() as handle:
        return validate_node_config(json.load(handle))


def nodes_for_coin(coin, repo_path, report, now=None, allow_unverified=False):
    platform = platform_for(coin)
    config = load_node_config(repo_path, platform)
    if coin.get("is_testnet", False) != (config["cluster"] == "devnet"):
        raise ValueError("Solana token/platform network does not match node cluster")
    now = time.time() if now is None else now
    platform_report = report.get(platform, {}) if isinstance(report, dict) else {}
    observations = platform_report.get("ssl", {}) if isinstance(platform_report, dict) else {}
    if not isinstance(observations, dict):
        observations = {}
    nodes = []
    for node in config["rpc_nodes"]:
        observed = observations.get(node["url"], {})
        if not isinstance(observed, dict):
            observed = {}
        last_connection = observed.get("last_connection", 0)
        verified = (
            observed.get("result") == "Passed"
            and observed.get("genesis_hash") == config["genesis_hash"]
            and type(last_connection) in (float, int)
            and 0 < last_connection <= now
            and now - last_connection < 604800
        )
        if verified or allow_unverified:
            nodes.append({"url": node["url"]})
    return nodes


def explorer_fields(coin):
    platform_for(coin)
    query = "?cluster=devnet" if coin.get("is_testnet", False) else ""
    return {
        "explorer_url": "https://explorer.solana.com/",
        "explorer_tx_url": "tx/{TX}" + query,
        "explorer_address_url": "address/{ADDRESS}" + query,
        "explorer_block_url": "block/{BLOCK}" + query,
    }


class SolanaRpcError(ValueError):
    pass


def _rpc(post, url, method, params):
    try:
        response = post(url, json={
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
        }, timeout=10, allow_redirects=False)
        if response.status_code != 200:
            raise SolanaRpcError("HTTP %s" % response.status_code)
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        if isinstance(error, SolanaRpcError):
            raise
        raise SolanaRpcError("RPC transport or JSON failure") from error
    if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0"
            or type(payload.get("id")) is not int or payload["id"] != 1
            or "error" in payload or "result" not in payload):
        raise SolanaRpcError("Malformed or failed %s response" % method)
    return payload["result"]


def probe_node(url, genesis_hash, post=None, now=None):
    post = requests.post if post is None else post
    try:
        actual_genesis = _rpc(post, url, "getGenesisHash", [])
        if actual_genesis != genesis_hash:
            raise SolanaRpcError("Wrong Solana cluster genesis hash")
        if _rpc(post, url, "getHealth", []) != "ok":
            raise SolanaRpcError("Solana node is not healthy")
        slot = _rpc(post, url, "getSlot", [{"commitment": "finalized"}])
        if type(slot) is not int or slot < 0:
            raise SolanaRpcError("Invalid finalized Solana slot")
        return {
            "last_connection": int(time.time() if now is None else now),
            "result": "Passed", "genesis_hash": actual_genesis, "slot": slot,
        }
    except SolanaRpcError as error:
        # Failed identity/health checks never inherit an earlier success timestamp.
        return {"last_connection": 0, "result": str(error)}


def scan_solana(repo_path, post=None, now=None):
    directory = Path(repo_path) / "solana"
    if not directory.exists():
        return {}
    configs = {
        path.name: load_node_config(repo_path, path.name)
        for path in sorted(directory.iterdir()) if path.is_file()
    }
    jobs = [(coin, node["url"], config["genesis_hash"])
            for coin, config in configs.items() for node in config["rpc_nodes"]]
    result = {coin: {"nodes_total_all": len(config["rpc_nodes"]),
                     "nodes_working_all": 0, "tcp": {}, "ssl": {}, "wss": {}}
              for coin, config in configs.items()}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(coin, url, pool.submit(probe_node, url, genesis, post, now))
                   for coin, url, genesis in jobs]
        for coin, url, future in futures:
            observation = future.result()
            result[coin]["ssl"][url] = observation
            if observation["result"] == "Passed":
                result[coin]["nodes_working_all"] += 1
    return result
