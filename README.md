# Bitcoin Monitor

[![Version](https://img.shields.io/badge/version-v0.1.0-blue.svg)](https://github.com/adriangalilea/bitcoin-monitor/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/adriangalilea/bitcoin-monitor/blob/main/LICENSE)

A simple Python library for monitoring Bitcoin addresses and receiving notifications about new transactions. This library uses the [bit](https://github.com/ofek/bit) library for Bitcoin operations.

## Features

- Monitor multiple Bitcoin addresses for new transactions
- Bitcoin address validation (legacy, SegWit, and Bech32 format support)
- Get notifications via:
  - macOS native notifications (automatically detected when running on macOS)
  - Email
- Simple REST API interface
- Command-line interface for quick monitoring
- [`supervisord`](https://supervisord.org/) [example config provided](examples/supervisor/supervisord.conf) and `bitcoin-supervisor start/stop/logs` provided out of the box.

## Installation

```bash
# Clone the repository
git clone https://github.com/adriangalilea/bitcoin-monitor.git
cd bitcoin-monitor

# Install with pip
pip install -e .

# Or install with Poetry
poetry install
```

## Usage

### As a Library

```python
from bitcoin_monitor import BitcoinAddressMonitor, MacOSNotifier, is_valid_address

# Create a monitor instance
monitor = BitcoinAddressMonitor()

# Check if an address is valid
address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"  # Example address
is_valid, address_type = is_valid_address(address)
if is_valid:
    print(f"Valid {address_type} address")
    
    # Add an address to monitor
    monitor.add_address(address)

    # Define a callback function for new transactions
    def on_new_transaction(address, transactions):
        notifier = MacOSNotifier()
        for tx in transactions:
            notifier.notify(
                title="New Bitcoin Transaction",
                message=f"Address {address} has a new transaction: {tx['txid']}"
            )

    # Start monitoring (will run until program exits)
    monitor.monitor_continuously(
        callback=on_new_transaction,
        interval_seconds=60  # Check every minute
    )
```

### Command-line Interface

```bash
# Monitor a single address with default options (macOS notifications)
bitcoin-monitor 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa

# Monitor multiple addresses, checking every 2 minutes
bitcoin-monitor 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa 3E8ociqZa9mZUSwGdSmAEMAoAxBK3FNDcd -i 120

# Monitor with email notifications
bitcoin-monitor 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa --email-notify \
    --smtp-server smtp.gmail.com --smtp-port 465 \
    --email-from your-email@gmail.com --email-password "your-app-password" \
    --email-to recipient@example.com


# Using supervisord for monitoring (with helper commands)
bitcoin-supervisor status        # Check monitoring status
bitcoin-supervisor start         # Start monitoring
bitcoin-supervisor stop          # Stop monitoring
bitcoin-supervisor logs          # View logs
bitcoin-supervisor logs -f       # Follow logs in real-time

# Or use bitcoin-supervisor with subcommands
bitcoin-supervisor status        # Same as above

# Using supervisord directly (if needed)
supervisorctl -c examples/supervisor/supervisord.conf status
```

### Examples

Check out the example scripts in the `examples` directory:

- `simple_monitor.py` - Basic monitoring example
- `monitor_address.py` - Enhanced monitoring example
- `supervisor/` - Supervisor integration:
  - `monitor.py` - Monitor script for supervisor
  - `supervisord.conf` - Sample supervisor configuration
  - `supervisor_helper.py` - Helper utilities for supervisor commands

```bash
# Run the address monitoring example (automatically uses macOS notifications if run on macOS)
python examples/monitor_address.py 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa -i 30 -v
```

### REST API

Start the API server:

```bash
python -m bitcoin_monitor.api
```

API endpoints:

- `GET /` - API info
- `GET /status` - Current monitoring status
- `POST /addresses` - Add an address to monitor
- `DELETE /addresses/{address}` - Remove an address
- `GET /addresses` - List all monitored addresses
- `GET /addresses/{address}` - Get details for a specific address
- `POST /config` - Update monitoring configuration
- `GET /config` - Get current configuration

Example: Add an address to monitor

```bash
curl -X POST "http://localhost:8000/addresses" \
     -H "Content-Type: application/json" \
     -d '{"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"}'
```

## Dependencies

- `bit`: Bitcoin library for Python
- `fastapi`: For REST API
- `uvicorn`: ASGI server for FastAPI
- `pydantic`: Data validation
- `backoff`: For exponential backoff and retries
- `rich`: Terminal UI formatting and display

# Credits

Created by [Adrian Galilea](https://adriangalilea.com)

## TODO

Future improvements planned for this project:

- [ ] Double-check architecture, there may be some overlap or unused code from rapid iteration, maybe between `examples/supervisor/supervisor_helper.py` and `bitcoin-monitor/cli.py`
- [ ] Add webhook notification support
- [ ] Add transaction filtering options (by amount, type, etc.)
