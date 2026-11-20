"""URL Validation and SSRF (Server-Side Request Forgery) Protection Module."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse
from typing import Tuple, List

logger = logging.getLogger("sitepulse.validators")


class SSRFProtectionError(ValueError):
    """Raised when a URL targets a private, loopback, or disallowed internal network destination."""
    pass


class InvalidURLError(ValueError):
    """Raised when a URL is malformed or uses an unsupported scheme."""
    pass


class DNSResolutionError(ValueError):
    """Raised when hostname DNS resolution fails or times out."""
    pass


# Explicitly forbidden hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "169.254.169.254",
    "instance-data",
}

# Forbidden domain suffix patterns
BLOCKED_DOMAINS_SUFFIXES = (
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".corp",
)


def is_ip_allowed(ip_str: str) -> Tuple[bool, str]:
    """
    Check if an IP address is a safe public IP and not a private, loopback,
    link-local, cloud metadata, or reserved address.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"Invalid IP address format: {ip_str}"

    if ip.is_loopback:
        return False, f"Loopback address '{ip_str}' is forbidden."
    if ip.is_private:
        return False, f"Private network address '{ip_str}' is forbidden."
    if ip.is_link_local:
        return False, f"Link-local / cloud metadata address '{ip_str}' is forbidden."
    if ip.is_reserved:
        return False, f"Reserved network address '{ip_str}' is forbidden."
    if ip.is_multicast:
        return False, f"Multicast address '{ip_str}' is forbidden."
    if ip.is_unspecified:
        return False, f"Unspecified address '{ip_str}' is forbidden."

    # Specific check for IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ipv4 = ip.ipv4_mapped
        if ipv4.is_loopback or ipv4.is_private or ipv4.is_link_local:
            return False, f"IPv4-mapped private address '{ip_str}' is forbidden."

    # Cloud metadata check (169.254.169.254, 100.100.100.200)
    if str(ip) in ("169.254.169.254", "100.100.100.200"):
        return False, f"Cloud metadata destination '{ip_str}' is forbidden."

    return True, ""


def resolve_and_verify_dns(hostname: str, port: int = 443) -> List[str]:
    """
    Resolve hostname to IP addresses and ensure none of them resolve to
    private, loopback, or internal networks.
    """
    logger.info(f"[STAGE: DNS_VALIDATION] Resolving DNS for hostname '{hostname}:{port}'")
    try:
        addr_info = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as e:
        logger.error(f"[EXTRACTION_FAILED at STAGE: DNS_VALIDATION] socket.gaierror for '{hostname}': {str(e)}")
        raise DNSResolutionError(f"DNS resolution failed for hostname '{hostname}': {str(e)}") from e
    except Exception as e:
        logger.error(f"[EXTRACTION_FAILED at STAGE: DNS_VALIDATION] DNS error for '{hostname}': {str(e)}")
        raise DNSResolutionError(f"Unexpected error resolving hostname '{hostname}': {str(e)}") from e

    if not addr_info:
        logger.error(f"[EXTRACTION_FAILED at STAGE: DNS_VALIDATION] No records found for '{hostname}'")
        raise DNSResolutionError(f"No DNS records found for hostname '{hostname}'.")

    resolved_ips: List[str] = []
    for entry in addr_info:
        sockaddr = entry[4]
        ip = sockaddr[0]
        resolved_ips.append(ip)

        allowed, reason = is_ip_allowed(ip)
        if not allowed:
            logger.warning(f"[EXTRACTION_FAILED at STAGE: DNS_VALIDATION] Disallowed IP destination for '{hostname}': {ip} - {reason}")
            raise SSRFProtectionError(
                f"Security violation: Hostname '{hostname}' resolves to disallowed IP '{ip}'. {reason}"
            )

    logger.info(f"[STAGE: DNS_VALIDATION] Successfully verified {len(resolved_ips)} IP addresses for '{hostname}'")
    return resolved_ips


def validate_url_security(url: str) -> str:
    """
    Comprehensive validation against SSRF, unsupported schemes, and malformed URLs.
    
    Returns the cleaned URL if safe, or raises InvalidURLError or SSRFProtectionError.
    """
    if not url or not isinstance(url, str):
        raise InvalidURLError("A valid website URL must be provided.")

    cleaned_url = url.strip()
    if not cleaned_url:
        raise InvalidURLError("URL cannot be empty.")

    logger.info(f"[STAGE: URL_VALIDATION] Validating scheme, credentials, and hostname for '{cleaned_url}'")

    # Parse URL
    try:
        parsed = urlparse(cleaned_url)
    except Exception as e:
        raise InvalidURLError(f"Malformed URL: {str(e)}") from e

    # Check scheme
    if parsed.scheme.lower() not in ("http", "https"):
        raise InvalidURLError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are allowed."
        )

    # Disallow userinfo (e.g. http://admin:pass@example.com)
    if parsed.username or parsed.password:
        raise SSRFProtectionError("URLs containing user credentials are not permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError("URL must contain a valid hostname.")

    hostname_lower = hostname.lower()

    # Disallow known localhost/metadata hostnames
    if hostname_lower in BLOCKED_HOSTNAMES:
        raise SSRFProtectionError(f"Targeting '{hostname}' is not permitted.")

    # Check blocked domain suffixes (.local, .internal, etc.)
    if any(hostname_lower.endswith(suffix) for suffix in BLOCKED_DOMAINS_SUFFIXES):
        raise SSRFProtectionError(f"Internal domain name '{hostname}' is not permitted.")

    # Check if hostname is an IP literal
    try:
        ip = ipaddress.ip_address(hostname_lower.strip("[]"))
        allowed, reason = is_ip_allowed(str(ip))
        if not allowed:
            raise SSRFProtectionError(f"Direct IP target '{hostname}' is forbidden. {reason}")
    except ValueError:
        # Not a raw IP literal; resolve via DNS
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        resolve_and_verify_dns(hostname_lower, port)

    return cleaned_url
