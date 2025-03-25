import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

# Create module-level logger
log = logging.getLogger(__name__)

# Add the parent directory to the path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich import box

# Import Rich for beautiful terminal UI
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from bitcoin_monitor import (
    BitcoinAddressMonitor,
    MacOSNotifier,
    format_transaction_message,
    is_valid_address,
)

# Initialize console
console = Console()


def display_header(title: str) -> None:
    """Display a styled header."""
    console.print()
    console.print(Panel(title, style="bold cyan", expand=False))


def format_btc(amount: float) -> Text:
    """Format Bitcoin amount with color."""
    text = Text(f"{amount:.8f} BTC")
    if amount > 0:
        text.stylize("bold green")
    return text


def format_tx_id(tx_id: str) -> Text:
    """Format transaction ID with truncation."""
    if len(tx_id) > 20:
        display_id = tx_id[:8] + "..." + tx_id[-8:]
    else:
        display_id = tx_id
    return Text(display_id, style="yellow")


def cleanup_spinners(address_display):
    """Cleanup all spinner objects to ensure they're removed from the display when exiting."""
    if address_display is None:
        return

    # Stop all progress spinner objects to clean up display
    if not address_display.balance_btc_data:
        address_display.balance_btc_progress.stop()
    if not address_display.balance_usd_data:
        address_display.balance_usd_progress.stop()
    if not address_display.tx_count_data:
        address_display.tx_count_progress.stop()


class AddressInfoDisplay:
    """Class to handle progressive display of address information with spinners."""

    def __init__(self, address: str, debug: bool = False):
        self.address = address
        self.debug = debug

        # Create Progress objects for each spinner (just spinner, no text)
        self.balance_btc_progress = Progress(
            SpinnerColumn(), auto_refresh=False, expand=False
        )
        self.balance_btc_task = self.balance_btc_progress.add_task("", total=None)

        self.balance_usd_progress = Progress(
            SpinnerColumn(), auto_refresh=False, expand=False
        )
        self.balance_usd_task = self.balance_usd_progress.add_task("", total=None)

        self.tx_count_progress = Progress(
            SpinnerColumn(), auto_refresh=False, expand=False
        )
        self.tx_count_task = self.tx_count_progress.add_task("", total=None)

        # Store completed data
        self.balance_btc_data = None
        self.balance_usd_data = None
        self.tx_count_data = None

        # Validate the address - this doesn't need a spinner as it's fast
        self.is_valid, self.address_type = is_valid_address(address)

    def update(self, address_info: Dict[str, Any]) -> None:
        """Update the display with available information."""
        # Update with actual data once available
        if "balance_btc" in address_info:
            balance_btc = address_info.get("balance_btc", 0)
            balance_text = Text()
            balance_text.append("₿ ", style="bright_yellow")
            balance_text.append(f"{balance_btc:.8f}", style="bold green")
            self.balance_btc_data = balance_text

        if "balance_usd" in address_info:
            balance_usd = address_info.get("balance_usd")
            if balance_usd is not None:
                usd_text = Text()
                usd_text.append("$ ", style="bright_yellow")
                usd_text.append(f"{balance_usd:,.2f}", style="green")
                self.balance_usd_data = usd_text
            else:
                self.balance_usd_data = Text("Not available", style="dim")

        if "transaction_count" in address_info:
            tx_count = address_info.get("transaction_count", 0)
            self.tx_count_data = Text(str(tx_count), style="bold cyan")

    def __rich__(self) -> Panel:
        """Generate the rich display for this address info."""
        # Create a grid for the layout
        grid = Table.grid(expand=False)
        grid.add_column(style="cyan")
        grid.add_column()

        # Add validation status if needed
        if not self.is_valid:
            validation_text = Text("INVALID ADDRESS FORMAT", style="red bold")
            console.print(
                Panel(
                    validation_text,
                    title="⚠️ Address Validation Error",
                    border_style="red",
                )
            )
        elif self.debug:
            validation_text = Text(
                f"Valid {self.address_type.capitalize()} Address", style="green bold"
            )
            console.print(Panel(validation_text, title="Address Validation"))

        balance_label = Text("💰 balance   ", style="dim")
        grid.add_row(
            balance_label,
            self.balance_btc_data
            if self.balance_btc_data
            else self.balance_btc_progress,
        )

        if self.balance_usd_data:
            grid.add_row("", self.balance_usd_data)

        grid.add_row("", "")

        txs_label = Text("⚡️ txs        ", style="dim")
        grid.add_row(
            txs_label,
            self.tx_count_data if self.tx_count_data else self.tx_count_progress,
        )

        # Create the panel with the full address as title
        return Panel(
            grid,
            title=self.address,
            box=box.ROUNDED,
            border_style="blue",
            padding=(1, 2),
        )


def display_address_info(
    address: str, address_info: Dict[str, Any], debug: bool = False
) -> None:
    """Display address information in a styled table."""
    # Create display object
    address_display = AddressInfoDisplay(address, debug)

    # Update with all available info
    address_display.update(address_info)

    # Print the panel
    console.print(address_display)


def display_transactions(transactions: List[Dict[str, Any]]) -> None:
    """Display transactions in a styled table."""
    if not transactions:
        return

    table = Table(show_header=True, box=box.ROUNDED)
    table.add_column("#", style="dim")
    table.add_column("Transaction ID", style="yellow")
    table.add_column("Time", style="cyan")

    for i, tx in enumerate(transactions[:5], 1):  # Show up to 5 recent transactions
        tx_id = tx.get("txid", "Unknown")
        time_str = "Unknown"

        if "time" in tx:
            time_str = datetime.fromtimestamp(tx["time"]).strftime("%Y-%m-%d %H:%M:%S")
        elif "blocktime" in tx:
            time_str = datetime.fromtimestamp(tx["blocktime"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        table.add_row(str(i), format_tx_id(tx_id), time_str)

    console.print(Panel(table, title="Recent Transactions"))


# Callback function has been integrated directly into display_updating_callback


def main():
    # Set up terminal UI
    console.clear()
    display_header("🔍 Bitcoin Address Monitor")

    parser = argparse.ArgumentParser(
        description="Monitor a Bitcoin address for transactions"
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
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )
    args = parser.parse_args()

    # Configure logging centrally
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create monitor instance with new logging paradigm
    monitor = BitcoinAddressMonitor()

    try:
        # Create the display object for progressive updates
        address_display = AddressInfoDisplay(args.address, debug=args.verbose)

        # Shared data between threads
        shared_data = {"address_info": {}, "is_complete": False, "error": None}

        # Progressive callback function
        def progressive_update(partial_result):
            # Update the shared data with the partial result
            shared_data["address_info"].update(partial_result)

            # Mark as complete if we have recent_transactions
            if "recent_transactions" in partial_result:
                shared_data["is_complete"] = True

        # Function to fetch data in background
        def fetch_address_info():
            try:
                # Get the actual data with progressive updates
                result = monitor.get_address_info(args.address)

                # Process the result in stages to simulate progressive updates
                # Using minimal delays to create a progressive effect without excessive waiting

                # First update balance only
                if "balance_btc" in result:
                    partial = {"balance_btc": result["balance_btc"]}
                    progressive_update(partial)
                    time.sleep(0.2)  # Minimal delay

                # Then update USD amount
                if "balance_usd" in result:
                    partial = {"balance_usd": result["balance_usd"]}
                    progressive_update(partial)
                    time.sleep(0.2)  # Minimal delay

                # Always provide values for the remaining fields, even if null
                # This ensures the spinners get replaced with something

                # Create a final update with all available data
                partial = {}

                # Include everything we have in the result
                if "transaction_count" in result:
                    partial["transaction_count"] = result["transaction_count"]
                if "total_received_satoshis" in result:
                    partial["total_received_satoshis"] = result[
                        "total_received_satoshis"
                    ]
                if "total_sent_satoshis" in result:
                    partial["total_sent_satoshis"] = result["total_sent_satoshis"]

                # Always include transaction count to ensure the spinner gets replaced
                if (
                    "transaction_count" not in partial
                    and "recent_transactions" in result
                ):
                    partial["transaction_count"] = len(
                        result.get("recent_transactions", [])
                    )

                # Always include recent transactions so we can mark as complete
                partial["recent_transactions"] = result.get("recent_transactions", [])

                progressive_update(partial)

                # Ensure completion is marked if for some reason the callback didn't do it
                shared_data["is_complete"] = True

            except Exception as e:
                shared_data["error"] = str(e)

        # Create a Live display to update the panel progressively
        with Live(address_display, refresh_per_second=10) as live:
            try:
                # Start the background thread
                monitor_thread = threading.Thread(
                    target=fetch_address_info, daemon=True
                )
                monitor_thread.start()

                # Update the display while the data is being fetched
                start_time = time.time()
                last_update = {}

                while not shared_data["is_complete"] and shared_data["error"] is None:
                    # Check for timeout (60 seconds)
                    if time.time() - start_time > 60:
                        raise TimeoutError(
                            "Timed out while fetching address information"
                        )

                    # Always update the display with latest data
                    current_data = shared_data["address_info"].copy()
                    if current_data != last_update:
                        # Update display with new data
                        address_display.update(current_data)
                        last_update = current_data.copy()

                    if not address_display.balance_btc_data:
                        address_display.balance_btc_progress.refresh()
                    if not address_display.balance_usd_data:
                        address_display.balance_usd_progress.refresh()
                    if not address_display.tx_count_data:
                        address_display.tx_count_progress.refresh()

                    live.refresh()

                    time.sleep(0.1)

                # Check if there was an error
                if shared_data["error"] is not None:
                    raise Exception(shared_data["error"])

                # Final update with complete data
                address_info = shared_data["address_info"]

                # Make a final update of all display values with the actual data
                address_display.update(address_info)

                if not address_display.tx_count_data:
                    if "recent_transactions" in address_info:
                        tx_count = len(address_info.get("recent_transactions", []))
                        address_display.tx_count_data = Text(
                            str(tx_count), style="bold cyan"
                        )
                    else:
                        address_display.tx_count_data = Text("0", style="bold cyan")
                live.update(address_display)

            except Exception as e:
                # Log and re-raise the exception
                console.print(f"[bold red]Error fetching address info:[/] {str(e)}")
                raise
            finally:
                # Ensure all spinners are properly cleaned up
                cleanup_spinners(address_display)

        # Do NOT display any panel here - we want to keep the panel that was shown with spinners
        # and let it transition naturally to the monitoring phase

        # Display recent transactions if any (these will appear below the panel)
        recent_txs = address_info.get("recent_transactions", [])
        if recent_txs:
            display_transactions(recent_txs)

        # Transaction counter for callback
        tx_counter = 0

        # Callback that will be invoked when new transactions are found
        def display_updating_callback(address, transactions):
            nonlocal tx_counter, live_display

            # Temporarily pause the live display
            live.stop()

            console.print("\n[bold cyan]Found new transactions![/]")

            # Process transactions
            for tx in transactions:
                # Update transaction counter
                tx_counter += 1

                # Send notifications - automatically uses macOS notifications
                # when running on a macOS system without any additional configuration
                title = "New Bitcoin Transaction"
                message = format_transaction_message(address, tx)
                notifier = MacOSNotifier()
                notifier.notify(title, message)

                # Create transaction info table
                table = Table(show_header=False, box=box.ROUNDED)
                table.add_column("Property", style="cyan")
                table.add_column("Value")

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

                # Add transaction details to table
                table.add_row("Transaction ID", format_tx_id(tx_id))
                table.add_row("Time", time_str)

                # Show transaction panel
                tx_panel = Panel(
                    table,
                    title=f"🔔 NEW TX FOR {address}",
                    border_style="green",
                    box=box.ROUNDED,
                )
                console.print(tx_panel)

            # Update the live display with the new transaction count
            live_display = make_live_display(
                address=short_address,
                last_check=datetime.now().strftime("%H:%M:%S"),
                countdown="waiting...",
                tx_count=tx_counter,
                checking=False,
                countdown_obj=None,
            )

            # Resume the live display with updated content
            live.start(live_display)

        # Create a two-line display using a single Live display

        # Format abbreviated address
        short_address = args.address[:6] + "..." + args.address[-6:]

        # Create the status display with two lines
        def make_live_display(
            address=short_address,
            last_check="Starting...",
            countdown="waiting...",
            tx_count=0,
            checking=False,
            countdown_obj=None,
        ):
            line1 = Text()
            line1.append("🔍 ", style="cyan")
            line1.append(address, style="cyan")
            line1.append(" | ", style="dim")
            line1.append("🕒 ", style="yellow")
            line1.append(last_check, style="yellow")
            line1.append(" | ", style="dim")

            # Build the second part based on state and if a spinner object is provided
            line1_part2 = Group()

            # Use different emoji for checking state vs countdown state
            if checking:
                if countdown_obj:
                    # Use the Progress spinner object directly
                    check_text = Text("⚙️ ", style="magenta")  # Gear emoji in magenta
                    line1_part2 = Group(check_text, countdown_obj)
                else:
                    line1.append(
                        "⚙️ ", style="magenta"
                    )  # Gear emoji for active processing
                    line1.append(countdown, style="magenta")
            else:
                line1.append("⏱️ ", style="blue")  # Timer emoji for countdown
                # Split the countdown to make just "remaining" faint
                if "remaining" in countdown:
                    parts = countdown.split(" remaining")
                    line1.append(parts[0], style="blue")
                    line1.append(" remaining", style="dim")
                else:
                    line1.append(countdown, style="blue")

            line2 = Text()
            line2.append("   ⚡️ ", style="green")
            line2.append(f"{tx_count}", style="bold yellow")  # Number in bold yellow
            line2.append(
                " txs detected", style="dim"
            )  # Text in lowercase and very faint with no color

            # Return different layouts based on whether we have a spinner object
            if checking and countdown_obj:
                # Line1 is already built as text up to the checking part
                return Group(Group(line1, line1_part2), line2)
            else:
                # Standard text-only return
                return Group(line1, line2)

        # Create initial display with current time
        now = datetime.now()
        initial_check_time = now.strftime("%H:%M:%S")
        live_display = make_live_display(
            address=short_address,
            last_check=initial_check_time,
            countdown=f"{args.interval}s remaining",
            tx_count=tx_counter,
            checking=False,
            countdown_obj=None,
        )

        # Track the next check time for countdown calculation
        next_check_time = now + timedelta(seconds=args.interval)

        # Start the live display
        with Live(live_display, refresh_per_second=4) as live:
            # Create a simple logger that logs to console and updates countdown timer
            class SimpleLogger:
                def __init__(self):
                    self.last_check_time = datetime.now()
                    # Start the initial countdown timer
                    self._update_countdown_timer()

                def debug(self, message):
                    if "Checking address:" in message:
                        nonlocal next_check_time, tx_counter, live_display
                        now = datetime.now()
                        self.last_check_time = now

                        # Create a Progress with spinner for checking status
                        checking_spinner = Progress(
                            SpinnerColumn(),
                            TextColumn("checking..."),
                            auto_refresh=False,
                            expand=False,
                        )
                        checking_spinner.add_task("", total=None)

                        # Update the spinner to keep it animated
                        checking_spinner.refresh()

                        live_display = make_live_display(
                            address=short_address,
                            last_check=now.strftime("%H:%M:%S"),
                            countdown_obj=checking_spinner,  # Pass the spinner object
                            tx_count=tx_counter,
                            checking=True,
                        )
                        live.update(live_display)

                        # After returning from check, update with countdown
                        # Calculate next check time for countdown
                        next_check_time = now + timedelta(seconds=args.interval)

                        # Now update with the countdown timer
                        live_display = make_live_display(
                            address=short_address,
                            last_check=now.strftime("%H:%M:%S"),
                            countdown=f"{args.interval}s remaining",
                            tx_count=tx_counter,
                            checking=False,
                            countdown_obj=None,
                        )
                        live.update(live_display)

                        # Start a countdown timer update thread
                        self._update_countdown_timer()

                def _update_countdown_timer(self):
                    # Update the countdown timer in a separate thread
                    def update_timer():
                        nonlocal next_check_time, live_display
                        if not next_check_time:
                            return

                        while True:
                            # Calculate remaining time
                            now = datetime.now()
                            if next_check_time <= now:
                                # Show checking indicator with spinner instead of 0s
                                checking_spinner = Progress(
                                    SpinnerColumn(),
                                    TextColumn("checking..."),
                                    auto_refresh=False,
                                    expand=False,
                                )
                                checking_spinner.add_task("", total=None)

                                # Update the spinner to keep it animated
                                checking_spinner.refresh()

                                new_display = make_live_display(
                                    address=short_address,
                                    last_check=self.last_check_time.strftime("%H:%M:%S")
                                    if self.last_check_time
                                    else "Starting...",
                                    countdown_obj=checking_spinner,
                                    tx_count=tx_counter,
                                    checking=True,
                                )
                                live.update(new_display)
                                break

                            remaining = (next_check_time - now).total_seconds()
                            remaining = max(
                                1, int(remaining)
                            )  # Min 1s to avoid showing 0s

                            # Update the live display with new countdown
                            new_display = make_live_display(
                                address=short_address,
                                last_check=self.last_check_time.strftime("%H:%M:%S")
                                if self.last_check_time
                                else "Starting...",
                                countdown=f"{remaining}s remaining",
                                tx_count=tx_counter,
                                checking=False,
                                countdown_obj=None,
                            )

                            # Update the live display
                            live_display = new_display
                            try:
                                live.update(live_display)
                            except Exception:
                                # The live display might have been stopped
                                break

                            # Update every second
                            time.sleep(0.9)

                    # Start timer in background thread
                    thread = threading.Thread(target=update_timer)
                    thread.daemon = True
                    thread.start()

                def info(self, message):
                    pass

                def warning(self, message):
                    pass

                def error(self, message):
                    pass

            # We'll use the custom SimpleLogger to intercept debug messages
            # for UI purposes. This is a special case where we need specific UI behavior.
            simple_logger = SimpleLogger()

            # Keep a reference to debug function
            original_debug_fn = log.debug

            # Create a wrapper to intercept debug messages
            def debug_wrapper(message):
                # Let SimpleLogger process messages that affect UI
                if "Checking address:" in message:
                    simple_logger.debug(message)
                # Still log to regular logger
                original_debug_fn(message)

            try:
                # Temporarily replace log.debug with our wrapper
                log.debug = debug_wrapper

                # Start the actual monitoring
                monitor.monitor_addresses(
                    addresses=[args.address],
                    callback=display_updating_callback,
                    interval_seconds=args.interval,
                )
            finally:
                # Restore original debug function
                log.debug = original_debug_fn

    except KeyboardInterrupt:
        # Cleanup spinners
        cleanup_spinners(address_display if "address_display" in locals() else None)
        # Let the user know we're exiting
        console.print("\n[bold magenta]Monitoring stopped by user[/]")
    except Exception as e:
        # Cleanup spinners
        cleanup_spinners(address_display if "address_display" in locals() else None)
        console.print(f"\n[bold red]Error:[/] {str(e)}")


if __name__ == "__main__":
    main()
