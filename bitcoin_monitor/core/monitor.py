import logging
import time
from typing import Any, Callable, Dict, List, Set

import backoff

# Import the NetworkAPI instead of individual functions
from bit.network import NetworkAPI
from bit.network.rates import currency_to_satoshi_cached

from bitcoin_monitor.core.validation import validate_address

# Module-level logger
log = logging.getLogger(__name__)


class BitcoinAddressMonitor:
    """
    A Bitcoin address monitor that uses the bit library to interact with the Bitcoin blockchain.
    """

    def __init__(self, min_request_interval: int = 10):
        """
        Initialize a Bitcoin address monitor.

        Args:
            min_request_interval: Minimum time between API requests in seconds.
                               Default is 10s to avoid rate limiting.
        """
        self.last_request_time = 0
        self.min_request_interval = min_request_interval
        self._monitored_addresses = {}  # Dictionary to track monitored addresses

    def get_address_info(
        self, address: str, progressive_callback=None
    ) -> Dict[str, Any]:
        """
        Get comprehensive information about a Bitcoin address.

        Args:
            address: The Bitcoin address to query
            progressive_callback: Optional callback to receive progressive updates

        Returns:
            Dictionary containing balance and transaction data

        Raises:
            ValueError: If the address is not a valid Bitcoin address
        """
        # Validate the address first
        if not validate_address(address):
            raise ValueError(f"Invalid Bitcoin address: {address}")

        result = {"address": address}

        try:
            # Respect rate limits
            self._rate_limit()
            log.debug(f"Fetching balance for {address}")

            # Get balance using NetworkAPI
            balance_satoshis = NetworkAPI.get_balance(address)

            # Update balance in result
            result.update(
                {
                    "balance_satoshis": balance_satoshis,
                    "balance_btc": balance_satoshis / 100000000,
                }
            )

            # If we have a progressive callback, let it know we have balance data
            if progressive_callback:
                progressive_callback(result.copy())

            # Get exchange rate for BTC -> USD conversion
            log.debug(f"Fetching exchange rate for {address}")
            btc_to_usd = 1 / (currency_to_satoshi_cached("USD") / 100000000)

            # Update USD value
            result.update(
                {
                    "balance_usd": (balance_satoshis / 100000000) * btc_to_usd
                    if btc_to_usd
                    else 0,
                }
            )

            # If we have a progressive callback, let it know we have USD data
            if progressive_callback:
                progressive_callback(result.copy())

            # Get transactions
            log.debug(f"Fetching transactions for {address}")
            transactions = NetworkAPI.get_transactions(address)

            transaction_count = len(transactions) if transactions else 0
            result.update(
                {
                    "transaction_count": transaction_count,
                    "recent_transactions": transactions[:10]
                    if transactions
                    else [],  # Limit to 10 most recent
                }
            )

            # Final callback with all data
            if progressive_callback:
                progressive_callback(result.copy())

        except Exception as e:
            result["error"] = f"Failed to fetch blockchain data: {str(e)}"

        return result

    def get_addresses_info(self, addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get information about multiple Bitcoin addresses.

        Args:
            addresses: List of Bitcoin addresses to query

        Returns:
            Dictionary mapping each address to its information
        """
        results = {}

        for address in addresses:
            results[address] = self.get_address_info(address)

        return results

    def add_address(self, address: str) -> None:
        """
        Add an address to monitor.

        Args:
            address: Bitcoin address to monitor

        Raises:
            ValueError: If the address is not a valid Bitcoin address
        """
        # Validate the address first
        if not validate_address(address):
            raise ValueError(f"Invalid Bitcoin address: {address}")

        # Get initial balance using NetworkAPI
        balance = NetworkAPI.get_balance(address)
        self._monitored_addresses[address] = balance
        log.debug(f"Address added to monitor: {address}")

    def remove_address(self, address: str) -> None:
        """
        Remove an address from monitoring.

        Args:
            address: Bitcoin address to stop monitoring

        Raises:
            KeyError: If the address is not being monitored
        """
        if address not in self._monitored_addresses:
            raise KeyError(f"Address not being monitored: {address}")

        del self._monitored_addresses[address]
        log.info(f"Removed address from monitoring: {address}")

    def get_address_balance(self, address: str) -> int:
        """
        Get the current balance for an address.

        Args:
            address: Bitcoin address to query

        Returns:
            Balance in satoshis

        Raises:
            KeyError: If the address is not being monitored
        """
        if address not in self._monitored_addresses:
            raise KeyError(f"Address not being monitored: {address}")

        # Fetch fresh balance and update our tracking
        self._rate_limit()
        balance = NetworkAPI.get_balance(address)
        self._monitored_addresses[address] = balance

        return balance

    def check_for_new_transactions(
        self, addresses: List[str], known_tx_hashes: Dict[str, Set[str]]
    ) -> Dict[str, Dict]:
        """
        Check for new transactions on specified addresses.

        Args:
            addresses: List of Bitcoin addresses to check
            known_tx_hashes: Dictionary mapping addresses to sets of known transaction hashes

        Returns:
            Dictionary with results for each address containing new transactions and balance info
        """
        results = {}

        for address in addresses:
            try:
                # Rate limit to avoid API issues
                self._rate_limit()

                # Get current blockchain data using NetworkAPI
                balance_satoshis = NetworkAPI.get_balance(address)
                transactions = NetworkAPI.get_transactions(address)

                # Extract transaction hashes
                current_tx_hashes = set(tx.get("txid") for tx in transactions)

                # Initialize result for this address
                results[address] = {
                    "balance_satoshis": balance_satoshis,
                    "balance_btc": balance_satoshis / 100000000,
                    "current_tx_hashes": current_tx_hashes,
                    "new_transactions": [],
                }

                # Find new transactions if we have known hashes for this address
                if address in known_tx_hashes:
                    new_tx_hashes = current_tx_hashes - known_tx_hashes[address]
                    if new_tx_hashes:
                        # Find the full transaction details for new transactions
                        new_txs = [
                            tx for tx in transactions if tx.get("txid") in new_tx_hashes
                        ]
                        results[address]["new_transactions"] = new_txs

            except Exception as e:
                # Record the error but continue checking other addresses
                results[address] = {
                    "error": f"Error checking address: {str(e)}",
                    "current_tx_hashes": set(),
                }

        return results

    @backoff.on_exception(
        backoff.expo,
        Exception,  # Catch all exceptions
        max_tries=5,
        on_backoff=lambda details: log.debug(
            f"Backing off {details['wait']:0.1f} seconds after {details['tries']} tries"
        ),
    )
    def monitor_addresses(
        self,
        addresses: List[str],
        callback: Callable[[str, List[Dict]], Any],
        interval_seconds: int = 60,
    ) -> None:
        """
        Monitor addresses continuously with a specified interval.

        Args:
            addresses: List of Bitcoin addresses to monitor
            callback: Function to call when new transactions are found.
                    Will be called with (address, new_transactions) arguments.
            interval_seconds: Time to wait between checks in seconds.

        Raises:
            ValueError: If any of the addresses is not a valid Bitcoin address
        """
        # Validate all addresses first
        invalid_addresses = [addr for addr in addresses if not validate_address(addr)]
        if invalid_addresses:
            raise ValueError(
                f"Invalid Bitcoin address(es): {', '.join(invalid_addresses)}"
            )

        known_tx_hashes = {}
        for address in addresses:
            if address not in self._monitored_addresses:
                balance = NetworkAPI.get_balance(address)
                self._monitored_addresses[address] = balance
                log.debug(f"Added address to monitor: {address}")

        log.info(f"Monitoring {len(addresses)} Bitcoin address(es)")

        for address in addresses:
            try:
                self._rate_limit()

                transactions = NetworkAPI.get_transactions(address)
                known_tx_hashes[address] = set(
                    tx.get("txid") for tx in transactions[:10]
                )

                log.debug(
                    f"Initialized {address} with {len(known_tx_hashes[address])} transactions"
                )
            except Exception as e:
                log.error(f"Failed to initialize {address}: {str(e)}")
                print(f"Failed to initialize {address}: {str(e)}")

        log.info(f"Starting monitoring loop, checking every {interval_seconds} seconds")

        while True:
            # Process one address at a time to better handle rate limits
            for address in addresses:
                if address not in known_tx_hashes:
                    known_tx_hashes[address] = set()

                try:
                    # Rate limit to avoid API issues
                    self._rate_limit()

                    # Check for new transactions for this address
                    log.debug(f"Checking address: {address}")

                    # Get current blockchain data using NetworkAPI
                    transactions = NetworkAPI.get_transactions(address)
                    current_tx_hashes = set(tx.get("txid") for tx in transactions)

                    # Find new transactions
                    new_tx_hashes = current_tx_hashes - known_tx_hashes[address]
                    if new_tx_hashes:
                        # Find the full transaction details for new transactions
                        new_txs = [
                            tx for tx in transactions if tx.get("txid") in new_tx_hashes
                        ]
                        log.info(f"Found {len(new_txs)} new transactions for {address}")
                        callback(address, new_txs)

                    # Update known transaction hashes
                    known_tx_hashes[address] = current_tx_hashes

                except Exception as e:
                    log.warning(f"Error checking {address}: {str(e)}")
                    print(f"Error checking {address}: {str(e)}")

            log.debug(f"Completed check cycle. Sleeping for {interval_seconds} seconds")
            if len(addresses) < 5:
                addr_str = ", ".join(addresses)
            else:
                addr_str = f"{len(addresses)} addresses"
            log.info(f"Monitor heartbeat: Watching {addr_str}")
            time.sleep(interval_seconds)

    def monitor_continuously(
        self, callback: Callable[[str, List[Dict]], Any], interval_seconds: int = 60
    ) -> None:
        """
        Monitor all tracked addresses continuously.

        Args:
            callback: Function to call when new transactions are found
            interval_seconds: Time between checks in seconds
        """
        addresses = list(self._monitored_addresses.keys())
        self.monitor_addresses(addresses, callback, interval_seconds)

    def _rate_limit(self) -> None:
        """
        Apply rate limiting to respect API limits.
        """
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            log.debug(f"Rate limiting: sleeping {sleep_time:.2f}s before next request")
            time.sleep(sleep_time)

        # Update last request time after the sleep
        self.last_request_time = time.time()

        # Add a small additional delay for safety with external APIs
        time.sleep(0.5)
