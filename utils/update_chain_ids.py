#!/usr/bin/env python3
import json

# Load the JSON data from file
with open('../coins', 'r') as f:
    coins = json.load(f)

# Process each coin in the list
for coin in coins:
    protocol = coin.get("protocol", {})
    if protocol.get("type") in ["ETH", "AVAX", "MATIC", "BNB", "KCS"]:
        # Ensure protocol_data exists
        protocol_data = protocol.setdefault("protocol_data", {})
        # Duplicate chain_id if it exists at top level
        if "chain_id" in coin:
            protocol_data["chain_id"] = coin["chain_id"]

# Write the updated data back to file or print to stdout
with open('../coins_updated', 'w') as f:
    json.dump(coins, f, indent=2)

print("Transformation complete. Output saved to coins_updated")
