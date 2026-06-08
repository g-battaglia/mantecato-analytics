"""Datacenter / cloud IP reputation — local lookup, no external calls.

Bots and scrapers overwhelmingly originate from cloud/datacenter networks rather
than residential ISPs. Checking the (transient, never-stored) client IP against a
**bundled** list of well-known datacenter CIDR blocks lets the tracker flag those
requests as bots without contacting any third-party service — the IP is used only
for this in-memory membership test and is never persisted.

The seed list is curated and intentionally **non-exhaustive**: full provider
ranges are large and change often. Operators can extend or override it without
touching code via ``settings.DATACENTER_CIDRS`` (a list of CIDR strings), e.g.
populated from the published AWS ``ip-ranges.json`` / GCP / Azure range files.
"""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Curated starter set of major cloud/datacenter IPv4 CIDR blocks. NOT exhaustive
# — see the module docstring for extending via ``settings.DATACENTER_CIDRS``.
_SEED_CIDRS: tuple[str, ...] = (
    # Amazon Web Services
    "3.0.0.0/9", "3.128.0.0/9", "13.32.0.0/15", "15.177.0.0/16",
    "18.32.0.0/11", "34.192.0.0/10", "35.71.64.0/18",
    "52.0.0.0/10", "52.64.0.0/12", "54.64.0.0/11", "54.144.0.0/12", "54.224.0.0/11",
    # Google Cloud / Google
    "34.64.0.0/10", "35.184.0.0/13", "35.192.0.0/14", "104.196.0.0/14",
    "130.211.0.0/16", "146.148.0.0/17",
    # Microsoft Azure
    "13.64.0.0/11", "20.0.0.0/8", "40.64.0.0/10", "52.224.0.0/11",
    "104.40.0.0/13", "137.116.0.0/15", "168.61.0.0/16",
    # DigitalOcean
    "104.131.0.0/16", "138.197.0.0/16", "159.65.0.0/16", "159.89.0.0/16",
    "165.227.0.0/16", "167.71.0.0/16", "167.99.0.0/16", "188.166.0.0/16",
    # Hetzner
    "5.9.0.0/16", "88.198.0.0/16", "94.130.0.0/16", "116.202.0.0/16",
    "135.181.0.0/16", "138.201.0.0/16", "144.76.0.0/16", "159.69.0.0/16",
    # OVH
    "51.38.0.0/16", "51.68.0.0/16", "51.75.0.0/16", "51.83.0.0/16",
    "54.36.0.0/16", "91.121.0.0/16", "137.74.0.0/16", "147.135.0.0/16",
    # Linode / Akamai
    "45.33.0.0/16", "45.56.0.0/16", "139.162.0.0/16", "172.104.0.0/15",
    "173.255.192.0/18", "192.155.80.0/20",
    # Oracle Cloud
    "129.146.0.0/16", "132.145.0.0/16", "150.136.0.0/16",
    # Scaleway / Online SAS
    "51.15.0.0/16", "51.158.0.0/16", "163.172.0.0/16", "212.47.224.0/19",
)

_networks_v4: list[ipaddress.IPv4Network] = []
_loaded = False


def _build() -> None:
    """Parse the seed + operator CIDRs into collapsed IPv4 networks (once)."""
    global _loaded
    extra = list(getattr(settings, "DATACENTER_CIDRS", []) or [])
    nets: list[ipaddress.IPv4Network] = []
    for cidr in (*_SEED_CIDRS, *extra):
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            logger.warning("Ignoring invalid datacenter CIDR: %r", cidr)
            continue
        if isinstance(net, ipaddress.IPv4Network):
            nets.append(net)
    _networks_v4.clear()
    _networks_v4.extend(ipaddress.collapse_addresses(nets))
    _loaded = True


def reload_ranges() -> None:
    """Force a rebuild of the network list (e.g. after changing settings/tests)."""
    _build()


def is_datacenter_ip(ip: str | None) -> bool:
    """Return ``True`` when *ip* falls inside a known datacenter/cloud CIDR block.

    Only IPv4 is checked (cloud bot traffic is overwhelmingly IPv4). Missing or
    invalid IPs and IPv6 addresses return ``False``. The IP is never stored.
    """
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if not isinstance(addr, ipaddress.IPv4Address):
        return False
    if not _loaded:
        _build()
    return any(addr in net for net in _networks_v4)
