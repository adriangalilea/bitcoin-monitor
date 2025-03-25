"""
Bitcoin address validation utilities.
"""
import re
from hashlib import sha256
from typing import Optional, Tuple

# Regular expressions for different address formats
REGEX_LEGACY = r"^[1][a-km-zA-HJ-NP-Z1-9]{25,34}$"  # Legacy addresses (P2PKH)
REGEX_SEGWIT = r"^[3][a-km-zA-HJ-NP-Z1-9]{25,34}$"  # SegWit addresses (P2SH)
REGEX_BECH32 = r"^(bc1)[a-zA-HJ-NP-Z0-9]{25,90}$"  # Native SegWit (Bech32)

# Base58 character set
DIGITS58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def decode_base58(address: str, length: int) -> bytes:
    """
    Decode a Base58 encoded address to bytes.

    Args:
        address: The Base58 encoded address
        length: The expected length of the decoded bytes

    Returns:
        The decoded bytes
    """
    n = 0
    for char in address:
        n = n * 58 + DIGITS58.index(char)
    return n.to_bytes(length, "big")


def is_valid_address(address: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a Bitcoin address.

    Args:
        address: The Bitcoin address to validate

    Returns:
        Tuple of (is_valid, address_type)
        where address_type is one of: "legacy", "segwit", "bech32", or None if invalid
    """
    # Check for empty or None addresses
    if not address:
        return False, None

    # Check for legacy address format (P2PKH, starts with 1)
    if re.match(REGEX_LEGACY, address):
        try:
            # Decode and verify checksum
            decoded = decode_base58(address, 25)
            if decoded[-4:] == sha256(sha256(decoded[:-4]).digest()).digest()[:4]:
                return True, "legacy"
        except Exception:
            pass

    # Check for SegWit address format (P2SH, starts with 3)
    elif re.match(REGEX_SEGWIT, address):
        try:
            # Decode and verify checksum
            decoded = decode_base58(address, 25)
            if decoded[-4:] == sha256(sha256(decoded[:-4]).digest()).digest()[:4]:
                return True, "segwit"
        except Exception:
            pass

    # Check for Bech32 address format (starts with bc1)
    elif re.match(REGEX_BECH32, address):
        # Basic format validation for now
        # Proper Bech32 validation would require more extensive checks
        return True, "bech32"

    # No valid format matched
    return False, None


def validate_address(address: str) -> bool:
    """
    Validates if a string is a valid Bitcoin address.

    Args:
        address: The Bitcoin address to validate

    Returns:
        True if valid, False otherwise
    """
    is_valid, _ = is_valid_address(address)
    return is_valid
