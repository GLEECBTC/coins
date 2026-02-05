#!/usr/bin/env python3
import os
import sys
import time
import json
import math
from copy import deepcopy
import requests
from PIL import Image
from scan_electrums import get_electrums_report
from ensure_chainids import ensure_chainids
from logger import logger
from uptime_tracker import UptimeTracker, format_contact_info


current_time = time.time()
script_path = os.path.abspath(os.path.dirname(__file__))
repo_path = script_path.replace("/utils", "")
os.chdir(script_path)

BINANCE_DELISTED_COINS = [
    "AGIX",
    "ANT",
    "BAL",
    "BIDR",
    "BTT",
    "BUSD",
    "ELF",
    "FIRO",
    "GFT",
    "GRS",
    "IRIS",
    "KMD",
    "LOOM",
    "MATIC",
    "MC",
    "MDX",
    "MIR",
    "NAV",
    "OCEAN",
    "OMG",
    "PAX",
    "QI",
    "REN",
    "REP",
    "SNT",
    "SRM",
    "VGX",
    "VIA",
    "WAVES",
    "YFII",
]

MISMATCHED_IDS = [
    "ZEN",
    "SC",
]

# TODO: Check all coins have an icon.
icons = [
    f
    for f in os.listdir(f"{repo_path}/icons")
    if os.path.isfile(f"{repo_path}/icons/{f}.png")
]
lightwallet_coins = [
    f
    for f in os.listdir(f"{repo_path}/light_wallet_d")
    if os.path.isfile(f"{repo_path}/light_wallet_d/{f}")
    and not f.endswith("_WSS")
]
lightwallet_wss_coins = [
    f
    for f in os.listdir(f"{repo_path}/light_wallet_d")
    if os.path.isfile(f"{repo_path}/light_wallet_d/{f}")
    and f.endswith("_WSS")
]
electrum_coins = [
    f
    for f in os.listdir(f"{repo_path}/electrums")
    if os.path.isfile(f"{repo_path}/electrums/{f}")
]
tendermint_coins = [
    f
    for f in os.listdir(f"{repo_path}/tendermint")
    if os.path.isfile(f"{repo_path}/tendermint/{f}")
]
ethereum_coins = [
    f
    for f in os.listdir(f"{repo_path}/ethereum")
    if os.path.isfile(f"{repo_path}/ethereum/{f}")
]
explorer_coins = [
    f
    for f in os.listdir(f"{repo_path}/explorers")
    if os.path.isfile(f"{repo_path}/explorers/{f}")
]

binance_quote_tickers = [
    "BTC",
    "ETH",
    "BNB",
    "USDT",
    "USDC",
    "TUSD",
    "XRP",
    "TRX",
    "TRY",
    "EUR",
    "BRL",
    "GBP",
    "AUD",
    "RUB",
    "NGN",
    "UAH",
]

with open(f"{repo_path}/explorers/explorer_paths.json", "r") as f:
    explorer_paths = json.load(f)

with open(f"{repo_path}/api_ids/forex_ids.json", "r") as f:
    forex_ids = json.load(f)

with open(f"{repo_path}/api_ids/livecoinwatch_ids.json", "r") as f:
    livecoinwatch_ids = json.load(f)

with open(f"{repo_path}/api_ids/binance_ids.json", "r") as f:
    binance_ids = json.load(f)

with open(f"{repo_path}/api_ids/coingecko_ids.json", "r") as f:
    coingecko_ids = json.load(f)

with open(f"{repo_path}/api_ids/coinpaprika_ids.json", "r") as f:
    coinpaprika_ids = json.load(f)




class CoinConfig:
    def __init__(self, coin_data: dict, electrum_scan_report: dict, uptime_tracker: UptimeTracker = None):
        self.coin_data = coin_data
        self.electrum_scan_report = electrum_scan_report
        self.uptime_tracker = uptime_tracker
        self.data = {}
        self.is_testnet = self.is_testnet_network()
        self.ticker = self.coin_data["coin"].replace("-TEST", "")
        self.base_ticker = self.ticker.split("-")[0]
        self.protocols = {
            "AVAX": "AVX-20",
            "BNB": "BEP-20",
            "ETC": "Ethereum Classic",
            "ETH": "ERC-20",
            "ETH-ARB20": "Arbitrum",
            "ETH-BASE": "Base",
            "EWT": "EWT",
            "GLMR": "Moonbeam",
            "KCS": "KRC-20",
            "POL": "Polygon",
            "MOVR": "Moonriver",
            "ONE": "HRC-20",
            "QTUM": "QRC-20",
            "RBTC": "RSK Smart Bitcoin",
            "SBCH": "SmartBCH",
            "ATOM": "TENDERMINT",
            "OSMO": "TENDERMINT",
            "IRIS": "TENDERMINT",
            "UBQ": "Ubiq",
        }
        self.testnet_protocols = {
            "AVAXT": "AVX-20",
            "BNBT": "BEP-20",
            "tQTUM": "QRC-20",
            "IRISTEST": "TENDERMINT",
            "NUCLEUSTEST": "TENDERMINT",
            "POLTEST": "Polygon",
            "UBQ": "Ubiq",
        }
        self.coin_type = coin_data["protocol"]["type"]
        self.data.update(
            {
                self.ticker: {
                    "coin": self.ticker,
                    "type": "",
                    "name": "",
                    "coinpaprika_id": "",
                    "coingecko_id": "",
                    "livecoinwatch_id": "",
                    "explorer_url": "",
                    "explorer_tx_url": "",
                    "explorer_address_url": "",
                    "supported": [],
                    "active": False,
                    "is_testnet": self.is_testnet,
                    "currently_enabled": False,
                    "wallet_only": False,
                }
            }
        )
        if self.coin_type in ["UTXO", "QRC20", "QTUM", "SIA"]:
            try:
                if self.coin_data["sign_message_prefix"]:
                    self.data[self.ticker].update(
                        {"sign_message_prefix": coin_data["sign_message_prefix"]}
                    )
                else:
                    self.data[self.ticker].update({"sign_message_prefix": ""})
            except KeyError as e:
                print(self.ticker + ": Sign message was not found\n")
        elif self.coin_type in ["ZHTLC"]:
            if self.ticker in lightwallet_coins:
                with open(f"{repo_path}/light_wallet_d/{self.ticker}", "r") as f:
                    lightwallet_servers = json.load(f)
                self.data[self.ticker].update(
                    {"light_wallet_d_servers": lightwallet_servers}
                )
                if f"{self.ticker}_WSS" in lightwallet_wss_coins:
                    with open(f"{repo_path}/light_wallet_d/{self.ticker}_WSS", "r") as f:
                        lightwallet_servers_wss = json.load(f)
                    self.data[self.ticker].update(
                        {"light_wallet_d_servers_wss": lightwallet_servers_wss}
                    )
                else:
                    self.data[self.ticker].update({
                        "light_wallet_d_servers_wss": []
                    })
            else:
                self.data[self.ticker].update({
                    "light_wallet_d_servers": [],
                    "light_wallet_d_servers_wss": []
                })
        elif self.coin_type in ["SIA"]:
            self.data[self.ticker].update({"nodes": ["SIA"]})

    def get_protocol_info(self):
        if "protocol_data" in self.coin_data["protocol"]:
            protocol_data = self.coin_data["protocol"]["protocol_data"]
            if "consensus_params" in protocol_data:
                # TODO: ZHTLC things
                self.data[self.ticker].update({"type": self.coin_type})
            if "check_point_block" in protocol_data:
                # ZHTLC only
                if "height" in protocol_data["check_point_block"]:
                    self.data[self.ticker].update(
                        {
                            "checkpoint_height": protocol_data["check_point_block"][
                                "height"
                            ]
                        }
                    )
                if "time" in protocol_data["check_point_block"]:
                    self.data[self.ticker].update(
                        {
                            "checkpoint_blocktime": protocol_data["check_point_block"][
                                "time"
                            ]
                        }
                    )


            elif "platform" in protocol_data:
                # TODO: ERC-like things
                platform = protocol_data["platform"]
                if self.is_testnet:
                    coin_type = self.testnet_protocols[platform]
                else:
                    coin_type = self.protocols[platform]
                self.data[self.ticker].update({"type": coin_type})
                if "contract_address" in protocol_data:
                    self.data[self.ticker].update(
                        {"contract_address": protocol_data["contract_address"]}
                    )
        else:
            self.data[self.ticker].update({"type": self.coin_type})

        self.parent_coin = self.get_parent_coin()
        if self.parent_coin:
            if self.parent_coin != self.ticker:
                self.data[self.ticker].update({"parent_coin": self.parent_coin})

        if self.coin_data["protocol"]["type"] in ["ETH", "QTUM"]:
            if self.ticker in self.protocols:
                coin_type = self.protocols[self.ticker]
            elif self.ticker in self.testnet_protocols:
                coin_type = self.testnet_protocols[self.ticker]
            elif self.parent_coin in self.protocols:
                coin_type = self.protocols[self.parent_coin]
            elif self.parent_coin in self.testnet_protocols:
                coin_type = self.testnet_protocols[self.parent_coin]
            else:
                coin_type = self.coin_data["protocol"]["type"]
            self.data[self.ticker].update({"type": coin_type})

        elif self.coin_data["protocol"]["type"] in ["TENDERMINT", "TENDERMINTTOKEN"]:
            coin_type = self.coin_data["protocol"]["type"]
            self.data[self.ticker].update({"type": coin_type})

    def is_testnet_network(self):
        if "is_testnet" in self.coin_data:
            return self.coin_data["is_testnet"]
        return False

    def get_forex_id(self):
        coin = self.ticker.replace("-segwit", "")
        if coin in forex_ids:
            self.data[self.ticker].update({"forex_id": forex_ids[coin]})

    def get_coinpaprika_id(self):
        coin = self.ticker.replace("-segwit", "")
        if coin in coinpaprika_ids:
            self.data[self.ticker].update({"coinpaprika_id": coinpaprika_ids[coin]})

    def get_coingecko_id(self):
        coin = self.ticker.replace("-segwit", "")
        if coin in coingecko_ids:
            self.data[self.ticker].update({"coingecko_id": coingecko_ids[coin]})

    def get_livecoinwatch_id(self):
        coin = self.ticker.split("-")[0]
        if coin in livecoinwatch_ids:
            self.data[self.ticker].update({"livecoinwatch_id": livecoinwatch_ids[coin]})

    def get_binance_id(self):
        coin = self.ticker.split("-")[0]
        if coin in binance_ids:
            self.data[self.ticker].update({"binance_id": binance_ids[coin]})

    def get_alias_ticker(self):
        if "alias_ticker" in self.coin_data:
            self.data[self.ticker].update(
                {"alias_ticker": self.coin_data["alias_ticker"]}
            )

    def get_asset(self):
        if "asset" in self.coin_data:
            self.data[self.ticker].update({"asset": self.coin_data["asset"]})

    def get_links(self):
        if "links" in self.coin_data:
            self.data[self.ticker].update({"links": self.coin_data["links"]})

    def get_hd_info(self):
        if "derivation_path" in self.coin_data:
            self.data[self.ticker].update(
                {"derivation_path": self.coin_data["derivation_path"]}
            )
        if "trezor_coin" in self.coin_data:
            self.data[self.ticker].update(
                {"trezor_coin": self.coin_data["trezor_coin"]}
            )

    def get_rewards_info(self):
        if self.ticker in ["KMD"]:
            self.data[self.ticker].update(
                {"is_claimable": True, "minimal_claim_amount": "10"}
            )

    def get_address_format(self):
        if "address_format" in self.coin_data:
            self.data[self.ticker].update(
                {"address_format": self.coin_data["address_format"]}
            )

        if self.ticker.find("-segwit") > -1:
            self.data[self.ticker].update({"address_format": {"format": "segwit"}})

    def is_smartchain(self):
        if "sign_message_prefix" in self.coin_data:
            if self.coin_data["sign_message_prefix"] == "Komodo Signed Message:\n":
                self.data[self.ticker]["type"] = "Smart Chain"

    def is_wallet_only(self):
        if "wallet_only" in self.coin_data:
            self.data[self.ticker].update(
                {"wallet_only": self.coin_data["wallet_only"]}
            )

    def get_scan_coin_for_status_check(self):
        """
        Get the coin name to check in electrum_scan_report for connectivity status.
        For token coins, this returns the parent chain coin.
        """
        # For token coins, we need to check parent chain status
        if self.ticker.endswith(("-QRC20", "-ERC20", "-BEP20", "-PLG20", "-AVX20")):
            if self.ticker.endswith("-QRC20"):
                return "tQTUM" if self.is_testnet else "QTUM"
            elif self.ticker.endswith("-ERC20"):
                return "ETH"
            elif self.ticker.endswith("-BEP20"):
                return "BNB"
            elif self.ticker.endswith("-PLG20"):
                return "MATIC"
            elif self.ticker.endswith("-AVX20"):
                return "AVAX"
        
        # For electrum coins, use the actual coin name (with segwit handling)
        coin = self.ticker.replace("-segwit", "")
        if self.data[self.ticker]["type"] == "QRC-20":
            if self.is_testnet:
                coin = "tQTUM"
            else:
                coin = "QTUM"
        
        return coin

    def get_parent_coin(self):
        """Used for getting filename for related coins/ethereum folder"""
        token_type = self.data[self.ticker]["type"]
        if self.ticker == "RBTC":
            return "RSK"

        if self.coin_type in ["TENDERMINTTOKEN", "TENDERMINT"]:
            for i in ["IRISTEST", "NUCLEUSTEST"]:
                if self.ticker.find(i) > -1:
                    self.is_testnet = True
                    return i
            for i in ["IBC_IRIS", "IBC_ATOM", "IBC_OSMO"]:
                if self.ticker.find(i) > -1:
                    return i.replace("IBC_", "")

        if self.coin_type not in ["UTXO", "ZHTLC", "BCH", "QTUM", "SIA"]:
            if self.data[self.ticker]["is_testnet"]:
                key_list = list(self.testnet_protocols.keys())
                value_list = list(self.testnet_protocols.values())
            else:
                key_list = list(self.protocols.keys())
                value_list = list(self.protocols.values())
            if self.ticker in key_list:
                return self.ticker

            if self.ticker == "RBTC":
                token_type = "RSK Smart Bitcoin"
            if token_type in value_list:
                i = value_list.index(token_type)
                return key_list[i]
            logger.warning(f"{token_type} not in value_list")
        return None

    def clean_name(self):
        self.data[self.ticker].update({"name": self.coin_data["fname"]})

    def get_generics(self):
        for i in self.coin_data:
            if i not in self.data[self.ticker]:
                self.data[self.ticker].update({i: self.coin_data[i]})

    def get_electrums(self):
        coin = self.ticker.replace("-segwit", "")
        if self.data[self.ticker]["type"] == "QRC-20":
            if self.is_testnet:
                coin = "tQTUM"
            else:
                coin = "QTUM"

        # Only process if this is actually an electrum coin
        if coin in electrum_coins:
            with open(f"{repo_path}/electrums/{coin}", "r") as f:
                electrums = json.load(f)
                    
            if coin in self.electrum_scan_report:
                valid_electrums = []
                current_time_local = time.time()  # Use local time to avoid scope issues
                for x in ["tcp", "ssl", "wss"]:
                    # This also filters ws with tcp/ssl server it is grouped with if valid.
                    if x not in self.electrum_scan_report[coin]:
                        continue
                    for k, v in self.electrum_scan_report[coin][x].items():
                        is_server_online = (v["last_connection"] > 0 and current_time_local - v["last_connection"] < 604800)  # 1 week grace period
                        
                        if is_server_online:
                            for electrum in electrums:
                                # Get disabled protocols for this electrum
                                disabled_protocols = [p.upper() for p in electrum.get("disabled", [])]
                                
                                # Check URL match for current protocol
                                e = deepcopy(electrum)
                                if "url" in e:
                                    if e["url"] == k:
                                        # Skip if this protocol is disabled
                                        if x.upper() not in disabled_protocols:
                                            e["protocol"] = x.upper()
                                            if "ws_url" in e:
                                                del e["ws_url"]
                                            if "disabled" in e:
                                                del e["disabled"]
                                            valid_electrums.append(e)
                                            
                                            # Track server uptime
                                            if self.uptime_tracker:
                                                contact_info = electrum.get("contact")
                                                self.uptime_tracker.update_server_status(
                                                    self.ticker, k, True, contact_info
                                                )
                                # Check WSS URL match
                                if "ws_url" in electrum:
                                    e = deepcopy(electrum)
                                    if e["ws_url"] == k:
                                        # Skip if WSS is disabled
                                        if "WSS" not in disabled_protocols:
                                            e["protocol"] = "WSS"
                                            e["url"] = k
                                            del e["ws_url"]
                                            if "disabled" in e:
                                                del e["disabled"]
                                            valid_electrums.append(e)
                                            
                                            # Track server uptime for WSS
                                            if self.uptime_tracker:
                                                contact_info = electrum.get("contact")
                                                self.uptime_tracker.update_server_status(
                                                    self.ticker, k, True, contact_info
                                                )
                        else:
                            # Track offline servers
                            if self.uptime_tracker:
                                for electrum in electrums:
                                    if ("url" in electrum and electrum["url"] == k) or \
                                       ("ws_url" in electrum and electrum["ws_url"] == k):
                                        contact_info = electrum.get("contact")
                                        self.uptime_tracker.update_server_status(
                                            self.ticker, k, False, contact_info
                                        )
                
                if len(valid_electrums) > 0:
                    valid_electrums = sort_dicts_list(valid_electrums, "url")                 
                    self.data[self.ticker].update({"electrum": valid_electrums})
                    
                    # Track coin as online
                    if self.uptime_tracker:
                        self.uptime_tracker.update_coin_status(self.ticker, True)
                else:
                    logger.warning(f"No working electrum servers found for {self.ticker}, marking as delisted")
                    self.data[self.ticker].update({"electrum": [], "delisted": True})
                    
                    # Track coin as offline
                    if self.uptime_tracker:
                        self.uptime_tracker.update_coin_status(self.ticker, False)
            elif self.coin_type in ["SIA"]:
                # SIA uses static nodes list
                self.data[self.ticker].update({"nodes": electrums})
            else:
                logger.warning(f"{coin} not found in electrum_scan_report!")
        # For non-electrum coins (EVM, Tendermint), nodes are handled in get_swap_contracts()

    def get_swap_contracts(self):
        contract_data = None

        if self.ticker in ethereum_coins:
            with open(f"{repo_path}/ethereum/{self.ticker}", "r") as f:
                contract_data = json.load(f)

        elif self.data[self.ticker]["type"] in ["TENDERMINT", "TENDERMINTTOKEN"]:
            with open(f"{repo_path}/tendermint/{self.parent_coin}", "r") as f:
                contract_data = json.load(f)

        elif self.ticker not in electrum_coins:
            if self.parent_coin not in [None]:
                with open(f"{repo_path}/ethereum/{self.parent_coin}", "r") as f:
                    contract_data = json.load(f)

        if contract_data:
            if "swap_contract_address" in contract_data:
                self.data[self.ticker].update(
                    {"swap_contract_address": contract_data["swap_contract_address"]}
                )
            if "fallback_swap_contract" in contract_data:
                self.data[self.ticker].update(
                    {"fallback_swap_contract": contract_data["fallback_swap_contract"]}
                )
            if "rpc_nodes" in contract_data:
                if self.data[self.ticker]["type"] in ["TENDERMINT", "TENDERMINTTOKEN"]:
                    key = "rpc_urls"
                else:
                    key = "nodes"
                    
                # Filter nodes based on scan report
                # For token coins, check parent chain connectivity instead of the token itself
                scan_coin = self.get_scan_coin_for_status_check()
                valid_nodes = []
                
                if scan_coin in electrum_scan_report:
                    # If parent chain is working, inherit all configured nodes for token
                    if self.ticker.endswith(("-QRC20", "-ERC20", "-BEP20", "-PLG20", "-AVX20")):
                        # For token coins, check if parent chain has working nodes
                        parent_has_working_nodes = False
                        for protocol in ["ssl", "wss", "tcp"]:
                            for node_url, node_data in electrum_scan_report[scan_coin][protocol].items():
                                if (current_time - node_data["last_connection"] < 604800):
                                    parent_has_working_nodes = True
                                    break
                            if parent_has_working_nodes:
                                break
                        
                        if parent_has_working_nodes:
                            # Parent chain is working, use all configured nodes for this token
                            valid_nodes = contract_data["rpc_nodes"]
                            logger.debug(f"Token {self.ticker} inheriting connectivity from working parent chain {scan_coin}")
                        else:
                            logger.warning(f"Parent chain {scan_coin} for token {self.ticker} has no working nodes")
                    else:
                        # For non-token coins, check each node individually
                        for node in contract_data["rpc_nodes"]:
                            node_url = node["url"]
                            # Check if this node appears in the scan report as working
                            node_found_working = False
                            
                            # Check in ssl section (HTTPS nodes)
                            if node_url in electrum_scan_report[scan_coin]["ssl"]:
                                node_data = electrum_scan_report[scan_coin]["ssl"][node_url]
                                if (current_time - node_data["last_connection"] < 604800):  # 1 week grace period
                                    valid_nodes.append(node)
                                    node_found_working = True
                            
                            # Check in wss section (WSS nodes) 
                            if not node_found_working and "ws_url" in node:
                                ws_url = node["ws_url"]
                                if ws_url in electrum_scan_report[scan_coin]["wss"]:
                                    node_data = electrum_scan_report[scan_coin]["wss"][ws_url]
                                    if (current_time - node_data["last_connection"] < 604800):  # 1 week grace period
                                        valid_nodes.append(node)
                                        node_found_working = True
                            
                            # Check in tcp section (HTTP nodes)
                            if not node_found_working and node_url in electrum_scan_report[scan_coin]["tcp"]:
                                node_data = electrum_scan_report[scan_coin]["tcp"][node_url]
                                if (current_time - node_data["last_connection"] < 604800):  # 1 week grace period
                                    valid_nodes.append(node)
                                    node_found_working = True
                            
                            # Track server uptime for RPC nodes
                            if self.uptime_tracker:
                                contact_info = node.get("contact")
                                self.uptime_tracker.update_server_status(
                                    self.ticker, node_url, node_found_working, contact_info
                                )
                                
                                # Also track WSS URL if present
                                if "ws_url" in node:
                                    ws_url = node["ws_url"]
                                    ws_working = ws_url in electrum_scan_report[scan_coin]["wss"] and \
                                               (current_time - electrum_scan_report[scan_coin]["wss"][ws_url]["last_connection"] < 604800)
                                    self.uptime_tracker.update_server_status(
                                        self.ticker, ws_url, ws_working, contact_info
                                    )
                                    
                            if not node_found_working:
                                logger.warning(f"Node {node_url} for {self.ticker} not found working in scan report")
                else:
                    # If not in scan report, use all nodes (fallback for coins not scanned)
                    valid_nodes = contract_data["rpc_nodes"]
                    logger.warning(f"{scan_coin} not found in electrum_scan_report, using all configured nodes for {self.ticker}")
                
                if valid_nodes:
                    values = sort_dicts_list(valid_nodes, "url")       
                    self.data[self.ticker].update({key: values})
                else:
                    logger.warning(f"No working nodes found for {self.ticker}, marking as delisted")
                    self.data[self.ticker].update({key: [], "delisted": True})

    def get_explorers(self):
        explorers = None
        coin = self.ticker.replace("-segwit", "")
        if coin in explorer_coins:
            with open(f"{repo_path}/explorers/{coin}", "r") as f:
                explorers = json.load(f)

        elif self.parent_coin in explorer_coins:
            with open(f"{repo_path}/explorers/{self.parent_coin}", "r") as f:
                explorers = json.load(f)

        if explorers:
            for x in explorers:
                for p in explorer_paths:
                    if x.find(p) > -1:
                        self.data[self.ticker].update(explorer_paths[p])
                        break

            self.data[self.ticker].update({"explorer_url": explorers[0]})
            for i in [
                ("explorer_tx_url", "tx/"),
                ("explorer_address_url", "address/"),
                ("explorer_block_url", "block/"),
            ]:
                if i[0] not in self.data[self.ticker]:
                    self.data[self.ticker].update({i[0]: i[1]})
                elif self.data[self.ticker][i[0]] == "":
                    self.data[self.ticker].update({i[0]: i[1]})


def parse_coins_repo(electrum_scan_report, uptime_tracker=None):
    ensure_chainids()
    errors = []
    coins_config = {}
    with open(f"{repo_path}/coins", "r") as f:
        coins_data = json.load(f)

    for item in coins_data:
        config = CoinConfig(item, electrum_scan_report, uptime_tracker)
        config.get_generics()
        config.get_protocol_info()
        config.clean_name()
        config.get_swap_contracts()
        config.get_electrums()
        config.get_explorers()
        config.is_smartchain()
        config.is_wallet_only()
        config.get_address_format()
        config.get_rewards_info()
        config.get_alias_ticker()
        config.get_asset()
        config.get_forex_id()
        config.get_coinpaprika_id()
        config.get_coingecko_id()
        config.get_livecoinwatch_id()
        config.get_binance_id()
        config.get_hd_info()
        config.get_links()
        coins_config.update(config.data)

    delisted_coins = []
    working_coins = []
    for coin in coins_config:
        if not coins_config[coin]["explorer_url"]:
            logger.warning(f"{coin} has no explorers!")
        
        # Check if coin is delisted (no working nodes/electrums)
        if coins_config[coin].get("delisted", False):
            delisted_coins.append(coin)
        else:
            # Check if coin has any connection methods
            has_connection = False
            for field in ["nodes", "electrum", "light_wallet_d_servers", "light_wallet_d_servers_wss", "rpc_urls"]:
                if field in coins_config[coin]:
                    if coins_config[coin][field]:  # Non-empty list
                        has_connection = True
                        break
            
            if has_connection:
                working_coins.append(coin)
            else:
                # No working connections found, mark as delisted
                coins_config[coin]["delisted"] = True
                delisted_coins.append(coin)

    logger.info(f"Working coins: {len(working_coins)}")
    logger.warning(f"Delisted coins (no working connections): {len(delisted_coins)} - {delisted_coins}")
    
    # Update scan summary with delisted coins if it exists
    scan_summary_path = f"{script_path}/scan_summary.json"
    if os.path.exists(scan_summary_path):
        try:
            with open(scan_summary_path, "r") as f:
                scan_summary = json.load(f)
            
            scan_summary["delisted_coins"] = delisted_coins
            
            with open(scan_summary_path, "w") as f:
                json.dump(scan_summary, f, indent=4)
        except Exception as e:
            logger.warning(f"Failed to update scan summary: {e}")
    
    if errors:
        logger.error(f"Errors:")
        for error in errors:
            logger.error(error)
    return coins_config, delisted_coins


def get_desktop_repo_coins_data():
    """for this to work, you need atomicdex-desktop cloned into
    the same folder as you cloned the coins repo."""
    desktop_coins_folder = "../../atomicDEX-Desktop/assets/config/"
    contents = os.listdir(desktop_coins_folder)
    for f in contents:
        if f.endswith("coins.json"):
            coins_fn = f
    with open(f"{repo_path}/atomicDEX-Desktop/assets/config/{coins_fn}", "r") as f:
        return json.load(f)


def filter_ssl(coins_config):
    coins_config_ssl = {}
    for coin in coins_config:
        # Skip delisted coins
        if coins_config[coin].get("delisted", False):
            continue
            
        coins_config_ssl.update({coin: coins_config[coin]})
        if "electrum" in coins_config[coin]:
            electrums = []
            for i in coins_config[coin]["electrum"]:
                if "protocol" in i:
                    if i["protocol"] == "SSL":
                        electrums.append(i)
            if len(coins_config_ssl[coin]["electrum"]) == 0:
                del coins_config_ssl[coin]
            else:
                electrums = filter_duplicate_domains(electrums)
                coins_config_ssl[coin]["electrum"] = electrums

        if "nodes" in coins_config[coin]:
            coins_config_ssl[coin]["nodes"] = [
                i for i in coins_config[coin]["nodes"] if i["url"].startswith("https")
            ]

        if "light_wallet_d_servers" in coins_config[coin]:
            coins_config_ssl[coin]["light_wallet_d_servers"] = [
                i
                for i in coins_config[coin]["light_wallet_d_servers"]
                if i.startswith("https")
            ]

    with open(f"{script_path}/coins_config_ssl.json", "w+") as f:
        json.dump(coins_config_ssl, f, indent=4)
    return coins_config_ssl


def item_exists(i, electrums):
    for e in electrums:
        if "url" in e and "url" in i:
            if i["url"] == e["url"]:
                return True
        if "ws_url" in e and "ws_url" in i:
            if i["ws_url"] == e["ws_url"]:
                return True
    return False


def filter_duplicate_domains(electrums):
    domains = {}
    for i in electrums:
        domain = i["url"].split(":")[0]
        if domain not in domains:
            domains.update({domain: {i['protocol']: i['url']}})
        else:
            domains[domain].update({i['protocol']: i['url']})
    for i in domains:
        if "SSL" in domains[i] and "TCP" in domains[i]:
            for e in electrums:
                if e["url"].startswith(i) and e["protocol"] == "TCP":
                    electrums.remove(e)
    return electrums
    

    

def filter_tcp(coins_config, coins_config_ssl):
    coins_config_tcp = {}
    for coin in coins_config:
        # Skip delisted coins
        if coins_config[coin].get("delisted", False):
            continue
            
        coins_config_tcp.update({coin: coins_config[coin]})
        # Omit komodo_proxy: true nodes - these are web only.
        if "nodes" in coins_config[coin]:
            coins_config_tcp[coin]["nodes"] = [
                i for i in coins_config[coin]["nodes"] if "komodo_proxy" not in i
            ]
        if "electrum" in coins_config[coin]:
            electrums = []
            # Prefer SSL
            if coin in coins_config_ssl:
                if len(coins_config_ssl[coin]["electrum"]) > 0:
                    electrums = coins_config_ssl[coin]["electrum"]
            for i in coins_config[coin]["electrum"]:
                if "komodo_proxy" in i:
                    if i["komodo_proxy"] == True:
                        continue
                if item_exists(i, electrums) == False:
                    if "protocol" in i:
                        # SSL is ok for legacy desktop so we allow them, else some coins with only SSL will be omited.
                        if i["protocol"] != "WSS":
                            electrums.append(i)
                    else:
                        electrums.append(i)

            if len(coins_config_tcp[coin]["electrum"]) == 0:
                del coins_config_tcp[coin]
            else:
                electrums = filter_duplicate_domains(electrums)
                coins_config_tcp[coin]["electrum"] = electrums

    with open(f"{script_path}/coins_config_tcp.json", "w+") as f:
        json.dump(coins_config_tcp, f, indent=4)
    return coins_config_tcp


def filter_wss(coins_config):
    coins_config_wss = {}
    for coin in coins_config:
        # Skip delisted coins
        if coins_config[coin].get("delisted", False):
            continue
            
        if "electrum" in coins_config[coin]:
            electrums = []
            for electrum_server in coins_config[coin]["electrum"]:
                if "protocol" in electrum_server:
                    if electrum_server["protocol"] == "WSS":
                        electrums.append(electrum_server)
                else:
                    logger.warning(f"No protocol data in {electrum_server}")
            if len(electrums) > 0:
                coins_config_wss.update({coin: coins_config[coin]})
                coins_config_wss[coin]["electrum"] = electrums
        elif "nodes" in coins_config[coin]:
            nodes = []
            for node in coins_config[coin]["nodes"]:
                if "ws_url" in node:
                    nodes.append(node)
            if len(nodes) > 0:
                coins_config_wss.update({coin: coins_config[coin]})
                coins_config_wss[coin]["nodes"] = nodes
        elif "light_wallet_d_servers_wss" in coins_config[coin]:
            coins_config_wss[coin]["light_wallet_d_servers_wss"] = [
                server_url
                for server_url in coins_config[coin]["light_wallet_d_servers_wss"]
                if server_url.startswith("https")
            ]
        else:
            logger.warning(f"{coin} not checked for WSS filter yet, including anyway.")
            coins_config_wss.update({coin: coins_config[coin]})

    with open(f"{script_path}/coins_config_wss.json", "w+") as f:
        json.dump(coins_config_wss, f, indent=4)
    return coins_config_wss


def generate_binance_api_ids(coins_config):
    kdf_coins = coins_config.keys()
    r = requests.get("https://defi-stats.komodo.earth/api/v3/binance/ticker_price")
    binance_tickers = r.json()
    pairs = []
    for ticker in binance_tickers:
        pair = ticker["symbol"]
        for quote in binance_quote_tickers:
            if ticker["symbol"].startswith(quote):
                pair = (quote, ticker["symbol"].replace(quote, ""))
                break
            elif ticker["symbol"].endswith(quote):
                pair = (ticker["symbol"].replace(quote, ""), quote)
                break
            
        pairs.append(pair)
    unknown_ids = [i for i in pairs if isinstance(i, str)]
    known_ids = [i for i in pairs if isinstance(i, tuple)]

    if unknown_ids:
        logger.warning(f"Unknown ids: {unknown_ids}")

    api_ids = {}
    known_id_coins = list(set([i[0] for i in known_ids] + [i[1] for i in known_ids]))
    for coin in kdf_coins:
        ticker = coin.split("-")[0]
        if ticker in known_id_coins:
            if ticker not in BINANCE_DELISTED_COINS and ticker not in MISMATCHED_IDS:
                api_ids.update({coin: ticker})

    with open(f"{repo_path}/api_ids/binance_ids.json", "w") as f:
        json.dump(api_ids, f, indent=4)

    # To use for candlestick data, reference api_ids/binance_ids.json
    # to get the base and quote id for a pair then concatentate them with no separator
    # Example candlestick url: https://api.binance.com/api/v3/klines?symbol=BNBBTC&interval=1d&limit=1000
    # Valid interval values are listed at https://binance-docs.github.io/apidocs/spot/en/#public-api-definitions


def sort_dict(d):
    return {k: d[k] for k in sorted(d)}

def sort_dicts_list(data, sort_key):
    return sorted(data, key=lambda x: x[sort_key])


def normalize_coin_name(name):
    """
    Remove common protocol suffixes from coin names for better icon matching.
    Also splits by separators and uses first part for broader matching.
    Examples: 
    - "BABYDOGE-BEP20" -> "babydoge"
    - "babydoge_bep20" -> "babydoge"
    - "1INCH-ERC20" -> "1inch"
    - "SOME-COMPLEX_NAME" -> "some"
    """
    name = name.lower()
    original_name = name
    
    # First try specific protocol suffix removal
    suffixes_to_remove = [
        # Dash-separated suffixes
        '-bep20', '-erc20', '-plg20', '-avx20', '-krc20', '-hrc20', 
        '-qrc20', '-arb20', '-test', '-testnet',
        # Underscore-separated suffixes  
        '_bep20', '_erc20', '_plg20', '_avx20', '_krc20', '_hrc20',
        '_qrc20', '_arb20', '_test', '_testnet'
    ]
    
    for suffix in suffixes_to_remove:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    
    # Also try splitting by separators and using first part
    # This catches any prefix before - or _ separators
    for separator in ['-', '_']:
        if separator in original_name:
            first_part = original_name.split(separator)[0]
            # Return the shorter/more general version between suffix removal and first part
            if len(first_part) <= len(name):
                return first_part
    
    return name


def generate_spritemap():
    icon_size = 128
    icons_dir = f"{repo_path}/icons"
    spritemap_img_path = f"{script_path}/spritemap.png"
    spritemap_json_path = f"{script_path}/spritemap.json"

    # Read coins file directly
    with open(f"{repo_path}/coins", "r") as f:
        coins_data = json.load(f)
    
    # Get all coin tickers and names from the coins file
    coin_tickers = set()
    coin_names = set()
    coin_fnames = set()  # Add set for fname values
    icon_name_to_ticker = {}
    
    for coin_entry in coins_data:
        ticker = coin_entry["coin"]
        coin_tickers.add(ticker.lower())
        
        # Map ticker to itself
        icon_name_to_ticker[ticker.lower()] = ticker
        
        # Also add normalized version of ticker (removes protocol suffixes)
        normalized_ticker = normalize_coin_name(ticker)
        if normalized_ticker != ticker.lower():
            coin_tickers.add(normalized_ticker)
            icon_name_to_ticker[normalized_ticker] = ticker
        
        # Also map name if available
        if "name" in coin_entry:
            name = coin_entry["name"].lower()
            coin_names.add(name)
            icon_name_to_ticker[name] = ticker
            
            # Also add normalized version of name
            normalized_name = normalize_coin_name(coin_entry["name"])
            if normalized_name != name:
                coin_names.add(normalized_name)
                icon_name_to_ticker[normalized_name] = ticker
        
        # Also map fname if available
        if "fname" in coin_entry:
            fname = coin_entry["fname"].lower()
            coin_fnames.add(fname)
            icon_name_to_ticker[fname] = ticker
            
            # Also add normalized version of fname
            normalized_fname = normalize_coin_name(coin_entry["fname"])
            if normalized_fname != fname:
                coin_fnames.add(normalized_fname)
                icon_name_to_ticker[normalized_fname] = ticker
    
    # Get available icons
    available_icons = [f for f in os.listdir(icons_dir) if f.endswith('.png') and f != 'spritemap.png']
    
    # Filter icons to match coin tickers, names, or fnames
    icons = []
    for icon_file in available_icons:
        icon_name = os.path.splitext(icon_file)[0].lower()
        # Try to match by ticker first, then by name, then by fname
        if icon_name in coin_tickers or icon_name in coin_names or icon_name in coin_fnames:
            icons.append(icon_file)
    
    # Sort alphabetically
    icons.sort()
    
    # Track unmatched items for reporting
    unmatched_report = {
        'icons_not_included': [],
        'coin_values_without_direct_icons_match': [],
        'names_without_direct_icons_match': [],
        'fnames_without_direct_icons_match': []
    }
    
    # Find icons that weren't included (exist but don't match any coin)
    included_icon_names = {os.path.splitext(icon)[0].lower() for icon in icons}
    for icon_file in available_icons:
        icon_name = os.path.splitext(icon_file)[0].lower()
        if icon_name not in included_icon_names:
            unmatched_report['icons_not_included'].append(icon_file)
    
    # Find coin data that doesn't have matching icons
    for coin_ticker in coin_tickers:
        if coin_ticker not in included_icon_names:
            unmatched_report['coin_values_without_direct_icons_match'].append(coin_ticker)
    
    for coin_name in coin_names:
        if coin_name not in included_icon_names:
            unmatched_report['names_without_direct_icons_match'].append(coin_name)
    
    for coin_fname in coin_fnames:
        if coin_fname not in included_icon_names:
            unmatched_report['fnames_without_direct_icons_match'].append(coin_fname)
    
    # Sort all unmatched lists for consistent output
    for key in unmatched_report:
        unmatched_report[key].sort()
    
    logger.info(f"Coin tickers from coins file: {len(coin_tickers)} (first 10): {sorted(list(coin_tickers))[:10]}")
    logger.info(f"Coin names from coins file: {len(coin_names)} (first 10): {sorted(list(coin_names))[:10]}")
    logger.info(f"Coin fnames from coins file: {len(coin_fnames)} (first 10): {sorted(list(coin_fnames))[:10]}")  # Add logging for fnames
    logger.info(f"Available icons count: {len(available_icons)} (first 10): {sorted(available_icons)[:10]}")
    logger.info(f"Matched icons count: {len(icons)} (first 10): {sorted(icons)[:10]}")
    
    # Log unmatched counts
    logger.info(f"Icons not included in spritemap: {len(unmatched_report['icons_not_included'])}")
    logger.info(f"Coin tickers without direct icons match: {len(unmatched_report['coin_values_without_direct_icons_match'])}")  
    logger.info(f"Coin names without direct icons match: {len(unmatched_report['names_without_direct_icons_match'])}")
    logger.info(f"Coin fnames without direct icons match: {len(unmatched_report['fnames_without_direct_icons_match'])}")
    
    #Save unmatched report to JSON file
    unmatched_report_path = f"{script_path}/spritemap_unmatched_report.json"
    try:
        with open(unmatched_report_path, 'w') as f:
            json.dump(unmatched_report, f, indent=4)
        logger.info(f"Generated unmatched items report at {unmatched_report_path}")
    except Exception as e:
        logger.error(f"Failed to save unmatched report: {e}")

    if not icons:
        logger.info("No icons found for valid coins to generate a spritemap.")
        return

    # Get the list of matched coin tickers for logging
    matched_coin_tickers = [icon_name_to_ticker.get(os.path.splitext(icon)[0].lower(), os.path.splitext(icon)[0].upper()) for icon in icons]
    logger.info(f"Generating spritemap with {len(icons)} icons for coins: {sorted(matched_coin_tickers)}")

    # Use more efficient rectangular packing instead of square grid
    # Calculate optimal dimensions to minimize wasted space
    total_area = len(icons) * icon_size * icon_size
    aspect_ratio = 1.2  # Slightly rectangular for better mobile/desktop fit
    ideal_width = math.sqrt(total_area * aspect_ratio)
    grid_cols = max(1, math.ceil(ideal_width / icon_size))
    grid_rows = math.ceil(len(icons) / grid_cols)
    
    spritemap_width = grid_cols * icon_size
    spritemap_height = grid_rows * icon_size

    logger.info(f"Spritemap dimensions: {spritemap_width}x{spritemap_height} ({grid_cols}x{grid_rows} grid)")

    spritemap = Image.new('RGBA', (spritemap_width, spritemap_height), (0, 0, 0, 0))
    coordinates = {}
    failed_icons = []

    processed_count = 0
    skipped_conversions = 0
    for i, icon_file in enumerate(icons):
        icon_path = os.path.join(icons_dir, icon_file)
        try:
            with Image.open(icon_path) as icon:
                original_width, original_height = icon.size
                
                # Skip format conversion if already RGBA (common for oxipng optimized PNGs)
                if icon.mode != 'RGBA':
                    icon = icon.convert('RGBA')
                else:
                    skipped_conversions += 1
                
                # Fast path for correctly sized images (skip all processing)
                if original_width == icon_size and original_height == icon_size:
                    # Image is already perfect size, no processing needed
                    processed_icon = icon
                else:
                    # Use padding instead of stretching to maintain aspect ratio
                    aspect_ratio = original_width / original_height
                    
                    if aspect_ratio > 1:  # Wider than tall
                        new_width = min(icon_size, original_width)
                        new_height = int(new_width / aspect_ratio)
                    else:  # Taller than wide or square
                        new_height = min(icon_size, original_height)
                        new_width = int(new_height * aspect_ratio)
                    
                    # Only resize if different from original (avoid unnecessary processing)
                    if new_width != original_width or new_height != original_height:
                        icon = icon.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Create transparent canvas and center the image
                    canvas = Image.new('RGBA', (icon_size, icon_size), (0, 0, 0, 0))
                    paste_x = (icon_size - new_width) // 2
                    paste_y = (icon_size - new_height) // 2
                    canvas.paste(icon, (paste_x, paste_y), icon)
                    processed_icon = canvas
                    
                    if original_width < icon_size or original_height < icon_size:
                        logger.info(f"Icon {icon_file} padded from {original_width}x{original_height} to {icon_size}x{icon_size} (resized to {new_width}x{new_height})")
                    processed_count += 1
                
                x = (i % grid_cols) * icon_size
                y = (i // grid_cols) * icon_size
                spritemap.paste(processed_icon, (x, y), processed_icon)  # Use icon as mask for proper alpha blending
                
                icon_name = os.path.splitext(icon_file)[0]  # Remove .png extension
                coordinates[icon_name] = {
                    'x': x,
                    'y': y,
                    'width': icon_size,
                    'height': icon_size
                }
        except Exception as e:
            logger.warning(f"Failed to process icon {icon_file}: {e}")
            failed_icons.append(icon_file)

    if failed_icons:
        logger.warning(f"Failed to process {len(failed_icons)} icons: {failed_icons}")

    # Log optimization stats
    logger.info(f"Processed {processed_count} icons (resized/padded), skipped format conversion for {skipped_conversions} already-RGBA icons")

    # Save with minimal compression since input images are already oxipng optimized
    # Using compress_level=1 for faster processing while still getting some compression
    try:
        spritemap.save(spritemap_img_path, 'PNG', optimize=False, compress_level=1)
        logger.info(f"Generated spritemap at {spritemap_img_path} (input images already oxipng optimized)")
        
        # Run oxipng on the final spritemap for maximum optimization
        try:
            import subprocess
            result = subprocess.run(['oxipng', '-o', '6', '--strip', 'safe', spritemap_img_path], 
                                  capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                logger.info(f"Post-processed spritemap with oxipng for optimal compression")
            else:
                logger.info(f"oxipng not available or failed, using PIL compression only")
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
            logger.info(f"oxipng post-processing skipped (not available or failed): {e}")
            
    except Exception as e:
        logger.error(f"Failed to save spritemap: {e}")
        return
        
    # Save coordinates with metadata
    spritemap_data = {
        'metadata': {
            'icon_size': icon_size,
            'grid_cols': grid_cols,
            'grid_rows': grid_rows,
            'total_icons': len(coordinates),
            'spritemap_width': spritemap_width,
            'spritemap_height': spritemap_height,
            'generated_at': int(current_time)
        },
        'coordinates': coordinates
    }
    
    try:
        with open(spritemap_json_path, 'w') as f:
            json.dump(spritemap_data, f, indent=4)
        logger.info(f"Generated spritemap coordinates at {spritemap_json_path}")
    except Exception as e:
        logger.error(f"Failed to save spritemap coordinates: {e}")


if __name__ == "__main__":
    generate_spritemap_only = len(sys.argv) > 1 and "spritemap" in sys.argv
    
    # If only generating spritemap, try to use existing config files to avoid long electrum scan
    if generate_spritemap_only:
        config_files = [
            f"{script_path}/coins_config.json",
            f"{script_path}/coins_config_ssl.json", 
            f"{script_path}/coins_config_tcp.json",
            f"{script_path}/coins_config_wss.json"
        ]
        
        # Check if all required config files exist
        all_files_exist = all(os.path.exists(f) for f in config_files)
        
        if all_files_exist:
            try:
                logger.info("Generating spritemap using existing config files...")
                with open(f"{script_path}/coins_config.json", "r") as f:
                    coins_config = json.load(f)
                with open(f"{script_path}/coins_config_ssl.json", "r") as f:
                    coins_config_ssl = json.load(f)
                with open(f"{script_path}/coins_config_tcp.json", "r") as f:
                    coins_config_tcp = json.load(f)
                with open(f"{script_path}/coins_config_wss.json", "r") as f:
                    coins_config_wss = json.load(f)
                
                # Validate that configs have data
                if coins_config and (coins_config_ssl or coins_config_tcp or coins_config_wss):
                    generate_spritemap()
                    logger.info("Spritemap generation completed successfully!")
                    sys.exit()
                else:
                    logger.warning("Config files exist but appear to be empty, running full scan...")
                    
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Error reading config files ({e}), running full scan to regenerate...")
        else:
            missing_files = [f for f in config_files if not os.path.exists(f)]
            logger.warning(f"Missing config files: {missing_files}")
            logger.warning("Running full scan to generate missing configs...")
        
        # Fall through to full processing if cached files don't work
    
    skip_scan = False
    if len(sys.argv) > 1:
        if sys.argv[1] == "no-scan":
            skip_scan = True
    if skip_scan is False:
        electrum_scan_report = get_electrums_report()
    else:
        # Use existing scan data
        with open(f"{script_path}/electrum_scan_report.json", "r") as f:
            electrum_scan_report = json.load(f)
        
        # Note: scan_summary will be generated after uptime tracker initialization

    # Initialize uptime tracking
    uptime_tracker = UptimeTracker(f"{script_path}/uptime_history.json")
    
    # Generate scan summary with uptime tracker as source of truth
    from scan_electrums import generate_scan_summary
    current_time = int(time.time())
    scan_summary = generate_scan_summary(electrum_scan_report, current_time, uptime_tracker)
    with open(f"{script_path}/scan_summary.json", "w") as f:
        json.dump(scan_summary, f, indent=4)
    
    coins_config, delisted_coins = parse_coins_repo(electrum_scan_report, uptime_tracker)
    
    # Generate and log uptime alerts
    alerts = uptime_tracker.generate_alerts()
    if alerts:
        logger.warning("=== UPTIME ALERTS ===")
        for alert in alerts:
            if "CRITICAL" in alert:
                logger.error(alert)
            else:
                logger.warning(alert)
        logger.warning("=== END UPTIME ALERTS ===")
    
    # Save uptime data
    uptime_tracker.save()
    
    # Always save the complete config (including delisted coins with empty node lists)
    with open(f"{script_path}/coins_config.json", "w+") as f:
        json.dump(coins_config, f, indent=4)
    
    # Also save an unfiltered version for backwards compatibility
    with open(f"{script_path}/coins_config_unfiltered.json", "w+") as f:
        json.dump(coins_config, f, indent=4)
    
    generate_binance_api_ids(coins_config)
        
    coins_config_ssl = filter_ssl(deepcopy(coins_config))
    coins_config_wss = filter_wss(deepcopy(coins_config))
    coins_config_tcp = filter_tcp(deepcopy(coins_config), coins_config_ssl)

    working_coins_count = 0
    for coin in coins_config:
        r = f"{coin}: [SSL {coin in coins_config_ssl}] [TCP {coin in coins_config_tcp}] [WSS {coin in coins_config_wss}]"
        if coins_config[coin].get("delisted", False):
            logger.warning(f"{coin}: [DELISTED - No working nodes]")
        elif (
            coin in coins_config_tcp
            and coin in coins_config_ssl
            and coin in coins_config_wss
        ):
            logger.info(r)
            working_coins_count += 1
        else:
            logger.calc(r)
            working_coins_count += 1
    
    logger.info(f"\nTotal coins: {len(coins_config)}")
    logger.info(f"Working coins: {working_coins_count}")
    logger.info(f"Delisted coins: {len(delisted_coins)}")
    logger.info(f"Total coins with SSL: {len(coins_config_ssl)}")
    logger.info(f"Total coins with TCP: {len(coins_config_tcp)}")
    logger.info(f"Total coins with WSS: {len(coins_config_wss)}")
    
    # Generate spritemap at the end of execution
    if generate_spritemap_only:
        logger.info("Generating spritemap after full processing (fallback)...")
        generate_spritemap()
        logger.info("Spritemap generation completed successfully!")
        sys.exit()
    else:
        logger.info("Generating spritemap after full processing...")
        generate_spritemap()
