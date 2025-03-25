import os
import sys

# Add the parent directory to the path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitcoin_monitor import (
    BitcoinAddressMonitor,
    MacOSNotifier,
    format_transaction_message,
)


def transaction_callback(address, transactions):
    """Called when new transactions are detected"""
    notifier = MacOSNotifier()

    for tx in transactions:
        title = "New Bitcoin Transaction"
        message = format_transaction_message(address, tx)
        notifier.notify(title, message)
        print(f"\n{message}\n")


def main():
    # Bitcoin addresses to monitor (examples - replace with your own)
    addresses = [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Bitcoin genesis address
        # Add your addresses here
    ]

    # Create a monitor instance
    monitor = BitcoinAddressMonitor(debug=True)

    # Show info for each address
    for address in addresses:
        print(f"Monitoring address: {address}")

        # Show current balance and transaction info
        address_info = monitor.get_address_info(address)
        print(f"  Balance: {address_info.get('balance_btc', 0):.8f} BTC")
        print(f"  Transaction count: {address_info.get('transaction_count', 0)}")

    # Monitor for new transactions
    print("\nMonitoring for new transactions...")
    print("Press Ctrl+C to stop")

    try:
        monitor.monitor_addresses(
            addresses=addresses,
            callback=transaction_callback,
            interval_seconds=60,  # Check every 60 seconds
        )
    except KeyboardInterrupt:
        print("\nMonitoring stopped")


if __name__ == "__main__":
    main()
