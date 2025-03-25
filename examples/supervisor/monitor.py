#!/usr/bin/env python3
import argparse
import logging
import sys

# Create module-level logger
log = logging.getLogger(__name__)

from datetime import datetime

# Import the bitcoin-monitor package
from bitcoin_monitor import (
    BitcoinAddressMonitor,
    MacOSNotifier,
    format_transaction_message,
    is_valid_address,
)


def setup_monitor(address, interval_seconds=30):
    """Set up and return a Bitcoin address monitor"""
    # First validate the address - this provides immediate feedback
    valid, address_type = is_valid_address(address)
    if not valid:
        # Use module logger for immediate error
        log.critical(f"ERROR: Invalid Bitcoin address: {address}")
        sys.exit(1)

    # Only create monitor if the address is valid
    monitor = BitcoinAddressMonitor()
    log.debug(f"Monitoring valid {address_type} address: {address}")

    try:
        address_info = monitor.get_address_info(address)
        balance_btc = address_info.get("balance_btc", 0)
        balance_usd = address_info.get("balance_usd", 0)
        tx_count = address_info.get("transaction_count", 0)

        log.debug(f"Current balance: {balance_btc:.8f} BTC (${balance_usd:.2f})")
        log.debug(f"Transaction count: {tx_count}")
        recent_txs = address_info.get("recent_transactions", [])
        if recent_txs:
            log.debug("Recent transactions:")
            for i, tx in enumerate(recent_txs[:5], 1):
                tx_id = tx.get("txid", "Unknown")
                time_str = "Unknown"

                if "time" in tx:
                    time_str = datetime.fromtimestamp(tx["time"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                elif "blocktime" in tx:
                    time_str = datetime.fromtimestamp(tx["blocktime"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                log.debug(f"  #{i}: {tx_id} at {time_str}")
    except Exception as e:
        log.warning(f"Could not get initial address info: {str(e)}")

    return monitor


def transaction_callback(address, transactions):
    """Callback function that will be invoked when new transactions are found"""
    log.info(f"ALERT: Found {len(transactions)} new transaction(s) for {address}")
    for tx in transactions:
        title = "New Bitcoin Transaction"
        message = format_transaction_message(address, tx)
        notifier = MacOSNotifier()
        notifier.notify(title, message)

        tx_id = tx.get("txid", "Unknown")
        time_str = "Unknown"

        if "time" in tx:
            time_str = datetime.fromtimestamp(tx["time"]).strftime("%Y-%m-%d %H:%M:%S")
        elif "blocktime" in tx:
            time_str = datetime.fromtimestamp(tx["blocktime"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        log.debug(f"Transaction ID: {tx_id}")
        log.debug(f"Time: {time_str}")
        log.debug(f"Message: {message}")
        log.debug("-" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Monitor a Bitcoin address for transactions (supervisord-friendly)"
    )
    parser.add_argument("address", help="Bitcoin address to monitor")
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=30,
        help="Check interval in seconds (default: 30)",
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    address = args.address
    interval = args.interval
    debug = args.debug

    # Configure logging centrally
    log_level = logging.DEBUG if debug else logging.INFO
    # This configures the root logger and all module loggers
    # Force output to stdout instead of default stderr
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Log startup message
    log.info(
        f"Starting Bitcoin address monitor for {address} (checking every {interval}s)"
    )

    # Create monitor (no log level needed as we've configured it centrally)
    monitor = setup_monitor(address, interval)

    try:
        monitor.monitor_addresses(
            addresses=[address],
            callback=transaction_callback,
            interval_seconds=interval,
        )
    except KeyboardInterrupt:
        log.info("Monitoring stopped by user")
    except Exception as e:
        log.error(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
