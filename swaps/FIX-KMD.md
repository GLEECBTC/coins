# FIX (FixedCoin)

## Coin Information

**Ticker:** FIX  
**Full Name:** FixedCoin  
**Type:** UTXO-based cryptocurrency  
**Block Time:** ~10 minutes  
**Decimals:** 8

**Official Links:**
- Website: https://web.fixedcoin.org/
- Explorer: https://explorer.fixedcoin.org/
- GitHub: https://github.com/biigbang0001/fixedcoin

---

## Blockchain Parameters
```json
{
  "coin": "FIX",
  "name": "fixedcoin",
  "fname": "FixedCoin",
  "rpcport": 24761,
  "txversion": 1,
  "pubtype": 1,
  "p2shtype": 0,
  "wiftype": 128,
  "txfee": 1000,
  "dust": 10000,
  "mm2": 1,
  "required_confirmations": 3,
  "mature_confirmations": 101,
  "avg_blocktime": 600,
  "decimals": 8,
  "protocol": {
    "type": "UTXO",
    "bip44": 0
  },
  "derivation_path": "m/44'/0'",
  "sign_message_prefix": "FixedCoin Signed Message:
",
  "links": {
    "github": "https://github.com/biigbang0001/fixedcoin",
    "homepage": "https://web.fixedcoin.org"
  }
}

```

---

## Electrum Servers

**Primary Server:**
- URL: `electrumx.fixedcoin.org:50002`
- Protocol: SSL
- Status: Active and tested ✅

**Secondary Server:**
- URL: `electrumx.nitopool.fr:50002`
- Protocol: SSL
- Status: Active and tested ✅

---

## Test Atomic Swap Details

### Test Information
- **Date:** October 25, 2025
- **KDF Version:** 2.1.0-beta_35e923949
- **Trading Pair:** FIX/KMD
- **Network ID:** 8762

### Swap Parameters
- **Base Coin:** FIX
- **Rel Coin:** KMD
- **Volume:** 0.02 FIX
- **Price:** 0.05 KMD per FIX
- **Total Value:** 0.001 KMD

---

## Atomic Swap Transaction IDs

**1. Taker Fee Transaction**
```
TXID: 25f0b74ec0a516ccabd91ef7b72bb009afc0180e8e04a241012973f882bc412a
Explorer: https://kmdexplorer.io/tx/25f0b74ec0a516ccabd91ef7b72bb009afc0180e8e04a241012973f882bc412a
Description: Taker pays the dex fee
```

**2. Maker Payment Transaction**
```
TXID: 00e9399f69ee7f471364281e8c7b534c95614118dcd0ae81af93a9e814348e63
Explorer: https://kmdexplorer.io/tx/00e9399f69ee7f471364281e8c7b534c95614118dcd0ae81af93a9e814348e63
Description: Maker sends KMD to HTLC
```

**3. Taker Payment Transaction**
```
TXID: d57940fff1fa8bd26a833f369035664c048c59201b8996e5361faebfbe71cd60
Explorer: https://explorer.fixedcoin.org/tx/d57940fff1fa8bd26a833f369035664c048c59201b8996e5361faebfbe71cd60
Description: Taker sends FIX to HTLC
```

**4. Taker Payment Spent Transaction**
```
TXID: 505303d8f09ac3a9cb4e144445a04f5d79fe784e94e23659bcee1801bffcfb7f
Explorer: https://explorer.fixedcoin.org/tx/505303d8f09ac3a9cb4e144445a04f5d79fe784e94e23659bcee1801bffcfb7f
Description: Maker claims FIX from HTLC
```

**5. Maker Payment Spent Transaction**
```
TXID: b26fd07d3a8232fba335f9e5c14ea52741dbe39596211c4c85a2e5c643fa0598
Explorer: https://kmdexplorer.io/tx/b26fd07d3a8232fba335f9e5c14ea52741dbe39596211c4c85a2e5c643fa0598
Description: Taker claims KMD from HTLC
```

---

## Testing Notes

- ✅ Electrum server connectivity verified
- ✅ Coin activation successful
- ✅ Atomic swap completed successfully
- ✅ All 5 TXIDs collected and verified
