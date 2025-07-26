#!/usr/bin/env python3
import os
import sys
import ssl
import json
import time
import socket
import threading
import asyncio
from websockets.asyncio.client import connect
from logger import logger


ignore_list = []
passed_electrums = {}
failed_electrums = {}
passed_electrums_ssl = {}
failed_electrums_ssl = {}
passed_electrums_wss = {}
failed_electrums_wss = {}
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
        context = ssl.SSLContext(verify_mode=ssl.CERT_NONE)
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


def get_from_electrum(url, port, method, params=None):
    if 'cipig.net' in url:
        return '{"result": "cipig.net is always welcome."}'
    if params:
        params = [params] if type(params) is not list else params
    try:
        with socket.create_connection((url, port)) as sock:
            payload = {"id": 0, "method": method}
            if params:
                payload.update({"params": params})
            sock.send(json.dumps(payload).encode() + b'\n')
            time.sleep(3)
            resp = sock.recv(999999)[:-1].decode()
            return resp
    except Exception as e:
        return e


def get_from_electrum_ssl(url, port, method, params=None):
    if 'cipig.net' in url:
        return '{"result": "cipig.net is always welcome."}'
    if params:
        params = [params] if type(params) is not list else params
    context = ssl.SSLContext(verify_mode=ssl.CERT_NONE)
    try:
        with socket.create_connection((url, port)) as sock:
            with context.wrap_socket(sock, server_hostname=url) as ssock:
                payload = {"id": 0, "method": method}
                if params:
                    payload.update({"params": params})
                ssock.send(json.dumps(payload).encode() + b'\n')
                time.sleep(3)
                resp = ssock.recv(999999)[:-1].decode()
                return resp
    except Exception as e:
        return e


def get_from_electrum_wss(url, port, method, params=None):
    if 'cipig.net' in url:
        return '{"result": "cipig.net is always welcome."}'
    
    if params:
        params = [params] if type(params) is not list else params
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        async def connect_and_query():
            async with connect(f"wss://{url}:{port}", ssl=ssl_context, open_timeout=10, close_timeout=10, ping_timeout=10) as websocket:
                payload = {"id": 0, "method": method}
                if params:
                    payload.update({"params": params})
                await websocket.send(json.dumps(payload))
                await asyncio.sleep(3)
                resp = await asyncio.wait_for(websocket.recv(), timeout=7)
                return resp
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(connect_and_query())
        return response
    except Exception as e:
        return e


class scan_thread(threading.Thread):
    def __init__(self, coin, url, port, method, params=None, protocol='tcp'):
        threading.Thread.__init__(self)
        self.coin = coin
        self.url = url
        self.port = port
        self.method = method
        self.params = params
        self.protocol = protocol

    def run(self):
        if self.protocol == "ssl":
            thread_electrum_ssl(self.coin, self.url, self.port, self.method, self.params)
        elif self.protocol == "tcp":
            thread_electrum(self.coin, self.url, self.port, self.method, self.params)
        elif self.protocol == "wss":
            thread_electrum_wss(self.coin, self.url, self.port, self.method, self.params)


def thread_electrum_wss(coin, url, port, method, params):
    x = ElectrumServer(coin, url, port, "WSS")
    resp = x.wss(method, params)
    el = parse_response(x, resp)

    if el.blockheight > 0:
        if coin not in passed_electrums_wss:
            passed_electrums_wss.update({coin:[]})
        passed_electrums_wss[coin].append(f"{url}:{port}")
        logger.calc(f"[WSS] {coin} {url}:{port} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_electrums_wss:
            failed_electrums_wss.update({coin:{}})
        failed_electrums_wss[coin].update({f"{url}:{port}": f"{el.result}"})
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
    
    if el.blockheight > 0:
        if coin not in passed_electrums_ssl:
            passed_electrums_ssl.update({coin:[]})
        passed_electrums_ssl[coin].append(f"{url}:{port}")
        logger.info(f"[SSL] {coin} {url}:{port} OK! Height: {el.blockheight}")
    else:
        if coin not in failed_electrums_ssl:
            failed_electrums_ssl.update({coin:{}})
        failed_electrums_ssl[coin].update({f"{url}:{port}": f"{el.result}"})
        logger.warning(f"[SSL] {coin} {url}:{port} Failed! | {el.result}")


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
                            "wss"
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
                                electrum["protocol"].lower()
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
                                "tcp"
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


def get_existing_report():
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



def get_electrums_report():
    current_time = int(time.time())
    existing_report = get_existing_report()
    electrum_dict = get_repo_electrums()
    protocol_lists = scan_electrums(electrum_dict)
    electrum_coins_ssl = set(protocol_lists['ssl'])
    electrum_coins = set(protocol_lists['tcp'])
    electrum_coins_wss = set(protocol_lists['wss'])

    num_electrums = len(electrum_coins) + len(electrum_coins_ssl) + len(electrum_coins_wss)
    i = 0
    while True:
        electrums_set = set(list(passed_electrums.keys()) + list(failed_electrums.keys())) - set(ignore_list)
        electrums_ssl_set = set(list(passed_electrums_ssl.keys()) + list(failed_electrums_ssl.keys())) - set(ignore_list)
        electrums_wss_set = set(list(passed_electrums_wss.keys()) + list(failed_electrums_wss.keys())) - set(ignore_list)
        electrums_pct = round(len(electrums_set) / len(electrum_coins) * 100, 2)
        electrums_ssl_pct = round(len(electrums_ssl_set) / len(electrum_coins_ssl) * 100, 2)
        electrums_wss_pct = round(len(electrums_wss_set) / len(electrum_coins_wss) * 100, 2)
        logger.query(f"TCP scan progress: {electrums_pct}% electrums ({len(electrums_set)}/{len(electrum_coins)})")
        if len(electrums_set) - len(electrum_coins) < 3:
            logger.query(electrum_coins.difference(electrums_set))
        logger.query(f"SSL scan progress: {electrums_ssl_pct}% electrums_ssl ({len(electrums_ssl_set)}/{len(electrum_coins_ssl)})")
        if len(electrums_ssl_set) - len(electrum_coins_ssl) < 3:
            logger.query(electrum_coins_ssl.difference(electrums_ssl_set))
        logger.query(f"WSS scan progress: {electrums_wss_pct}% electrums_wss ({len(electrums_wss_set)}/{len(electrum_coins_wss)})")
        if len(electrums_wss_set) - len(electrum_coins_wss) < 3:
            logger.query(electrum_coins_wss.difference(electrums_wss_set))
            
        if electrums_set == electrum_coins:
            if electrums_ssl_set == electrum_coins_ssl:
                if electrums_wss_set == electrum_coins_wss:
                    logger.info("Electrum scan complete!")
                    break
        if i > (num_electrums * 0.1 + 90):
            logger.warning("Electrum scan loop expired incomplete after 60 iterations.")
            break
        i += 1
        time.sleep(3)

    results = {}

    all_electrums = list(electrums_ssl_set.union(electrums_set).union(electrums_wss_set))
    all_electrums.sort()
    for coin in all_electrums:
        if coin in passed_electrums: passed = len(passed_electrums[coin])
        else: passed =  0
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
        results.update({
            coin: {
                "electrums_total_all": passed + failed + passed_ssl + failed_ssl + passed_wss + failed_wss,
                "electrums_working_all": passed + passed_ssl + passed_wss,
                "electrums_total_tcp": passed + failed,
                "electrums_working_tcp": passed,
                "electrums_total_ssl": passed_ssl + failed_ssl,
                "electrums_working_ssl": passed_ssl,
                "electrums_total_wss": passed_wss + failed_wss,
                "electrums_working_wss": passed_wss,
                "tcp": {},
                "ssl": {},
                "wss": {}
            }
        })

        if coin in passed_electrums:
            x = list(passed_electrums[coin])
            x.sort()
            for i in x:
                results[coin]["tcp"].update({
                    i: {
                        "last_connection": current_time,
                        "result": "Passed"
                    }
                })

        if coin in failed_electrums:
            x = list(failed_electrums[coin].keys())
            x.sort()
            for i in x:
                results[coin]["tcp"].update({
                    i: {
                        "last_connection": get_last_connection(existing_report, coin, "tcp", i),
                        "result": failed_electrums[coin][i]
                    }
                })

        if coin in passed_electrums_ssl:
            x = list(passed_electrums_ssl[coin])
            x.sort()
            for i in x:
                results[coin]["ssl"].update({
                    i: {
                        "last_connection": current_time,
                        "result": "Passed"
                    }
                })

        if coin in failed_electrums_ssl:
            x = list(failed_electrums_ssl[coin].keys())
            x.sort()
            for i in x:
                results[coin]["ssl"].update({
                    i: {
                        "last_connection": get_last_connection(existing_report, coin, "ssl", i),
                        "result": failed_electrums_ssl[coin][i]
                    }
                })

        if coin in passed_electrums_wss:
            x = list(passed_electrums_wss[coin])
            x.sort()
            for i in x:
                results[coin]["wss"].update({
                    i: {
                        "last_connection": current_time,
                        "result": "Passed"
                    }
                })

        if coin in failed_electrums_wss:
            x = list(failed_electrums_wss[coin].keys())
            x.sort()
            for i in x:
                results[coin]["wss"].update({
                    i: {
                        "last_connection": get_last_connection(existing_report, coin, "wss", i),
                        "result": failed_electrums_wss[coin][i]
                    }
                })

    with open(f"{script_path}/electrum_scan_report.json", "w+") as f:
        f.write(json.dumps(results, indent=4))

    # print(json.dumps(results, indent=4))
    return results

if __name__ == '__main__':
    get_electrums_report()
