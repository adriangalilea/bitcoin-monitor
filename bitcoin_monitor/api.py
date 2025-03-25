import threading
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field

from bitcoin_monitor.core.monitor import BitcoinAddressMonitor
from bitcoin_monitor.core.notify import (
    EmailNotifier,
    MacOSNotifier,
    MultiNotifier,
    format_transaction_message,
)


# Data models
class BitcoinAddress(BaseModel):
    address: str


class EmailConfig(BaseModel):
    smtp_server: str
    port: int
    sender_email: str
    password: str
    recipient_email: str


class MonitorConfig(BaseModel):
    addresses: List[str] = Field(default_factory=list)
    check_interval_seconds: int = 60
    enable_macos_notifications: bool = True
    email_config: Optional[EmailConfig] = None


# Create the FastAPI app
app = FastAPI(
    title="Bitcoin Address Monitor",
    description="A simple API for monitoring Bitcoin addresses and receiving notifications",
    version="0.1.0",
)

# Global state
monitor = BitcoinAddressMonitor()
monitor_thread = None
monitor_config = MonitorConfig()
is_monitoring = False


def get_notifier():
    """Configure and return a notifier based on the current config"""
    handlers = []

    if monitor_config.enable_macos_notifications:
        handlers.append(MacOSNotifier())

    if monitor_config.email_config:
        ec = monitor_config.email_config
        handlers.append(
            EmailNotifier(
                smtp_server=ec.smtp_server,
                port=ec.port,
                sender_email=ec.sender_email,
                password=ec.password,
                recipient_email=ec.recipient_email,
            )
        )

    if not handlers:
        handlers.append(MacOSNotifier())  # Default to macOS notifications

    return MultiNotifier(handlers)


def transaction_callback(address: str, transactions: List[Dict[str, Any]]):
    """Callback function for new transactions"""
    notifier = get_notifier()

    for tx in transactions:
        title = "New Bitcoin Transaction"
        message = format_transaction_message(address, tx)
        notifier.notify(title, message)


def start_monitoring_thread():
    """Start the monitoring thread"""
    global monitor_thread, is_monitoring

    if is_monitoring:
        return

    def monitor_task():
        monitor.monitor_continuously(
            callback=transaction_callback,
            interval_seconds=monitor_config.check_interval_seconds,
        )

    monitor_thread = threading.Thread(target=monitor_task, daemon=True)
    monitor_thread.start()
    is_monitoring = True


@app.get("/")
async def root():
    return {"message": "Bitcoin Address Monitor API"}


@app.get("/status")
async def status():
    """Get the current monitoring status"""
    addresses = list(monitor._monitored_addresses.keys())
    return {
        "is_monitoring": is_monitoring,
        "addresses_count": len(addresses),
        "addresses": addresses,
        "check_interval_seconds": monitor_config.check_interval_seconds,
        "enable_macos_notifications": monitor_config.enable_macos_notifications,
        "email_notifications_configured": monitor_config.email_config is not None,
    }


@app.post("/addresses")
async def add_address(address_data: BitcoinAddress, background_tasks: BackgroundTasks):
    """Add a Bitcoin address to monitor"""
    try:
        monitor.add_address(address_data.address)

        # Add to config
        if address_data.address not in monitor_config.addresses:
            monitor_config.addresses.append(address_data.address)

        # Start monitoring if not already started
        if not is_monitoring:
            background_tasks.add_task(start_monitoring_thread)

        return {
            "status": "success",
            "message": f"Now monitoring address: {address_data.address}",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/addresses/{address}")
async def remove_address(address: str):
    """Remove a Bitcoin address from monitoring"""
    try:
        monitor.remove_address(address)

        # Remove from config
        if address in monitor_config.addresses:
            monitor_config.addresses.remove(address)

        return {
            "status": "success",
            "message": f"Stopped monitoring address: {address}",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/addresses")
async def list_addresses():
    """List all monitored addresses"""
    addresses = {}
    for address in monitor._monitored_addresses:
        addresses[address] = {
            "balance_satoshis": monitor._monitored_addresses[address],
            "balance_btc": monitor._monitored_addresses[address] / 100000000,
        }

    return {"addresses": addresses, "count": len(addresses)}


@app.get("/addresses/{address}")
async def get_address_details(address: str):
    """Get details for a specific address"""
    # Check if we're monitoring this address
    try:
        if address in monitor._monitored_addresses:
            # For monitored addresses, get fresh data
            info = monitor.get_address_info(address)
            info["is_monitored"] = True
            return info
        else:
            # For non-monitored addresses, just get basic info
            info = monitor.get_address_info(address)
            info["is_monitored"] = False
            return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/config")
async def update_config(config: MonitorConfig, background_tasks: BackgroundTasks):
    """Update the monitoring configuration"""
    global monitor_config

    # Update the config
    monitor_config = config

    # Update monitored addresses
    current_addresses = set(monitor._monitored_addresses.keys())
    config_addresses = set(config.addresses)

    # Add new addresses
    for address in config_addresses - current_addresses:
        try:
            monitor.add_address(address)
        except Exception as e:
            print(f"Failed to add address {address}: {str(e)}")

    # Remove addresses no longer in config
    for address in current_addresses - config_addresses:
        monitor.remove_address(address)

    # Start monitoring if not already started and we have addresses
    if not is_monitoring and monitor_config.addresses:
        background_tasks.add_task(start_monitoring_thread)

    return {"status": "success", "message": "Configuration updated"}


@app.get("/config")
async def get_config():
    """Get the current configuration"""
    return monitor_config


def run_api(host="0.0.0.0", port=8000):
    """Run the FastAPI app"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_api()
