#!/usr/bin/env python3
import os
import sys
import ssl
import json
import time
import socket
import threading
import asyncio
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse
from websockets.asyncio.client import connect
from logger import logger


ignore_list = []
passed_electrums = {}
failed_electrums = {}
passed_electrums_ssl = {}
failed_electrums_ssl = {}
passed_electrums_wss = {}
failed_electrums_wss = {}
passed_tendermint = {}
failed_tendermint = {}
passed_tendermint_wss = {}
failed_tendermint_wss = {}
passed_ethereum = {}
failed_ethereum = {}
passed_ethereum_wss = {}
failed_ethereum_wss = {}
socket.setdefaulttimeout(10)
script_path = os.path.abspath(os.path.dirname(__file__))
repo_path = script_path.replace("/utils", "")
os.chdir(script_path)




class ElectrumServer:
    __slots__ = ("coin", "url", "port", "protocol", "result", "blockheight", "last_connection")
    
    def __init__(self, coin, url, port, protocol):
        self.coin = coin
        self.url = url
        self.port = port
        self.protocol = protocol
        self.result = None
        self.blockheight = -1
        self.last_connection = -1

    def tcp(self, method, params=None):
        if params:
            params = [params] if type(params) is not list else params
        try:
            with socket.create_connection((self.url, self.port)) as sock:
                # Handshake
                payload = {"id": 0, "method": "server.version", "params": ["kmd_coins_repo", ["1.4", "1.6"]]}
                sock.send(json.dumps(payload).encode() + b'\n')
                time.sleep(1)
                resp = sock.recv(999999)[:-1].decode()
                # logger.info(f"TCP {self.url}:{self.port} {resp}")
                # Request
                payload = {"id": 0, "method": method}
                if params:
                    payload.update({"params": params})
                sock.send(json.dumps(payload).encode() + b'\n')
                time.sleep(1)
                resp = sock.recv(999999)[:-1].decode()
                resp = resp.splitlines()
                if len(resp) > 0:
                    resp = resp[-1]
                return resp
        except Exception as e:
            return e

    def ssl(self, method, params=None):
        if params:
            params = [params] if type(params) is not list else params
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        try:
            with socket.create_connection((self.url, self.port)) as sock:
                with context.wrap_socket(sock, server_hostname=self.url) as ssock:
                    # Handshake
                    payload = {"id": 0, "method": "server.version", "params": ["kmd_coins_repo", ["1.4", "1.6"]]}
                    ssock.send(json.dumps(payload).encode() + b'\n')
                    time.sleep(1)
                    resp = ssock.recv(999999)[:-1].decode()
                    # logger.info(f"SSL {self.url}:{self.port} {resp}")
                    # Request                    
                    payload = {"id": 0, "method": method}
                    if params:
                        payload.update({"params": params})
                    ssock.send(json.dumps(payload).encode() + b'\n')
                    time.sleep(1)
                    resp = ssock.recv(999999)[:-1].decode()
                    resp = resp.splitlines()
                    if len(resp) > 0:
                        resp = resp[-1]
                    return resp
        except Exception as e:
            return e

    def wss(self, method, params=None):    
        if params:
            params = [params] if type(params) is not list else params
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        try:
            async def connect_and_query():
                async with connect(f"wss://{self.url}:{self.port}", ssl=ssl_context, open_timeout=10, close_timeout=10, ping_timeout=10) as websocket:
                    # Handshake
                    payload = {"id": 0, "method": "server.version", "params": ["kmd_coins_repo", ["1.4", "1.6"]]}
                    await websocket.send(json.dumps(payload))
                    await asyncio.sleep(1)
                    resp = await asyncio.wait_for(websocket.recv(), timeout=7)
                    payload = {"id": 0, "method": method}
                    if params:
                        payload.update({"params": params})
                    await websocket.send(json.dumps(payload))
                    await asyncio.sleep(1)
                    resp = await asyncio.wait_for(websocket.recv(), timeout=7)
                    resp = resp.splitlines()
                    if len(resp) > 0:
                        resp = resp[-1]
                    return resp
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(connect_and_query())
            return response
        except Exception as e:
            return e



def create_komodo_auth_payload(target_uri: str) -> str:
    """
    Create authentication payload for komodo.earth endpoints
    Based on get_auth_resp.py logic
    """
    import os
    
    trusted_peer_id = os.getenv('TRUSTED_PEER_ID', 'ci-cd-trusted-peer')
    
    # Create far future expiration (year 2099)
    expires_at = 4070908800  # 2099-01-01
    
    auth_payload = {
        "signature_bytes": [0] * 64,  # 64-byte dummy signature
        "address": trusted_peer_id,
        "raw_message": {
            "uri": target_uri,
            "body_size": 0,
            "public_key_encoded": [8, 1, 18, 32] + [0] * 32,  # Dummy public key
            "expires_at": expires_at
        }
    }
    
    return json.dumps(auth_payload)


def get_komodo_auth_headers(url: str) -> dict:
    """Get authentication headers for komodo.earth endpoints"""
    if 'node.komodo.earth' in url:
        return {
            "Content-Type": "application/json",
            "X-Auth-Payload": create_komodo_auth_payload(url)
        }
    return {"Content-Type": "application/json"}


def check_ssl_certificate_expiry(url, port=None):
    """Check SSL certificate expiry and return days until expiry."""
    try:
        if port is None:
            # Extract host and port from URL
            parsed = urlparse(url if url.startswith(('http://', 'https://')) else f"https://{url}")
            hostname = parsed.hostname
            port = parsed.port or 443
        else:
            hostname = url
            
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                
                # Parse the expiry date
                not_after = cert['notAfter']
                expiry_date = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                # Make expiry_date timezone-aware (assuming UTC)
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
                current_date = datetime.now(timezone.utc)
                
                days_until_expiry = (expiry_date - current_date).days
                
                # Extract issuer information
                issuer = dict(x[0] for x in cert['issuer'])
                issuer_cn = issuer.get('commonName', 'Unknown')
                
                return {
                    "days_until_expiry": days_until_expiry,
                    "expiry_date": expiry_date.strftime('%Y-%m-%d %H:%M:%S UTC'),
                    "issuer": issuer_cn,
                    "valid": days_until_expiry > 0
                }
    except Exception as e:
        return {"error": str(e), "valid": False}


class TendermintServer:
    __slots__ = ("coin", "url", "ws_url", "api_url", "result", "blockheight", "last_connection", "cert_info")
    
    def __init__(self, coin, url, ws_url=None, api_url=None):
        self.coin = coin
        self.url = url
        self.ws_url = ws_url
        self.api_url = api_url
        self.result = None
        self.blockheight = -1
        self.last_connection = -1
        self.cert_info = None

    def http_rpc(self, method="status", params=None):
        """Query Tendermint RPC via HTTP"""
        try:
            rpc_url = f"{self.url.rstrip('/')}/{method}"
            if params:
                rpc_url += f"?{params}"
            
            headers = get_komodo_auth_headers(self.url)
            response = requests.get(rpc_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def wss_rpc(self):
        """Query Tendermint via WebSocket"""
        if not self.ws_url:
            return {"error": "No WebSocket URL provided"}
        
        try:
            async def connect_and_query():
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                async with connect(self.ws_url, ssl=ssl_context, open_timeout=10) as websocket:
                    # Subscribe to status
                    payload = {
                        "jsonrpc": "2.0",
                        "method": "status",
                        "id": 1
                    }
                    await websocket.send(json.dumps(payload))
                    await asyncio.sleep(1)
                    resp = await asyncio.wait_for(websocket.recv(), timeout=7)
                    return json.loads(resp)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(connect_and_query())
            return response
        except Exception as e:
            return {"error": str(e)}


class EthereumServer:
    __slots__ = ("coin", "url", "ws_url", "result", "blockheight", "last_connection", "cert_info")
    
    def __init__(self, coin, url, ws_url=None):
        self.coin = coin
        self.url = url
        self.ws_url = ws_url
        self.result = None
        self.blockheight = -1
        self.last_connection = -1
        self.cert_info = None

    def http_rpc(self, method="eth_blockNumber", params=None):
        """Query Ethereum RPC via HTTP"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or [],
                "id": 1
            }
            
            headers = get_komodo_auth_headers(self.url)
            response = requests.post(self.url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def wss_rpc(self, method="eth_blockNumber", params=None):
        """Query Ethereum via WebSocket"""
        if not self.ws_url:
            return {"error": "No WebSocket URL provided"}
        
        try:
            async def connect_and_query():
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                async with connect(self.ws_url, ssl=ssl_context, open_timeout=10) as websocket:
                    payload = {
                        "jsonrpc": "2.0",
                        "method": method,
                        "params": params or [],
                        "id": 1
                    }
                    await websocket.send(json.dumps(payload))
                    await asyncio.sleep(1)
                    resp = await asyncio.wait_for(websocket.recv(), timeout=7)
                    return json.loads(resp)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(connect_and_query())
            return response
        except Exception as e:
            return {"error": str(e)}


class scan_thread(threading.Thread):
    def __init__(self, coin, url, port=None, method=None, params=None, protocol='tcp', node_type='electrum', ws_url=None, api_url=None):
        threading.Thread.__init__(self)
        self.coin = coin
        self.url = url
        self.port = port
        self.method = method
        self.params = params
        self.protocol = protocol
        self.node_type = node_type
        self.ws_url = ws_url
        self.api_url = api_url

    def run(self):
        if self.node_type == 'electrum':
            if self.protocol == "ssl":
                thread_electrum_ssl(self.coin, self.url, self.port, self.method, self.params)
            elif self.protocol == "tcp":
                thread_electrum(self.coin, self.url, self.port, self.method, self.params)
            elif self.protocol == "wss":
                thread_electrum_wss(self.coin, self.url, self.port, self.method, self.params)
        elif self.node_type == 'tendermint':
            if self.protocol == "http":
                thread_tendermint(self.coin, self.url, self.api_url)
            elif self.protocol == "wss":
                thread_tendermint_wss(self.coin, self.url, self.ws_url)
        elif self.node_type == 'ethereum':
            if self.protocol == "http":
                thread_ethereum(self.coin, self.url)
            elif self.protocol == "wss":
                thread_ethereum_wss(self.coin, self.url, self.ws_url)


def thread_electrum_wss(coin, url, port, method, params):
    x = ElectrumServer(coin, url, port, "WSS")
    resp = x.wss(method, params)
    el = parse_response(x, resp)

    # Check SSL certificate expiry for WSS connections
    cert_info = check_ssl_certificate_expiry(url, port)
    cert_days = cert_info.get("days_until_expiry") if isinstance(cert_info, dict) else None
    cert_error = cert_info.get("error") if isinstance(cert_info, dict) and "error" in cert_info else None

    if el.blockheight > 0:
        if coin not in passed_electrums_wss:
            passed_electrums_wss.update({coin: {}})
        passed_electrums_wss[coin][f"{url}:{port}"] = {"cert_days": cert_days, "cert_error": cert_error}
        logger.calc(f"[WSS] {coin} {url}:{port} OK! Height: {el.blockheight}, SSL expires in {cert_days} days" if cert_days else f"[WSS] {coin} {url}:{port} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_electrums_wss:
            failed_electrums_wss.update({coin: {}})
        failed_electrums_wss[coin].update({f"{url}:{port}": {"result": el.result, "cert_days": cert_days, "cert_error": cert_error}})
        logger.warning(f"[WSS] {coin} {url}:{port} Failed! {el.result}")


def thread_electrum(coin, url, port, method, params):
    x = ElectrumServer(coin, url, port, "TCP")
    resp = x.tcp(method, params)
    el = parse_response(x, resp)

    if el.blockheight > 0:
        if coin not in passed_electrums:
            passed_electrums.update({coin:[]})
        passed_electrums[coin].append(f"{url}:{port}")
        logger.calc(f"[TCP] {coin} {url}:{port} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_electrums:
            failed_electrums.update({coin:{}})
        failed_electrums[coin].update({f"{url}:{port}": f"{el.result}"})
        logger.warning(f"[TCP] {coin} {url}:{port} Failed! | {el.result}")


def thread_electrum_ssl(coin, url, port, method, params):
    x = ElectrumServer(coin, url, port, "SSL")
    resp = x.ssl(method, params)
    el = parse_response(x, resp)
    
    # Check SSL certificate expiry
    cert_info = check_ssl_certificate_expiry(url, port)
    cert_days = cert_info.get("days_until_expiry") if isinstance(cert_info, dict) else None
    cert_error = cert_info.get("error") if isinstance(cert_info, dict) and "error" in cert_info else None
    
    if el.blockheight > 0:
        if coin not in passed_electrums_ssl:
            passed_electrums_ssl.update({coin: {}})
        passed_electrums_ssl[coin][f"{url}:{port}"] = {"cert_days": cert_days, "cert_error": cert_error}
        logger.info(f"[SSL] {coin} {url}:{port} OK! Height: {el.blockheight}, SSL expires in {cert_days} days" if cert_days else f"[SSL] {coin} {url}:{port} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_electrums_ssl:
            failed_electrums_ssl.update({coin: {}})
        failed_electrums_ssl[coin].update({f"{url}:{port}": {"result": el.result, "cert_days": cert_days, "cert_error": cert_error}})
        logger.warning(f"[SSL] {coin} {url}:{port} Failed! | {el.result}")


def thread_tendermint(coin, url, api_url):
    """Thread function for scanning Tendermint HTTP RPC"""
    x = TendermintServer(coin, url, api_url=api_url)
    resp = x.http_rpc()
    el = parse_tendermint_response(x, resp)

    # Check SSL certificate if HTTPS
    cert_days = None
    cert_error = None
    if url.startswith('https://'):
        cert_info = check_ssl_certificate_expiry(url)
        cert_days = cert_info.get("days_until_expiry") if isinstance(cert_info, dict) else None
        cert_error = cert_info.get("error") if isinstance(cert_info, dict) and "error" in cert_info else None

    if el.blockheight > 0:
        if coin not in passed_tendermint:
            passed_tendermint.update({coin: {}})
        passed_tendermint[coin][url] = {"cert_days": cert_days, "cert_error": cert_error}
        logger.calc(f"[TENDERMINT] {coin} {url} OK! Height: {el.blockheight}, SSL expires in {cert_days} days" if cert_days else f"[TENDERMINT] {coin} {url} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_tendermint:
            failed_tendermint.update({coin: {}})
        failed_tendermint[coin].update({url: {"result": el.result, "cert_days": cert_days, "cert_error": cert_error}})
        logger.warning(f"[TENDERMINT] {coin} {url} Failed! {el.result}")


def thread_tendermint_wss(coin, url, ws_url):
    """Thread function for scanning Tendermint WebSocket"""
    x = TendermintServer(coin, url, ws_url=ws_url)
    resp = x.wss_rpc()
    el = parse_tendermint_response(x, resp)

    # Check SSL certificate for WSS
    cert_days = None
    cert_error = None
    if ws_url and ws_url.startswith('wss://'):
        cert_info = check_ssl_certificate_expiry(ws_url)
        cert_days = cert_info.get("days_until_expiry") if isinstance(cert_info, dict) else None
        cert_error = cert_info.get("error") if isinstance(cert_info, dict) and "error" in cert_info else None

    endpoint = ws_url or url
    if el.blockheight > 0:
        if coin not in passed_tendermint_wss:
            passed_tendermint_wss.update({coin: {}})
        passed_tendermint_wss[coin][endpoint] = {"cert_days": cert_days, "cert_error": cert_error}
        logger.calc(f"[TENDERMINT WSS] {coin} {endpoint} OK! Height: {el.blockheight}, SSL expires in {cert_days} days" if cert_days else f"[TENDERMINT WSS] {coin} {endpoint} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_tendermint_wss:
            failed_tendermint_wss.update({coin: {}})
        failed_tendermint_wss[coin].update({endpoint: {"result": el.result, "cert_days": cert_days, "cert_error": cert_error}})
        logger.warning(f"[TENDERMINT WSS] {coin} {endpoint} Failed! {el.result}")


def thread_ethereum(coin, url):
    """Thread function for scanning Ethereum HTTP RPC"""
    x = EthereumServer(coin, url)
    resp = x.http_rpc()
    el = parse_ethereum_response(x, resp)

    # Check SSL certificate if HTTPS
    cert_days = None
    cert_error = None
    if url.startswith('https://'):
        cert_info = check_ssl_certificate_expiry(url)
        cert_days = cert_info.get("days_until_expiry") if isinstance(cert_info, dict) else None
        cert_error = cert_info.get("error") if isinstance(cert_info, dict) and "error" in cert_info else None

    if el.blockheight > 0:
        if coin not in passed_ethereum:
            passed_ethereum.update({coin: {}})
        passed_ethereum[coin][url] = {"cert_days": cert_days, "cert_error": cert_error}
        logger.calc(f"[ETHEREUM] {coin} {url} OK! Height: {el.blockheight}, SSL expires in {cert_days} days" if cert_days else f"[ETHEREUM] {coin} {url} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_ethereum:
            failed_ethereum.update({coin: {}})
        failed_ethereum[coin].update({url: {"result": el.result, "cert_days": cert_days, "cert_error": cert_error}})
        logger.warning(f"[ETHEREUM] {coin} {url} Failed! {el.result}")


def thread_ethereum_wss(coin, url, ws_url):
    """Thread function for scanning Ethereum WebSocket"""
    x = EthereumServer(coin, url, ws_url=ws_url)
    resp = x.wss_rpc()
    el = parse_ethereum_response(x, resp)

    # Check SSL certificate for WSS
    cert_days = None
    cert_error = None
    if ws_url and ws_url.startswith('wss://'):
        cert_info = check_ssl_certificate_expiry(ws_url)
        cert_days = cert_info.get("days_until_expiry") if isinstance(cert_info, dict) else None
        cert_error = cert_info.get("error") if isinstance(cert_info, dict) and "error" in cert_info else None

    endpoint = ws_url or url
    if el.blockheight > 0:
        if coin not in passed_ethereum_wss:
            passed_ethereum_wss.update({coin: {}})
        passed_ethereum_wss[coin][endpoint] = {"cert_days": cert_days, "cert_error": cert_error}
        logger.calc(f"[ETHEREUM WSS] {coin} {endpoint} OK! Height: {el.blockheight}, SSL expires in {cert_days} days" if cert_days else f"[ETHEREUM WSS] {coin} {endpoint} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_ethereum_wss:
            failed_ethereum_wss.update({coin: {}})
        failed_ethereum_wss[coin].update({endpoint: {"result": el.result, "cert_days": cert_days, "cert_error": cert_error}})
        logger.warning(f"[ETHEREUM WSS] {coin} {endpoint} Failed! {el.result}")


def parse_tendermint_response(tm_obj, resp):
    """Parse Tendermint RPC response"""
    try:
        if isinstance(resp, dict) and "error" in resp:
            tm_obj.result = resp["error"]
        elif isinstance(resp, dict) and "result" in resp:
            result = resp["result"]
            if "sync_info" in result:
                tm_obj.blockheight = int(result["sync_info"]["latest_block_height"])
                tm_obj.last_connection = int(time.time())
                tm_obj.result = "Passed"
            else:
                tm_obj.result = "Invalid response format"
        else:
            tm_obj.result = f"Unexpected response: {resp}"
    except Exception as e:
        tm_obj.result = f"Parse error: {e}"
        logger.error(f"[TENDERMINT] Error parsing {tm_obj.coin} {tm_obj.url} | Response: {resp} | Error: {e}")
    return tm_obj


def parse_ethereum_response(eth_obj, resp):
    """Parse Ethereum RPC response"""
    try:
        if isinstance(resp, dict) and "error" in resp:
            eth_obj.result = resp["error"]
        elif isinstance(resp, dict) and "result" in resp:
            result = resp["result"]
            if isinstance(result, str) and result.startswith("0x"):
                # Convert hex block number to decimal
                eth_obj.blockheight = int(result, 16)
                eth_obj.last_connection = int(time.time())
                eth_obj.result = "Passed"
            else:
                eth_obj.result = f"Invalid block format: {result}"
        else:
            eth_obj.result = f"Unexpected response: {resp}"
    except Exception as e:
        eth_obj.result = f"Parse error: {e}"
        logger.error(f"[ETHEREUM] Error parsing {eth_obj.coin} {eth_obj.url} | Response: {resp} | Error: {e}")
    return eth_obj


def parse_response(el_obj, resp):
    try:
        # Short form for known error responses
        low_str = str(resp).lower()
        if low_str.find('timeout') > -1 or low_str.find('timed out') > -1:
            logger.warning(low_str)
            el_obj.result = "Timed out"
        elif low_str.find('refused') > -1 or low_str.find('connect call failed') > -1:
            el_obj.result = "Connection refused"
        elif low_str.find('no route to host') > -1:
            el_obj.result = "No route to host"
        elif low_str.find('name or service not known') > -1:
            el_obj.result = "Name or service not known"
        elif low_str.find('network is unreachable') > -1:
            el_obj.result = "Network is unreachable "
        elif low_str.find('ssl handshake is taking longer than') > -1:
            el_obj.result = "SSL handshake timed out"
        elif low_str.find('oserror') > -1:
            el_obj.result = "OS Error"
            
        elif low_str.find('gaierror') > -1:
            el_obj.result = "Gai Error"
        elif len(str(resp)) < 3:
            el_obj.result = "Empty response"

        # Long form for known success responses
        elif "result" in json.loads(resp):
            el_obj.result = json.loads(resp)['result']
        elif "params" in json.loads(resp):
            el_obj.result = json.loads(resp)['params'][0]
        else:
            logger.error(json.loads(resp))

        if "height" in el_obj.result:
            el_obj.blockheight = int(el_obj.result['height'])
            el_obj.last_connection = int(time.time())
        elif "block_height" in el_obj.result:
            el_obj.blockheight = int(el_obj.result['block_height'])
            el_obj.last_connection = int(time.time())
    except Exception as e:
        logger.error(f"[{el_obj.protocol}] Error parsing {el_obj.coin} {el_obj.url} {el_obj.port} | Response: [{e}] {resp}")
    return el_obj


def scan_electrums(electrum_dict):
    thread_list = []
    protocol_lists = {
        "tcp": [],
        "ssl": [],
        "wss": []
    }

    for coin in electrum_dict:
        for electrum in electrum_dict[coin]:
                if "ws_url" in electrum:
                    url, port = electrum["ws_url"].split(":")
                    protocol_lists['wss'].append(coin)
                
                    thread_list.append(
                        scan_thread(
                            coin,
                            url,
                            port,
                            "blockchain.headers.subscribe",
                            [],
                            "wss",
                            node_type='electrum'
                        )
                    )
                if 'url' in electrum:
                    url, port = electrum["url"].split(":")
                    if "protocol" in electrum:
                        protocol_lists[electrum["protocol"].lower()].append(coin)
                        thread_list.append(
                            scan_thread(
                                coin,
                                url,
                                port,
                                "blockchain.headers.subscribe",
                                [],
                                electrum["protocol"].lower(),
                                node_type='electrum'
                            )
                        )
                    else:
                        protocol_lists['tcp'].append(coin)
                        thread_list.append(
                            scan_thread(
                                coin,
                                url,
                                port,
                                "blockchain.headers.subscribe",
                                [],
                                "tcp",
                                node_type='electrum'
                            )
                        )

        
    for thread in thread_list:
        thread.start()
        time.sleep(0.1)
    return protocol_lists


def scan_tendermint(tendermint_dict):
    """Scan Tendermint RPC nodes"""
    thread_list = []
    protocol_lists = {
        "http": [],
        "wss": []
    }

    for coin in tendermint_dict:
        if "rpc_nodes" in tendermint_dict[coin]:
            for node in tendermint_dict[coin]["rpc_nodes"]:
                if "url" in node:
                    protocol_lists['http'].append(coin)
                    thread_list.append(
                        scan_thread(
                            coin,
                            node["url"],
                            protocol="http",
                            node_type='tendermint',
                            api_url=node.get("api_url")
                        )
                    )
                
                if "ws_url" in node:
                    protocol_lists['wss'].append(coin)
                    thread_list.append(
                        scan_thread(
                            coin,
                            node["url"],
                            protocol="wss",
                            node_type='tendermint',
                            ws_url=node["ws_url"]
                        )
                    )
    
    for thread in thread_list:
        thread.start()
        time.sleep(0.1)
    return protocol_lists


def scan_ethereum(ethereum_dict):
    """Scan Ethereum RPC nodes"""
    thread_list = []
    protocol_lists = {
        "http": [],
        "wss": []
    }

    for coin in ethereum_dict:
        if "rpc_nodes" in ethereum_dict[coin]:
            for node in ethereum_dict[coin]["rpc_nodes"]:
                if "url" in node:
                    protocol_lists['http'].append(coin)
                    thread_list.append(
                        scan_thread(
                            coin,
                            node["url"],
                            protocol="http",
                            node_type='ethereum'
                        )
                    )
                
                if "ws_url" in node:
                    protocol_lists['wss'].append(coin)
                    thread_list.append(
                        scan_thread(
                            coin,
                            node["url"],
                            protocol="wss",
                            node_type='ethereum',
                            ws_url=node["ws_url"]
                        )
                    )
    
    for thread in thread_list:
        thread.start()
        time.sleep(0.1)
    return protocol_lists


def get_repo_electrums():
    electrum_coins = [
        f for f in os.listdir(f"{repo_path}/electrums") 
        if os.path.isfile(f"{repo_path}/electrums/{f}") 
        and f not in ["SCZEN", "SC"]
    ]
    repo_electrums = {}
    for coin in electrum_coins:
        try:
            with open(f"{repo_path}/electrums/{coin}", "r") as f:
                electrums = json.load(f)
                repo_electrums.update({coin: electrums})
        except json.decoder.JSONDecodeError:
            print(f"{coin} electrums failed to parse, exiting.")
            sys.exit(1)
    return repo_electrums


def get_repo_tendermint():
    """Load tendermint node configurations"""
    tendermint_path = f"{repo_path}/tendermint"
    if not os.path.exists(tendermint_path):
        return {}
    
    tendermint_coins = [
        f for f in os.listdir(tendermint_path) 
        if os.path.isfile(f"{tendermint_path}/{f}")
    ]
    repo_tendermint = {}
    for coin in tendermint_coins:
        try:
            with open(f"{tendermint_path}/{coin}", "r") as f:
                nodes = json.load(f)
                repo_tendermint.update({coin: nodes})
        except json.decoder.JSONDecodeError:
            print(f"{coin} tendermint config failed to parse, exiting.")
            sys.exit(1)
    return repo_tendermint


def get_repo_ethereum():
    """Load ethereum node configurations"""
    ethereum_path = f"{repo_path}/ethereum"
    if not os.path.exists(ethereum_path):
        return {}
    
    ethereum_coins = [
        f for f in os.listdir(ethereum_path) 
        if os.path.isfile(f"{ethereum_path}/{f}")
    ]
    repo_ethereum = {}
    for coin in ethereum_coins:
        try:
            with open(f"{ethereum_path}/{coin}", "r") as f:
                nodes = json.load(f)
                repo_ethereum.update({coin: nodes})
        except json.decoder.JSONDecodeError:
            print(f"{coin} ethereum config failed to parse, exiting.")
            sys.exit(1)
    return repo_ethereum


def get_existing_report():
    # Load existing electrum scan report for connection history
    if os.path.exists("electrum_scan_report.json"):
        with open(f"{script_path}/electrum_scan_report.json", "r") as f:
            return json.load(f)
    return {}


def get_last_connection(report, coin, protocol, server):
    try:
        return report[coin][protocol][server]["last_connection"]
    except KeyError:
        return 0
    except TypeError:
        return 0



def generate_scan_summary(legacy_results, current_time, uptime_tracker=None):
    """Generate scan summary with servers offline >30 days using uptime tracker as source of truth"""
    days_since_connection = {}
    THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60  # 30 days in seconds
    
    # If uptime tracker is provided, use it as the source of truth
    if uptime_tracker:
        for coin, coin_data in legacy_results.items():
            for protocol in ["tcp", "ssl", "wss"]:
                if protocol in coin_data:
                    for server, server_data in coin_data[protocol].items():
                        # Check uptime tracker for real offline duration
                        offline_duration = uptime_tracker.get_server_offline_duration(coin, server)
                        if offline_duration and offline_duration > THIRTY_DAYS_SECONDS:
                            days_offline = int(offline_duration / (24 * 60 * 60))
                            days_since_connection[server] = days_offline
    else:
        # Fallback to scan report data if no uptime tracker
        for coin, coin_data in legacy_results.items():
            for protocol in ["tcp", "ssl", "wss"]:
                if protocol in coin_data:
                    for server, server_data in coin_data[protocol].items():
                        last_connection = server_data.get("last_connection", 0)
                        
                        # Only include servers that haven't connected for over 30 days
                        if last_connection == 0:
                            # Never connected - skip rather than using misleading 999 days
                            continue
                        else:
                            days_offline = (current_time - last_connection) / (24 * 60 * 60)
                            if days_offline > 30:
                                days_since_connection[server] = int(days_offline)
    
    return {
        "delisted_coins": [],  # Will be populated by generate_app_configs.py
        "days_since_connection": days_since_connection
    }


def get_electrums_report():
    current_time = int(time.time())
    existing_report = get_existing_report()
    
    # Load all node types
    electrum_dict = get_repo_electrums()
    tendermint_dict = get_repo_tendermint()
    ethereum_dict = get_repo_ethereum()
    
    # Scan all node types
    electrum_protocol_lists = scan_electrums(electrum_dict)
    tendermint_protocol_lists = scan_tendermint(tendermint_dict)
    ethereum_protocol_lists = scan_ethereum(ethereum_dict)
    
    # Electrum sets
    electrum_coins_ssl = set(electrum_protocol_lists['ssl'])
    electrum_coins = set(electrum_protocol_lists['tcp'])
    electrum_coins_wss = set(electrum_protocol_lists['wss'])
    
    # Tendermint sets
    tendermint_coins_http = set(tendermint_protocol_lists['http'])
    tendermint_coins_wss = set(tendermint_protocol_lists['wss'])
    
    # Ethereum sets
    ethereum_coins_http = set(ethereum_protocol_lists['http'])
    ethereum_coins_wss = set(ethereum_protocol_lists['wss'])

    total_nodes = (len(electrum_coins) + len(electrum_coins_ssl) + len(electrum_coins_wss) + 
                   len(tendermint_coins_http) + len(tendermint_coins_wss) + 
                   len(ethereum_coins_http) + len(ethereum_coins_wss))
    i = 0
    while True:
        # Check Electrum progress
        electrums_set = set(list(passed_electrums.keys()) + list(failed_electrums.keys())) - set(ignore_list)
        electrums_ssl_set = set(list(passed_electrums_ssl.keys()) + list(failed_electrums_ssl.keys())) - set(ignore_list)
        electrums_wss_set = set(list(passed_electrums_wss.keys()) + list(failed_electrums_wss.keys())) - set(ignore_list)
        
        # Check Tendermint progress
        tendermint_http_set = set(list(passed_tendermint.keys()) + list(failed_tendermint.keys())) - set(ignore_list)
        tendermint_wss_set = set(list(passed_tendermint_wss.keys()) + list(failed_tendermint_wss.keys())) - set(ignore_list)
        
        # Check Ethereum progress
        ethereum_http_set = set(list(passed_ethereum.keys()) + list(failed_ethereum.keys())) - set(ignore_list)
        ethereum_wss_set = set(list(passed_ethereum_wss.keys()) + list(failed_ethereum_wss.keys())) - set(ignore_list)
        
        # Calculate progress percentages
        if len(electrum_coins) > 0:
            electrums_pct = round(len(electrums_set) / len(electrum_coins) * 100, 2)
            logger.query(f"Electrum TCP scan progress: {electrums_pct}% ({len(electrums_set)}/{len(electrum_coins)})")
        
        if len(electrum_coins_ssl) > 0:
            electrums_ssl_pct = round(len(electrums_ssl_set) / len(electrum_coins_ssl) * 100, 2)
            logger.query(f"Electrum SSL scan progress: {electrums_ssl_pct}% ({len(electrums_ssl_set)}/{len(electrum_coins_ssl)})")
        
        if len(electrum_coins_wss) > 0:
            electrums_wss_pct = round(len(electrums_wss_set) / len(electrum_coins_wss) * 100, 2)
            logger.query(f"Electrum WSS scan progress: {electrums_wss_pct}% ({len(electrums_wss_set)}/{len(electrum_coins_wss)})")
            
        if len(tendermint_coins_http) > 0:
            tendermint_http_pct = round(len(tendermint_http_set) / len(tendermint_coins_http) * 100, 2)
            logger.query(f"Tendermint HTTP scan progress: {tendermint_http_pct}% ({len(tendermint_http_set)}/{len(tendermint_coins_http)})")
        
        if len(tendermint_coins_wss) > 0:
            tendermint_wss_pct = round(len(tendermint_wss_set) / len(tendermint_coins_wss) * 100, 2)
            logger.query(f"Tendermint WSS scan progress: {tendermint_wss_pct}% ({len(tendermint_wss_set)}/{len(tendermint_coins_wss)})")
            
        if len(ethereum_coins_http) > 0:
            ethereum_http_pct = round(len(ethereum_http_set) / len(ethereum_coins_http) * 100, 2)
            logger.query(f"Ethereum HTTP scan progress: {ethereum_http_pct}% ({len(ethereum_http_set)}/{len(ethereum_coins_http)})")
        
        if len(ethereum_coins_wss) > 0:
            ethereum_wss_pct = round(len(ethereum_wss_set) / len(ethereum_coins_wss) * 100, 2)
            logger.query(f"Ethereum WSS scan progress: {ethereum_wss_pct}% ({len(ethereum_wss_set)}/{len(ethereum_coins_wss)})")
            
        # Check if all scans are complete
        all_complete = (
            electrums_set == electrum_coins and
            electrums_ssl_set == electrum_coins_ssl and
            electrums_wss_set == electrum_coins_wss and
            tendermint_http_set == tendermint_coins_http and
            tendermint_wss_set == tendermint_coins_wss and
            ethereum_http_set == ethereum_coins_http and
            ethereum_wss_set == ethereum_coins_wss
        )
        
        if all_complete:
            logger.info("All node scans complete!")
            break
            
        if i > (total_nodes * 0.1 + 120):
            logger.warning("Node scan loop expired incomplete after extended timeout.")
            break
        i += 1
        time.sleep(3)

    results = {
        "utxo": {},
        "evm": {},
        "tendermint": {}
    }

    # Process UTXO coins (Electrum)
    utxo_coins = list(electrums_ssl_set.union(electrums_set).union(electrums_wss_set))
    utxo_coins.sort()
    
    for coin in utxo_coins:
        # Count Electrum nodes only
        if coin in passed_electrums: passed = len(passed_electrums[coin])
        else: passed = 0
        if coin in passed_electrums_ssl: passed_ssl = len(passed_electrums_ssl[coin])
        else: passed_ssl = 0
        if coin in passed_electrums_wss: passed_wss = len(passed_electrums_wss[coin])
        else: passed_wss = 0
        if coin in failed_electrums: failed = len(failed_electrums[coin])
        else: failed = 0
        if coin in failed_electrums_ssl: failed_ssl = len(failed_electrums_ssl[coin])
        else: failed_ssl = 0
        if coin in failed_electrums_wss: failed_wss = len(failed_electrums_wss[coin])
        else: failed_wss = 0
        
        # Create UTXO-specific result structure
        results["utxo"][coin] = {
            "total_all": passed + failed + passed_ssl + failed_ssl + passed_wss + failed_wss,
            "working_all": passed + passed_ssl + passed_wss,
            "total_tcp": passed + failed,
            "working_tcp": passed,
            "total_ssl": passed_ssl + failed_ssl,
            "working_ssl": passed_ssl,
            "total_wss": passed_wss + failed_wss,
            "working_wss": passed_wss,
            "tcp": {},
            "ssl": {},
            "wss": {}
        }

        # Add UTXO node details
        if coin in passed_electrums:
            x = list(passed_electrums[coin])
            x.sort()
            for i in x:
                results["utxo"][coin]["tcp"].update({
                    i: {
                        "last_connection": current_time,
                        "result": "Passed",
                        "ssl_days_left": 1
                    }
                })

        if coin in failed_electrums:
            x = list(failed_electrums[coin].keys())
            x.sort()
            for i in x:
                results["utxo"][coin]["tcp"].update({
                    i: {
                        "last_connection": get_last_connection(existing_report, coin, "tcp", i),
                        "result": failed_electrums[coin][i],
                        "ssl_days_left": -1
                    }
                })

        if coin in passed_electrums_ssl:
            x = list(passed_electrums_ssl[coin])
            x.sort()
            for i in x:
                cert_days = passed_electrums_ssl[coin][i].get("cert_days")
                cert_error = passed_electrums_ssl[coin][i].get("cert_error")
                
                ssl_info = {
                    "last_connection": current_time,
                    "result": "CERTIFICATE_VERIFY_FAILED" if cert_error else "Passed"
                }
                ssl_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    ssl_info["ssl_error"] = cert_error
                results["utxo"][coin]["ssl"].update({i: ssl_info})

        if coin in failed_electrums_ssl:
            x = list(failed_electrums_ssl[coin].keys())
            x.sort()
            for i in x:
                ssl_info = {
                    "last_connection": get_last_connection(existing_report, coin, "ssl", i),
                    "result": failed_electrums_ssl[coin][i].get("result", failed_electrums_ssl[coin][i])
                }
                cert_days = failed_electrums_ssl[coin][i].get("cert_days")
                cert_error = failed_electrums_ssl[coin][i].get("cert_error")
                ssl_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    ssl_info["ssl_error"] = cert_error
                results["utxo"][coin]["ssl"].update({i: ssl_info})

        if coin in passed_electrums_wss:
            x = list(passed_electrums_wss[coin])
            x.sort()
            for i in x:
                cert_days = passed_electrums_wss[coin][i].get("cert_days")
                cert_error = passed_electrums_wss[coin][i].get("cert_error")
                
                wss_info = {
                    "last_connection": current_time,
                    "result": "CERTIFICATE_VERIFY_FAILED" if cert_error else "Passed"
                }
                wss_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    wss_info["ssl_error"] = cert_error
                results["utxo"][coin]["wss"].update({i: wss_info})

        if coin in failed_electrums_wss:
            x = list(failed_electrums_wss[coin].keys())
            x.sort()
            for i in x:
                wss_info = {
                    "last_connection": get_last_connection(existing_report, coin, "wss", i),
                    "result": failed_electrums_wss[coin][i].get("result", failed_electrums_wss[coin][i])
                }
                cert_days = failed_electrums_wss[coin][i].get("cert_days")
                cert_error = failed_electrums_wss[coin][i].get("cert_error")
                wss_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    wss_info["ssl_error"] = cert_error
                results["utxo"][coin]["wss"].update({i: wss_info})

    # Process Tendermint coins
    tendermint_coins = list(tendermint_http_set.union(tendermint_wss_set))
    tendermint_coins.sort()
    
    for coin in tendermint_coins:
        # Count Tendermint nodes only
        if coin in passed_tendermint: passed_tm = len(passed_tendermint[coin])
        else: passed_tm = 0
        if coin in passed_tendermint_wss: passed_tm_wss = len(passed_tendermint_wss[coin])
        else: passed_tm_wss = 0
        if coin in failed_tendermint: failed_tm = len(failed_tendermint[coin])
        else: failed_tm = 0
        if coin in failed_tendermint_wss: failed_tm_wss = len(failed_tendermint_wss[coin])
        else: failed_tm_wss = 0
        
        # Create Tendermint-specific result structure
        results["tendermint"][coin] = {
            "total_all": passed_tm + failed_tm + passed_tm_wss + failed_tm_wss,
            "working_all": passed_tm + passed_tm_wss,
            "total_http": passed_tm + failed_tm,
            "working_http": passed_tm,
            "total_wss": passed_tm_wss + failed_tm_wss,
            "working_wss": passed_tm_wss,
            "http": {},
            "wss": {}
        }

        # Add Tendermint node details
        if coin in passed_tendermint:
            x = list(passed_tendermint[coin])
            x.sort()
            for i in x:
                cert_days = passed_tendermint[coin][i].get("cert_days")
                cert_error = passed_tendermint[coin][i].get("cert_error")
                
                tm_info = {
                    "last_connection": current_time,
                    "result": "CERTIFICATE_VERIFY_FAILED" if cert_error else "Passed"
                }
                tm_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    tm_info["ssl_error"] = cert_error
                results["tendermint"][coin]["http"].update({i: tm_info})

        if coin in failed_tendermint:
            x = list(failed_tendermint[coin].keys())
            x.sort()
            for i in x:
                tm_info = {
                    "last_connection": get_last_connection(existing_report, coin, "tendermint_http", i),
                    "result": failed_tendermint[coin][i].get("result", failed_tendermint[coin][i])
                }
                cert_days = failed_tendermint[coin][i].get("cert_days")
                cert_error = failed_tendermint[coin][i].get("cert_error")
                tm_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    tm_info["ssl_error"] = cert_error
                results["tendermint"][coin]["http"].update({i: tm_info})

        if coin in passed_tendermint_wss:
            x = list(passed_tendermint_wss[coin])
            x.sort()
            for i in x:
                cert_days = passed_tendermint_wss[coin][i].get("cert_days")
                cert_error = passed_tendermint_wss[coin][i].get("cert_error")
                
                wss_info = {
                    "last_connection": current_time,
                    "result": "CERTIFICATE_VERIFY_FAILED" if cert_error else "Passed"
                }
                wss_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    wss_info["ssl_error"] = cert_error
                results["tendermint"][coin]["wss"].update({i: wss_info})

        if coin in failed_tendermint_wss:
            x = list(failed_tendermint_wss[coin].keys())
            x.sort()
            for i in x:
                wss_info = {
                    "last_connection": get_last_connection(existing_report, coin, "tendermint_wss", i),
                    "result": failed_tendermint_wss[coin][i].get("result", failed_tendermint_wss[coin][i])
                }
                cert_days = failed_tendermint_wss[coin][i].get("cert_days")
                cert_error = failed_tendermint_wss[coin][i].get("cert_error")
                wss_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    wss_info["ssl_error"] = cert_error
                results["tendermint"][coin]["wss"].update({i: wss_info})

    # Process EVM coins (Ethereum-based)
    evm_coins = list(ethereum_http_set.union(ethereum_wss_set))
    evm_coins.sort()
    
    for coin in evm_coins:
        # Count EVM nodes only
        if coin in passed_ethereum: passed_eth = len(passed_ethereum[coin])
        else: passed_eth = 0
        if coin in passed_ethereum_wss: passed_eth_wss = len(passed_ethereum_wss[coin])
        else: passed_eth_wss = 0
        if coin in failed_ethereum: failed_eth = len(failed_ethereum[coin])
        else: failed_eth = 0
        if coin in failed_ethereum_wss: failed_eth_wss = len(failed_ethereum_wss[coin])
        else: failed_eth_wss = 0
        
        # Create EVM-specific result structure
        results["evm"][coin] = {
            "total_all": passed_eth + failed_eth + passed_eth_wss + failed_eth_wss,
            "working_all": passed_eth + passed_eth_wss,
            "total_http": passed_eth + failed_eth,
            "working_http": passed_eth,
            "total_wss": passed_eth_wss + failed_eth_wss,
            "working_wss": passed_eth_wss,
            "http": {},
            "wss": {}
        }

        # Add EVM node details
        if coin in passed_ethereum:
            x = list(passed_ethereum[coin])
            x.sort()
            for i in x:
                cert_days = passed_ethereum[coin][i].get("cert_days")
                cert_error = passed_ethereum[coin][i].get("cert_error")
                
                eth_info = {
                    "last_connection": current_time,
                    "result": "CERTIFICATE_VERIFY_FAILED" if cert_error else "Passed"
                }
                eth_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    eth_info["ssl_error"] = cert_error
                results["evm"][coin]["http"].update({i: eth_info})

        if coin in failed_ethereum:
            x = list(failed_ethereum[coin].keys())
            x.sort()
            for i in x:
                eth_info = {
                    "last_connection": get_last_connection(existing_report, coin, "ethereum_http", i),
                    "result": failed_ethereum[coin][i].get("result", failed_ethereum[coin][i])
                }
                cert_days = failed_ethereum[coin][i].get("cert_days")
                cert_error = failed_ethereum[coin][i].get("cert_error")
                eth_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    eth_info["ssl_error"] = cert_error
                results["evm"][coin]["http"].update({i: eth_info})

        if coin in passed_ethereum_wss:
            x = list(passed_ethereum_wss[coin])
            x.sort()
            for i in x:
                cert_days = passed_ethereum_wss[coin][i].get("cert_days")
                cert_error = passed_ethereum_wss[coin][i].get("cert_error")
                
                wss_info = {
                    "last_connection": current_time,
                    "result": "CERTIFICATE_VERIFY_FAILED" if cert_error else "Passed"
                }
                wss_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    wss_info["ssl_error"] = cert_error
                results["evm"][coin]["wss"].update({i: wss_info})

        if coin in failed_ethereum_wss:
            x = list(failed_ethereum_wss[coin].keys())
            x.sort()
            for i in x:
                wss_info = {
                    "last_connection": get_last_connection(existing_report, coin, "ethereum_wss", i),
                    "result": failed_ethereum_wss[coin][i].get("result", failed_ethereum_wss[coin][i])
                }
                cert_days = failed_ethereum_wss[coin][i].get("cert_days")
                cert_error = failed_ethereum_wss[coin][i].get("cert_error")
                wss_info["ssl_days_left"] = cert_days if cert_days is not None else -1
                if cert_error:
                    wss_info["ssl_error"] = cert_error
                results["evm"][coin]["wss"].update({i: wss_info})


    # Generate electrum_scan_report.json
    legacy_results = {}
    
    # Merge all node types into the legacy format
    for section_name, section_data in results.items():
        for coin, coin_data in section_data.items():
            if coin not in legacy_results:
                legacy_results[coin] = {
                    "nodes_total_all": 0,
                    "nodes_working_all": 0,
                    "tcp": {},
                    "ssl": {},
                    "wss": {}
                }
            
            # Map the new structure to legacy structure based on protocol type
            if section_name == "utxo":
                # UTXO protocols map directly
                if "tcp" in coin_data:
                    for node, node_data in coin_data["tcp"].items():
                        legacy_results[coin]["tcp"][node] = dict(node_data)
                if "ssl" in coin_data:
                    for node, node_data in coin_data["ssl"].items():
                        legacy_results[coin]["ssl"][node] = dict(node_data)
                if "wss" in coin_data:
                    for node, node_data in coin_data["wss"].items():
                        legacy_results[coin]["wss"][node] = dict(node_data)
            elif section_name == "tendermint":
                # Tendermint HTTP goes to ssl (since they're HTTPS), WSS stays as wss
                if "http" in coin_data:
                    for node, node_data in coin_data["http"].items():
                        # Determine if HTTP or HTTPS based on URL
                        if node.startswith("https://"):
                            legacy_results[coin]["ssl"][node] = dict(node_data)
                        else:
                            legacy_results[coin]["tcp"][node] = dict(node_data)
                if "wss" in coin_data:
                    for node, node_data in coin_data["wss"].items():
                        legacy_results[coin]["wss"][node] = dict(node_data)
            elif section_name == "evm":
                # EVM HTTP goes to ssl (since they're HTTPS), WSS stays as wss
                if "http" in coin_data:
                    for node, node_data in coin_data["http"].items():
                        # Determine if HTTP or HTTPS based on URL
                        if node.startswith("https://"):
                            legacy_results[coin]["ssl"][node] = dict(node_data)
                        else:
                            legacy_results[coin]["tcp"][node] = dict(node_data)
                if "wss" in coin_data:
                    for node, node_data in coin_data["wss"].items():
                        legacy_results[coin]["wss"][node] = dict(node_data)
            
            # Calculate totals for legacy format
            total_nodes = 0
            working_nodes = 0
            
            for protocol_data in coin_data.values():
                if isinstance(protocol_data, dict):
                    for node_data in protocol_data.values():
                        total_nodes += 1
                        if node_data.get("result") == "Passed":
                            working_nodes += 1
            
            legacy_results[coin]["nodes_total_all"] = total_nodes
            legacy_results[coin]["nodes_working_all"] = working_nodes

    with open(f"{script_path}/electrum_scan_report.json", "w+") as f:
        f.write(json.dumps(legacy_results, indent=4))

    # Note: scan_summary will be generated in generate_app_configs.py with uptime tracker

    # print(json.dumps(results, indent=4))
    return legacy_results

if __name__ == '__main__':
    get_electrums_report()
