#!/usr/bin/env python3
import requests
import json

supported_networks = {
    "BEP20": 56,
    "ERC20": 1,
    "FTM20": 250,
    "PLG20": 137,
    "PLG20_OLD": 137,
    "AVX20": 43114,
    "AVX20_OLD": 43114,
    "KRC20": 321,
    "HRC20": 128,
    "MVR20": 1285
}

supported_platforms = {
    "BNB": 56,
    "ERC20": 1,
    "FTM": 250,
    "POL": 137,
    "AVAX": 43114,
    "KCS": 321,
    "ETH-ARB20": 42161,
    "MOVR": 1285,
    "HT": 128,
    "IRIS": 6688,
}

exclude_protocols = ['UTXO', 'QRC20', "SLPTOKEN", "ZHTLC", "BCH", "QTUM", "tQTUM"]

def ensure_chainids():
    url = "https://chainid.network/chains_mini.json"
    networks = requests.get(url).json()

    with open('../coins', 'r') as f:
        coins = json.load(f)

    for i in coins:
        if 'chain_id' not in i:
            ticker = i['coin']
            if '-' in i:
                suffix = ticker.split('-')[1]
                ticker = ticker.split('-')[0]
            if 'protocol' in i:
                if 'type' in i['protocol']:
                    if i['protocol']['type'] in exclude_protocols:
                        continue
                    elif i['protocol']['type'] == 'ERC20':
                        if 'protocol_data' in i:
                            if 'platform' in i['protocol']['protocol_data']:
                                platform = i['protocol']['protocol_data']['platform']
                                if 'chain_id' in platform:
                                    continue
                                if platform in supported_platforms:
                                    network = supported_platforms[platform]
                                    print(f"$$$ Chain ID set to {network} for {ticker}")
                                else:
                                    print(f"!!! Unknown platform type for {ticker}: {i}")
                    elif i['protocol']['type'] in ['TENDERMINTTOKEN', 'TENDERMINT']:
                        print(ticker)
                    elif i['protocol']['type'] in ['ETH']:
                        print(ticker)
                    else:
                        print(f"^^^ Unknown protocol type for {ticker}: {i}")
                                
                        continue
                print(f"Chain ID not found for {ticker}")
                suffix = None
                if suffix in ['QRC20', 'SLP']:
                    continue
                if suffix in supported_networks:
                    network = supported_networks[suffix]
                    print(f"!!! Chain ID set to {network} for {ticker}")
                else:
                    for j in networks:
                        if "nativeCurrency" in []:
                            if j['nativeCurrency']['symbol'] == ticker:
                                i['chain_id'] = j
                                print(f">>> Chain ID set to {j} for {ticker}")
                                break

