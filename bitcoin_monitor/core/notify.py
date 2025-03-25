import smtplib
import ssl
import subprocess
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List


class NotificationHandler:
    """Base class for notification handlers"""

    def notify(self, title: str, message: str) -> None:
        """Send a notification"""
        raise NotImplementedError("Subclasses must implement notify method")


class MacOSNotifier(NotificationHandler):
    """Send notifications using native macOS notification system

    This notifier is automatically used when running on macOS platforms.
    It requires no additional configuration and uses the native macOS
    notification center to display transaction alerts.
    """

    def notify(self, title: str, message: str) -> None:
        """
        Send a notification using the macOS notification center.

        This method uses AppleScript (via osascript) to display notifications
        and works automatically when run on macOS systems.

        Args:
            title: Notification title
            message: Notification message
        """
        # Escape double quotes in title and message
        title = title.replace('"', '\\"')
        message = message.replace('"', '\\"')

        apple_script = f"""
        display notification "{message}" with title "{title}"
        """

        try:
            subprocess.run(["osascript", "-e", apple_script], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to send macOS notification: {str(e)}")


class EmailNotifier(NotificationHandler):
    """Send notifications via email"""

    def __init__(
        self,
        smtp_server: str,
        port: int,
        sender_email: str,
        password: str,
        recipient_email: str,
    ):
        """
        Initialize email notifier.

        Args:
            smtp_server: SMTP server address
            port: SMTP server port
            sender_email: Email address to send from
            password: Email password or app password
            recipient_email: Email address to send to
        """
        self.smtp_server = smtp_server
        self.port = port
        self.sender_email = sender_email
        self.password = password
        self.recipient_email = recipient_email

    def notify(self, title: str, message: str) -> None:
        """
        Send an email notification.

        Args:
            title: Email subject
            message: Email body
        """
        msg = MIMEMultipart()
        msg["Subject"] = title
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email

        msg.attach(MIMEText(message, "plain"))

        context = ssl.create_default_context()

        try:
            with smtplib.SMTP_SSL(
                self.smtp_server, self.port, context=context
            ) as server:
                server.login(self.sender_email, self.password)
                server.send_message(msg)
        except Exception as e:
            print(f"Failed to send email notification: {str(e)}")


class MultiNotifier(NotificationHandler):
    """Send notifications to multiple handlers"""

    def __init__(self, handlers: List[NotificationHandler]):
        """
        Initialize with a list of notification handlers.

        Args:
            handlers: List of NotificationHandler instances
        """
        self.handlers = handlers

    def notify(self, title: str, message: str) -> None:
        """
        Send notifications through all registered handlers.

        Args:
            title: Notification title
            message: Notification message
        """
        for handler in self.handlers:
            try:
                handler.notify(title, message)
            except Exception as e:
                print(f"Handler {handler.__class__.__name__} failed: {str(e)}")


def format_transaction_message(address: str, tx: Dict[str, Any]) -> str:
    """
    Format a transaction notification message.

    Args:
        address: Bitcoin address
        tx: Transaction data from bit library API

    Returns:
        Formatted message string
    """
    # The bit library transaction format is different from Blockchain.info
    # Calculate the net amount for this address
    tx_id = tx.get("txid", "Unknown")

    # Extract amounts from the transaction
    received = 0
    sent = 0

    # Check outputs (vout) for received amounts
    for output in tx.get("vout", []):
        script_pubkey = output.get("scriptPubKey", {})
        addresses = script_pubkey.get("addresses", [])

        if address in addresses:
            received += int(
                float(output.get("value", 0)) * 100000000
            )  # Convert BTC to satoshis

    # Check inputs (vin) for sent amounts
    for input_tx in tx.get("vin", []):
        prev_addresses = (
            input_tx.get("prevout", {}).get("scriptPubKey", {}).get("addresses", [])
        )

        if address in prev_addresses:
            value = input_tx.get("prevout", {}).get("value", 0)
            sent += int(float(value) * 100000000)  # Convert BTC to satoshis

    # Calculate net amount
    net_amount = received - sent

    # Convert satoshis to BTC
    btc_amount = abs(net_amount) / 100000000

    # Format the message
    if net_amount > 0:
        action = f"received {btc_amount:.8f} BTC"
    else:
        action = f"sent {btc_amount:.8f} BTC"

    # Get timestamp if available
    time_str = "Unknown"
    if "time" in tx:
        time_str = datetime.fromtimestamp(tx["time"]).strftime("%Y-%m-%d %H:%M:%S")
    elif "blocktime" in tx:
        time_str = datetime.fromtimestamp(tx["blocktime"]).strftime("%Y-%m-%d %H:%M:%S")

    # Build message
    message = f"Address {address}\n{action}\nTx: {tx_id}\nTime: {time_str}"

    # Add confirmation count if available
    if "confirmations" in tx:
        message += f"\nConfirmations: {tx['confirmations']}"

    return message
