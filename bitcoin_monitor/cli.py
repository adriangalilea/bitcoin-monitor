import argparse
import logging
import sys
from typing import Any, Dict, List

# Create module logger
log = logging.getLogger(__name__)

from bitcoin_monitor.core.monitor import BitcoinAddressMonitor
from bitcoin_monitor.core.notify import (
    EmailNotifier,
    MacOSNotifier,
    MultiNotifier,
    format_transaction_message,
)


def configure_notifiers(args):
    """Configure notification handlers based on command line arguments"""
    handlers = []

    # macOS notifications (default)
    if args.macos_notify or (not args.email_notify):
        handlers.append(MacOSNotifier())

    # Email notifications
    if args.email_notify:
        if not all(
            [
                args.smtp_server,
                args.smtp_port,
                args.email_from,
                args.email_password,
                args.email_to,
            ]
        ):
            print(
                "Error: Email notification requires --smtp-server, --smtp-port, "
                "--email-from, --email-password, and --email-to"
            )
            sys.exit(1)

        handlers.append(
            EmailNotifier(
                smtp_server=args.smtp_server,
                port=args.smtp_port,
                sender_email=args.email_from,
                password=args.email_password,
                recipient_email=args.email_to,
            )
        )

    return MultiNotifier(handlers)


def transaction_callback(notifier, address: str, transactions: List[Dict[str, Any]]):
    """Callback function for new transactions"""
    for tx in transactions:
        title = "New Bitcoin Transaction"
        message = format_transaction_message(address, tx)
        notifier.notify(title, message)
        log.info(f"ALERT: New transaction for {address}\n{message}")


def monitor_addresses(args):
    """Monitor Bitcoin addresses based on command line arguments"""
    addresses = args.addresses

    if not addresses:
        log.error("No Bitcoin addresses specified")
        return

    # Configure logging based on verbose flag
    log_level = logging.DEBUG if args.verbose else logging.INFO
    # Force output to stdout instead of default stderr
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Create monitor and notifier
    monitor = BitcoinAddressMonitor()
    notifier = configure_notifiers(args)

    # No validation needed
    for address in addresses:
        log.info(f"Monitoring address: {address}")

    # Define callback with access to the notifier
    def callback(addr, txs):
        return transaction_callback(notifier, addr, txs)

    # Start monitoring
    log.info(f"Monitoring {len(addresses)} Bitcoin address(es)...")
    log.info(f"Checking for new transactions every {args.interval} seconds")
    log.info("Press Ctrl+C to stop")

    try:
        monitor.monitor_addresses(
            addresses=addresses, callback=callback, interval_seconds=args.interval
        )
    except KeyboardInterrupt:
        log.info("Monitoring stopped by user")


def main():
    """Main entry point for the CLI"""
    parser = argparse.ArgumentParser(description="Bitcoin Address Monitor")

    # Main arguments
    parser.add_argument("addresses", nargs="*", help="Bitcoin addresses to monitor")
    parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=60,
        help="Check interval in seconds (default: 60)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    # Notification options
    notification_group = parser.add_argument_group("Notification Options")
    notification_group.add_argument(
        "--macos-notify",
        action="store_true",
        help="Enable macOS notifications (default)",
    )

    # Email notification options
    email_group = parser.add_argument_group("Email Notification Options")
    email_group.add_argument(
        "--email-notify", action="store_true", help="Enable email notifications"
    )
    email_group.add_argument("--smtp-server", help="SMTP server address")
    email_group.add_argument("--smtp-port", type=int, help="SMTP server port")
    email_group.add_argument("--email-from", help="Sender email address")
    email_group.add_argument("--email-password", help="Email password or app password")
    email_group.add_argument("--email-to", help="Recipient email address")

    args = parser.parse_args()

    monitor_addresses(args)


if __name__ == "__main__":
    main()
