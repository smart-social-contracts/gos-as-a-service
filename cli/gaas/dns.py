"""DNS record rendering and propagation polling for IC custom domains."""

from __future__ import annotations

import time
from dataclasses import dataclass

import dns.exception
import dns.resolver

ICP_GATEWAY = "icp1.io"


@dataclass(frozen=True)
class DnsRecord:
    record_type: str
    host: str
    value: str
    notes: str = ""


def render_dns_records(domain: str, frontend_canister_id: str) -> list[DnsRecord]:
    """Render the exact DNS records required for an IC custom domain."""
    domain = domain.rstrip(".").lower()
    acme_target = f"_acme-challenge.{domain}.{ICP_GATEWAY}"

    return [
        DnsRecord(
            record_type="CNAME/ALIAS",
            host=domain,
            value=ICP_GATEWAY,
            notes="apex/subdomain host → IC gateway",
        ),
        DnsRecord(
            record_type="TXT",
            host=f"_canister-id.{domain}",
            value=frontend_canister_id,
            notes="canister ownership proof",
        ),
        DnsRecord(
            record_type="CNAME",
            host=f"_acme-challenge.{domain}",
            value=acme_target,
            notes="ACME certificate challenge delegation",
        ),
    ]


def _resolve_txt(name: str) -> set[str]:
    try:
        answers = dns.resolver.resolve(name, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout):
        return set()
    values: set[str] = set()
    for rdata in answers:
        if hasattr(rdata, "strings"):
            values.add("".join(part.decode("utf-8", errors="replace") for part in rdata.strings))
        else:
            values.add(str(rdata).strip('"'))
    return values


def _resolve_cname(name: str) -> str | None:
    try:
        answers = dns.resolver.resolve(name, "CNAME")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout):
        return None
    for rdata in answers:
        return str(rdata.target).rstrip(".").lower()
    return None


def dns_records_ready(domain: str, canister_id: str) -> tuple[bool, list[str]]:
    """Return whether required DNS records appear to be propagated."""
    domain = domain.rstrip(".").lower()
    expected = render_dns_records(domain, canister_id)
    issues: list[str] = []

    canister_host = f"_canister-id.{domain}"
    txt_values = _resolve_txt(canister_host)
    if canister_id not in txt_values and not any(canister_id in value for value in txt_values):
        issues.append(f"TXT {canister_host} does not contain {canister_id}")

    acme_host = f"_acme-challenge.{domain}"
    acme_expected = f"_acme-challenge.{domain}.{ICP_GATEWAY}"
    acme_value = _resolve_cname(acme_host)
    if acme_value != acme_expected:
        issues.append(
            f"CNAME {acme_host} expected {acme_expected}, got {acme_value or 'missing'}"
        )

    host_cname = _resolve_cname(domain)
    if host_cname != ICP_GATEWAY:
        issues.append(
            f"CNAME/ALIAS {domain} expected {ICP_GATEWAY}, got {host_cname or 'missing'}"
        )

    return len(issues) == 0, issues


def wait_for_dns(
    domain: str,
    canister_id: str,
    timeout: float = 300.0,
    poll_interval: float = 10.0,
) -> bool:
    """Poll until DNS records propagate or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _issues = dns_records_ready(domain, canister_id)
        if ready:
            return True
        time.sleep(poll_interval)
    return False
