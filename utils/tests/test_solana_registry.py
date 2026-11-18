from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
from requests.adapters import BaseAdapter

UTILS = Path(__file__).resolve().parents[1]
REPO = UTILS.parent
sys.path.insert(0, str(UTILS))
import generate_app_configs as generator
from solana_registry import (CLUSTER_GENESIS_HASHES, load_node_config,
                             nodes_for_coin, platform_for, probe_node, scan_solana,
                             validate_node_config, validate_registry_coins)

with (REPO / "coins").open() as handle:
    COINS = {coin["coin"]: coin for coin in json.load(handle)}
DEVNET = CLUSTER_GENESIS_HASHES["devnet"]
MAINNET = CLUSTER_GENESIS_HASHES["mainnet-beta"]
URL = "https://api.devnet.solana.com"
NOW = 2000000000


def rpc_response(result, status=200):
    response = Mock(status_code=status)
    response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": result}
    return response


def successful_post(genesis=DEVNET, slot=42):
    return Mock(side_effect=[rpc_response(genesis), rpc_response("ok"), rpc_response(slot)])


def valid_report(platform="TESTSOL", url=URL, genesis=DEVNET):
    return {platform: {"tcp": {}, "wss": {}, "ssl": {url: {
        "result": "Passed", "last_connection": NOW, "genesis_hash": genesis, "slot": 42,
    }}}}


def valid_solana_report():
    report = {}
    for ticker in ("SOL", "TESTSOL"):
        source = load_node_config(REPO, ticker)
        report[ticker] = {"tcp": {}, "wss": {}, "ssl": {
            node["url"]: {
                "result": "Passed",
                "last_connection": NOW,
                "genesis_hash": source["genesis_hash"],
                "slot": 42,
            }
            for node in source["rpc_nodes"]
        }}
    return report


def generated_solana_catalog():
    report = valid_solana_report()
    with patch("solana_registry.time.time", return_value=NOW):
        return {
            coin["coin"]: generator.CoinConfig(coin, report).generate()
            for coin in validate_registry_coins(COINS.values())
        }


class NodeProbeTests(unittest.TestCase):
    def test_healthy_node_requires_identity_health_and_finalized_slot(self):
        post = successful_post()
        result = probe_node(URL, DEVNET, post, NOW)
        self.assertEqual(result["result"], "Passed")
        self.assertEqual(result["last_connection"], NOW)
        self.assertEqual(result["genesis_hash"], DEVNET)
        self.assertEqual(result["slot"], 42)
        calls = [call.kwargs["json"] for call in post.call_args_list]
        self.assertEqual([call["method"] for call in calls],
                         ["getGenesisHash", "getHealth", "getSlot"])
        self.assertEqual(calls[-1]["params"], [{"commitment": "finalized"}])
        self.assertTrue(all(call.kwargs["allow_redirects"] is False
                            for call in post.call_args_list))

    def test_wrong_cluster_stops_before_health_and_does_not_preserve_success(self):
        post = successful_post(MAINNET)
        result = probe_node(URL, DEVNET, post, NOW)
        self.assertEqual(result["last_connection"], 0)
        self.assertIn("Wrong Solana cluster", result["result"])
        self.assertEqual(post.call_count, 1)

    def test_unhealthy_node_is_rejected(self):
        post = Mock(side_effect=[rpc_response(DEVNET), rpc_response("behind")])
        self.assertIn("not healthy", probe_node(URL, DEVNET, post, NOW)["result"])
        self.assertEqual(post.call_count, 2)

    def test_rate_limit_is_a_failure(self):
        post = Mock(return_value=rpc_response(None, 429))
        self.assertEqual(probe_node(URL, DEVNET, post, NOW),
                         {"last_connection": 0, "result": "HTTP 429"})

    def test_https_redirect_to_plain_http_is_refused_without_following(self):
        calls = []
        class RedirectAdapter(BaseAdapter):
            def send(self, request, **kwargs):
                calls.append(request.url)
                response = requests.Response()
                response.request = request
                response.url = request.url
                if request.url.startswith("https:"):
                    response.status_code = 307
                    response.headers["Location"] = request.url.replace("https:", "http:", 1)
                    response._content = b""
                else:
                    # A valid chain reply must not make an HTTPS downgrade acceptable.
                    method = json.loads(request.body)["method"]
                    result = {"getGenesisHash": DEVNET, "getHealth": "ok", "getSlot": 42}[method]
                    response.status_code = 200
                    response._content = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()
                return response

            def close(self):
                pass

        with requests.Session() as session:
            session.trust_env = False
            session.mount("https://", RedirectAdapter())
            session.mount("http://", RedirectAdapter())
            result = probe_node(URL, DEVNET, session.post, NOW)
        self.assertEqual(result, {"last_connection": 0, "result": "HTTP 307"})
        self.assertEqual(calls, [URL + "/"])

    def test_rpc_error_does_not_count_as_success(self):
        response = rpc_response(None)
        response.json.return_value = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32005}}
        self.assertEqual(probe_node(URL, DEVNET, Mock(return_value=response), NOW)["last_connection"], 0)

    def test_malformed_response_and_invalid_json_fail(self):
        for payload in [[], {}, {"result": DEVNET}, {"jsonrpc": "2.0", "id": 2, "result": DEVNET},
                        {"jsonrpc": "2.0", "id": True, "result": DEVNET}]:
            with self.subTest(payload=payload):
                response = rpc_response(None)
                response.json.return_value = payload
                self.assertEqual(probe_node(URL, DEVNET, Mock(return_value=response), NOW)["last_connection"], 0)
        response.json.side_effect = ValueError("invalid JSON")
        self.assertEqual(probe_node(URL, DEVNET, Mock(return_value=response), NOW)["last_connection"], 0)

    def test_transport_error_does_not_leak_url_or_credentials(self):
        post = Mock(side_effect=requests.Timeout("private provider URL"))
        result = probe_node(URL, DEVNET, post, NOW)
        self.assertEqual(result["result"], "RPC transport or JSON failure")

    def test_slot_must_be_a_nonnegative_integer(self):
        for slot in [True, -1, "42", None, 3.2]:
            with self.subTest(slot=slot):
                self.assertEqual(probe_node(URL, DEVNET, successful_post(slot=slot), NOW)["last_connection"], 0)
        self.assertEqual(probe_node(URL, DEVNET, successful_post(slot=0), NOW)["result"], "Passed")

    def test_scan_reports_native_platforms_only_and_https_nodes(self):
        def post(url, json, timeout, allow_redirects):
            self.assertFalse(allow_redirects)
            genesis = DEVNET if "devnet" in url else MAINNET
            result = {"getGenesisHash": genesis, "getHealth": "ok", "getSlot": 42}[json["method"]]
            return rpc_response(result)
        result = scan_solana(REPO, post, NOW)
        self.assertEqual(set(result), {"SOL", "TESTSOL"})
        for platform, report in result.items():
            configured = {node["url"] for node in load_node_config(REPO, platform)["rpc_nodes"]}
            self.assertEqual(set(report["ssl"]), configured)
            self.assertEqual(report["nodes_total_all"], len(configured))
            self.assertEqual(report["nodes_working_all"], len(configured))
            self.assertFalse(report["tcp"])
            self.assertFalse(report["wss"])

    def test_mainnet_lists_a_browser_usable_node_first(self):
        # api.mainnet-beta.solana.com answers 403 to any request carrying an
        # Origin header, so browsers cannot use it. KDF starts with the first
        # node and only falls back in list order, so web wallets need another
        # node ahead of it.
        nodes = [node["url"] for node in load_node_config(REPO, "SOL")["rpc_nodes"]]
        self.assertGreater(len(nodes), 1)
        self.assertNotEqual(nodes[0], "https://api.mainnet-beta.solana.com")


class RegistryTests(unittest.TestCase):
    def test_four_asset_catalog_matches_kdf_metadata(self):
        catalog = generated_solana_catalog()
        self.assertEqual(set(catalog), {"SOL", "TESTSOL", "USDC-SOL", "TESTUSDC-TESTSOL"})
        for ticker, entry in catalog.items():
            coin = COINS[ticker]
            self.assertEqual(entry["coin"], coin["coin"])
            self.assertLessEqual(entry["coin"].count("-"), 1)
            self.assertEqual(entry["protocol"], coin["protocol"])
            self.assertEqual(entry["type"], coin["protocol"]["type"])
            self.assertEqual(entry["derivation_path"], "m/44'/501'")
            self.assertEqual(entry["required_confirmations"], 1)
            self.assertEqual(entry["wallet_only"], not coin["is_testnet"])
            self.assertFalse(entry.get("delisted", False))
            self.assertEqual(set(entry["nodes"][0]), {"url"})
            if entry["type"] == "SOLANATOKEN":
                self.assertEqual(entry["parent_coin"], coin["protocol"]["protocol_data"]["platform"])
                self.assertEqual(entry["decimals"], 6)
                self.assertEqual(entry["nodes"], catalog[entry["parent_coin"]]["nodes"])
            else:
                self.assertEqual(entry["decimals"], 9)

    def test_registry_rejects_multiple_ticker_separators(self):
        token = deepcopy(COINS["TESTUSDC-TESTSOL"])
        token["coin"] = "TEST-USDC-TESTSOL"
        with self.assertRaisesRegex(ValueError, "at most one hyphen"):
            validate_registry_coins([COINS["TESTSOL"], token])

    def test_registry_rejects_mainnet_pricing_prefixes_for_testnet(self):
        for ticker, replacement in [("TESTSOL", "SOL-DEV"),
                                    ("TESTUSDC-TESTSOL", "USDC-TESTSOL")]:
            source = deepcopy(list(COINS.values()))
            for coin in source:
                if coin["coin"] == ticker:
                    coin["coin"] = replacement
            with self.subTest(ticker=ticker), self.assertRaisesRegex(
                    ValueError, "mainnet pricing prefix"):
                validate_registry_coins(source)

    def test_devnet_tickers_preserve_identity_without_mainnet_pricing_ids(self):
        catalog = generated_solana_catalog()
        for ticker in ["TESTSOL", "TESTUSDC-TESTSOL"]:
            with self.subTest(ticker=ticker):
                entry = catalog[ticker]
                self.assertEqual(entry["coin"], ticker)
                for field in ["coinpaprika_id", "coingecko_id", "livecoinwatch_id",
                              "binance_id", "forex_id"]:
                    self.assertFalse(entry.get(field), field)
        self.assertEqual(catalog["TESTUSDC-TESTSOL"]["parent_coin"], "TESTSOL")
        self.assertEqual(catalog["SOL"]["livecoinwatch_id"], "SOL")
        self.assertEqual(catalog["USDC-SOL"]["livecoinwatch_id"], "USDC")

    def test_token_parent_is_explicit_not_inferred_from_ticker(self):
        token = deepcopy(COINS["TESTUSDC-TESTSOL"])
        token["coin"] = "ARBITRARY-NAME"
        self.assertEqual(platform_for(token), "TESTSOL")
        self.assertEqual(nodes_for_coin(token, REPO, valid_report(), NOW), [{"url": URL}])

    def test_missing_platform_node_file_is_an_error(self):
        token = deepcopy(COINS["TESTUSDC-TESTSOL"])
        token["protocol"]["protocol_data"]["platform"] = "NOT-A-PLATFORM"
        with self.assertRaises(FileNotFoundError):
            nodes_for_coin(token, REPO, {}, NOW)

    def test_regular_catalog_generation_rejects_missing_parent(self):
        with patch.object(generator, "ensure_chainids"), patch.object(
                generator.json, "load", return_value=[COINS["TESTUSDC-TESTSOL"]]):
            with self.assertRaisesRegex(ValueError, "parent must exist"):
                generator.parse_coins_repo({})

    def test_registry_requires_native_precision_and_matching_parent_network(self):
        for field, value in [("decimals", 8), ("decimals", True), ("is_testnet", False)]:
            coins = deepcopy([COINS["TESTSOL"], COINS["TESTUSDC-TESTSOL"]])
            coins[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_registry_coins(coins)

    def test_token_2022_fixture_preserves_metadata_without_public_listing(self):
        fixture = deepcopy(COINS["TESTUSDC-TESTSOL"])
        fixture["coin"] = "TESTTOKEN2022-TESTSOL"
        data = fixture["protocol"]["protocol_data"]
        data["program_id"] = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
        with patch("solana_registry.time.time", return_value=NOW):
            entry = generator.CoinConfig(fixture, valid_report()).generate()
        self.assertEqual(entry["protocol"]["protocol_data"], data)
        self.assertEqual(entry["parent_coin"], "TESTSOL")
        self.assertEqual(entry["wallet_only"], fixture["wallet_only"])
        self.assertNotIn("TESTTOKEN2022-TESTSOL", generated_solana_catalog())

    def test_malformed_scan_cache_does_not_admit_unverified_nodes(self):
        for report in [None, [], {"TESTSOL": None}, {"TESTSOL": {"ssl": []}},
                       {"TESTSOL": {"ssl": {URL: None}}}]:
            with self.subTest(report=report):
                self.assertEqual(nodes_for_coin(COINS["TESTSOL"], REPO, report, NOW), [])

    def test_wrong_cluster_and_stale_scan_never_enable_nodes(self):
        for report in [{}, valid_report(genesis=MAINNET), valid_report()]:
            effective_now = NOW + 604801 if report == valid_report() else NOW
            self.assertEqual(nodes_for_coin(COINS["TESTSOL"], REPO, report, effective_now), [])
        report = valid_report()
        report["TESTSOL"]["ssl"][URL]["result"] = "Wrong Solana cluster genesis hash"
        self.assertEqual(nodes_for_coin(COINS["TESTSOL"], REPO, report, NOW), [])

    def test_token_network_must_match_platform(self):
        token = deepcopy(COINS["TESTUSDC-TESTSOL"])
        token["is_testnet"] = False
        with self.assertRaisesRegex(ValueError, "network does not match"):
            nodes_for_coin(token, REPO, valid_report(), NOW)

    def test_registry_rejects_invalid_token_metadata(self):
        for field, value in [("mint_address", "invalid"), ("program_id", "invalid"),
                             ("decimals", True), ("decimals", -1), ("decimals", 256),
                             ("platform", "../SOL"), ("platform", "..")]:
            with self.subTest(field=field, value=value):
                token = deepcopy(COINS["TESTUSDC-TESTSOL"])
                token["protocol"]["protocol_data"][field] = value
                with self.assertRaises(ValueError):
                    platform_for(token)

    def test_node_schema_rejects_wrong_identity_and_extra_wire_fields(self):
        source = load_node_config(REPO, "TESTSOL")
        for change in [{"genesis_hash": MAINNET}, {"cluster": "unknown"}, {"rpc_nodes": []},
                       {"rpc_nodes": [{"url": URL, "komodo_proxy": True}]},
                       {"rpc_nodes": [{"url": "http://localhost"}]},
                       {"rpc_nodes": [{"url": "https://user:password@example.com"}]}]:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    validate_node_config({**source, **change})

    def test_node_schema_requires_canonical_public_https_urls(self):
        source = load_node_config(REPO, "TESTSOL")
        invalid_urls = [
            "https://api.devnet.solana.com:bad",
            "https://api.devnet.solana.com:65536",
            "https://api.devnet.solana.com:0",
            "https://@api.devnet.solana.com",
            "https://:@api.devnet.solana.com",
            "https://api.devnet.solana.com#",
            "\nhttps://api.devnet.solana.com",
            "https://api.devnet.solana.com/\tpath",
            "https://api.devnet.solana.com/\x00path",
            "https://api.devnet.solana.com/\\path",
            "HTTPS://api.devnet.solana.com",
        ]
        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_node_config({**source, "rpc_nodes": [{"url": url}]})
        for url in [URL, URL + ":443", URL + "/rpc?network=devnet"]:
            with self.subTest(url=url):
                self.assertEqual(validate_node_config(
                    {**source, "rpc_nodes": [{"url": url}]})["rpc_nodes"], [{"url": url}])

    def test_chain_id_scan_reads_its_own_registry_from_any_working_directory(self):
        previous_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as directory, patch(
                "ensure_chainids.requests.get", return_value=Mock(json=lambda: [])), patch(
                "builtins.print"):
            try:
                os.chdir(directory)
                generator.ensure_chainids()
                self.assertEqual(Path.cwd(), Path(directory).resolve())
            finally:
                os.chdir(previous_directory)

    def test_generation_filters_failed_solana_nodes_instead_of_using_fallback(self):
        config = generator.CoinConfig(COINS["TESTSOL"], {})
        entry = config.generate()
        self.assertTrue(entry["delisted"])
        self.assertEqual(entry["nodes"], [])

    def test_verified_generation_accepts_matching_healthy_nodes(self):
        with patch("solana_registry.time.time", return_value=NOW):
            entry = generator.CoinConfig(COINS["TESTUSDC-TESTSOL"], valid_report()).generate()
        self.assertEqual(entry["nodes"], [{"url": URL}])
        self.assertFalse(entry.get("delisted", False))

    def test_full_generator_keeps_verified_native_and_token_entries_listed(self):
        report = valid_solana_report()
        source = [COINS[ticker] for ticker in ["SOL", "TESTSOL", "USDC-SOL", "TESTUSDC-TESTSOL"]]
        original_load = json.load
        def load(handle):
            return source if str(handle.name).endswith("/coins") else original_load(handle)
        with tempfile.TemporaryDirectory() as directory, patch.object(
                generator, "ensure_chainids"), patch.object(generator.json, "load", side_effect=load), patch.object(
                generator, "script_path", directory), patch("solana_registry.time.time", return_value=NOW):
            catalog, delisted = generator.parse_coins_repo(report)
        self.assertEqual(set(catalog), {"SOL", "TESTSOL", "USDC-SOL", "TESTUSDC-TESTSOL"})
        self.assertEqual(delisted, [])
        for ticker, entry in catalog.items():
            self.assertTrue(entry["nodes"])
            self.assertFalse(entry.get("delisted", False))

    def test_mainnet_and_devnet_explorer_query_placement(self):
        catalog = generated_solana_catalog()
        for ticker, suffix in [
            ("SOL", ""),
            ("USDC-SOL", ""),
            ("TESTSOL", "?cluster=devnet"),
            ("TESTUSDC-TESTSOL", "?cluster=devnet"),
        ]:
            with self.subTest(ticker=ticker):
                entry = catalog[ticker]
                self.assertEqual(entry["explorer_url"], "https://explorer.solana.com/")
                self.assertEqual(entry["explorer_tx_url"], "tx/{TX}" + suffix)
                self.assertEqual(entry["explorer_address_url"], "address/{ADDRESS}" + suffix)
                self.assertEqual(entry["explorer_block_url"], "block/{BLOCK}" + suffix)

    def test_https_solana_survives_native_and_browser_filters(self):
        catalog = generated_solana_catalog()
        with tempfile.TemporaryDirectory() as directory, patch.object(generator, "script_path", directory):
            ssl = generator.filter_ssl(deepcopy(catalog))
            tcp = generator.filter_tcp(deepcopy(catalog), ssl)
            wss = generator.filter_wss(deepcopy(catalog))
        for filtered in (ssl, tcp, wss):
            self.assertEqual(set(filtered), set(catalog))
            self.assertEqual(filtered["TESTUSDC-TESTSOL"]["nodes"], [{"url": URL}])

    def test_existing_evm_and_tron_generation_keeps_protocol_and_nodes(self):
        for ticker, kind in [("ETH", "ERC-20"), ("TRX", "TRX"), ("USDT-TRC20", "TRC-20")]:
            with self.subTest(ticker=ticker):
                config = generator.CoinConfig(COINS[ticker], {})
                entry = config.generate()
                self.assertEqual(entry["type"], kind)
                self.assertTrue(entry["nodes"])
                self.assertEqual(entry["protocol"], COINS[ticker]["protocol"])
                self.assertNotIn("genesis_hash", entry)


if __name__ == "__main__":
    unittest.main()
