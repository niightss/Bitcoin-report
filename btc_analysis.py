#!/usr/bin/env python3
"""
Bitcoin Transaction Analyzer

Fetches Bitcoin transaction history for a Bitcoin wallet address using the
Blockchain.com API, then calculates transaction statistics and activity trends.
"""

import sys
from datetime import datetime, timezone
from statistics import mean

import requests

API_BASE_URL = "https://blockchain.info/rawaddr/{address}"
DEFAULT_LIMIT = 50
REQUEST_TIMEOUT = 20
SATOSHIS_PER_BTC = 100_000_000


def validate_bitcoin_address(address: str) -> bool:
    """Validate basic Bitcoin address format."""
    return isinstance(address, str) and len(address.strip()) >= 26


def satoshis_to_btc(satoshis: int) -> float:
    """Convert satoshis to BTC."""
    return satoshis / SATOSHIS_PER_BTC


def fetch_transaction_data(address: str, limit: int = DEFAULT_LIMIT) -> dict:
    """Fetch transaction data from Blockchain.com API."""
    url = API_BASE_URL.format(address=address)

    headers = {
        "User-Agent": "BitcoinTransactionAnalyzer/1.0",
        "Accept": "application/json",
    }

    params = {
        "limit": limit,
        "cors": "true",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 429:
            raise RuntimeError("Rate limit reached. Please try again later.")

        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            raise RuntimeError("Unexpected API response format.")

        return data

    except requests.exceptions.Timeout:
        raise RuntimeError("Request timed out while contacting the API.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Network connection error. Check your internet connection.")
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"HTTP error from API: {exc}")
    except ValueError:
        raise RuntimeError("Failed to parse JSON response from API.")


def extract_transaction_value(tx: dict) -> int:
    """Estimate total transaction value in satoshis."""
    total_input = 0

    for tx_input in tx.get("inputs", []):
        previous_output = tx_input.get("prev_out", {})
        total_input += previous_output.get("value", 0)

    total_output = sum(output.get("value", 0) for output in tx.get("out", []))
    fee = tx.get("fee", 0)

    if total_input > 0:
        return max(total_input - fee, 0)

    return total_output


def classify_transaction(tx: dict, wallet_address: str) -> str:
    """Classify transaction direction for the provided wallet."""
    inputs = tx.get("inputs", [])
    outputs = tx.get("out", [])

    outgoing = any(
        tx_input.get("prev_out", {}).get("addr") == wallet_address
        for tx_input in inputs
    )

    incoming = any(
        output.get("addr") == wallet_address
        for output in outputs
    )

    if outgoing and incoming:
        return "self-transfer"
    if outgoing:
        return "outgoing"
    if incoming:
        return "incoming"

    return "unknown"


def build_activity_summary(timestamps: list[int]) -> str:
    """Build a short activity summary from transaction timestamps."""
    if len(timestamps) < 2:
        return "Not enough data to determine activity trend."

    timestamps.sort()

    first_tx = datetime.fromtimestamp(timestamps[0], tz=timezone.utc)
    last_tx = datetime.fromtimestamp(timestamps[-1], tz=timezone.utc)

    span_days = max((last_tx - first_tx).days, 1)
    transactions_per_day = len(timestamps) / span_days

    if transactions_per_day >= 5:
        return f"High activity: about {transactions_per_day:.1f} transactions per day."
    if transactions_per_day >= 1.5:
        return f"Moderate activity: about {transactions_per_day:.1f} transactions per day."

    return f"Low activity: about {transactions_per_day:.1f} transactions per day."


def analyze_transactions(data: dict, wallet_address: str) -> dict:
    """Analyze Bitcoin transaction data."""
    transactions = data.get("txs", [])

    if not transactions:
        return {
            "count": 0,
            "total_btc": 0.0,
            "average_btc": 0.0,
            "largest_btc": 0.0,
            "largest_hash": None,
            "incoming_count": 0,
            "outgoing_count": 0,
            "self_transfer_count": 0,
            "activity_summary": "No transactions found for this address.",
        }

    transaction_values = []
    incoming_count = 0
    outgoing_count = 0
    self_transfer_count = 0
    largest_transaction = None
    largest_value = 0
    timestamps = []

    for tx in transactions:
        value_sats = extract_transaction_value(tx)
        transaction_values.append(value_sats)

        tx_type = classify_transaction(tx, wallet_address)

        if tx_type == "incoming":
            incoming_count += 1
        elif tx_type == "outgoing":
            outgoing_count += 1
        elif tx_type == "self-transfer":
            self_transfer_count += 1

        if value_sats > largest_value:
            largest_value = value_sats
            largest_transaction = tx

        if tx.get("time"):
            timestamps.append(tx["time"])

    total_sats = sum(transaction_values)
    average_sats = int(mean(transaction_values)) if transaction_values else 0

    return {
        "count": len(transactions),
        "total_btc": satoshis_to_btc(total_sats),
        "average_btc": satoshis_to_btc(average_sats),
        "largest_btc": satoshis_to_btc(largest_value),
        "largest_hash": largest_transaction.get("hash") if largest_transaction else None,
        "incoming_count": incoming_count,
        "outgoing_count": outgoing_count,
        "self_transfer_count": self_transfer_count,
        "activity_summary": build_activity_summary(timestamps),
    }


def print_report(address: str, report: dict) -> None:
    """Print formatted Bitcoin transaction report."""
    print("\nBitcoin Transaction Report")
    print("=" * 40)
    print(f"Address: {address}")
    print(f"Transaction count: {report['count']}")
    print(f"Incoming transactions: {report['incoming_count']}")
    print(f"Outgoing transactions: {report['outgoing_count']}")
    print(f"Self-transfers: {report['self_transfer_count']}")
    print(f"Total value transferred: {report['total_btc']:.8f} BTC")
    print(f"Average transaction size: {report['average_btc']:.8f} BTC")
    print(f"Largest transaction: {report['largest_btc']:.8f} BTC")

    if report["largest_hash"]:
        print(f"Largest transaction hash: {report['largest_hash']}")

    print(f"Activity summary: {report['activity_summary']}")
    print("=" * 40)


def main() -> None:
    """Run Bitcoin Transaction Analyzer."""
    address = input("Enter a Bitcoin address: ").strip()

    if not validate_bitcoin_address(address):
        print("Invalid Bitcoin address format.")
        sys.exit(1)

    try:
        data = fetch_transaction_data(address)
        report = analyze_transactions(data, address)
        print_report(address, report)

    except RuntimeError as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
