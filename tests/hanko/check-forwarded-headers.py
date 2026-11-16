#!/usr/bin/env python3
"""Check the temporary development ingress probe without printing IP addresses.

Apply forwarded-headers-probe.yaml, wait for its Pod and HTTPRoute to become
ready, run this script, and delete the manifest immediately afterward.
"""

import ipaddress
import sys
import urllib.error
import urllib.request

HOST = "https://identity-dev.pocket-doc.app"
PATH = "/__hanko-forwarded-headers-probe"
FORGED = "203.0.113.123"
POD_NETWORK = ipaddress.ip_network("10.42.0.0/16")


def get(path, headers=None):
    request = urllib.request.Request(
        HOST + path,
        headers={"User-Agent": "Mozilla/5.0 Hanko-header-check", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(4096).decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, ""


def probe(headers=None):
    status, body = get(PATH, headers)
    if status != 200 or "|" not in body:
        return status, None, None
    actual, forwarded = body.split("|", 1)
    try:
        client = ipaddress.ip_address(actual.strip())
        chain = [ipaddress.ip_address(item.strip()) for item in forwarded.split(",")]
    except ValueError:
        return status, None, None
    return status, client, chain


def hanko_xff_candidate(chain):
    # Hanko 3.1 uses Echo's XFF extractor. Its default trusted ranges include
    # loopback, link-local and private addresses, plus the configured PodCIDR.
    for address in reversed(chain):
        trusted = address in POD_NETWORK or address.is_loopback or address.is_link_local
        if isinstance(address, ipaddress.IPv4Address):
            trusted |= any(address in ipaddress.ip_network(cidr) for cidr in (
                "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"
            ))
        else:
            trusted |= address in ipaddress.ip_network("fc00::/7")
        if not trusted:
            return address
    return chain[0] if chain else None


def check(condition, description):
    print(("PASS: " if condition else "FAIL: ") + description)
    return condition


def main():
    try:
        status, trace = get("/cdn-cgi/trace")
        trace_values = dict(line.split("=", 1) for line in trace.splitlines() if "=" in line)
        trace_ip = ipaddress.ip_address(trace_values["ip"])
        status_baseline, baseline, chain = probe()
        if not check(status == 200 and status_baseline == 200 and baseline == trace_ip,
                     "baseline Cloudflare client IP matches Cloudflare trace"):
            return 1
        results = [check(hanko_xff_candidate(chain) == baseline,
                         "baseline forwarded chain resolves to the Cloudflare client IP")]
        for description, headers in (
            ("forged X-Forwarded-For", {"X-Forwarded-For": FORGED}),
            ("forged CF-Connecting-IP", {"CF-Connecting-IP": FORGED}),
            ("both forged headers", {"X-Forwarded-For": FORGED, "CF-Connecting-IP": FORGED}),
        ):
            response_status, observed, observed_chain = probe(headers)
            if response_status == 403:
                results.append(check(True, description + " rejected at the edge"))
            else:
                results.append(check(response_status == 200 and observed == baseline and
                                     hanko_xff_candidate(observed_chain) == baseline,
                                     description + " did not change the resolved client"))
        return 0 if all(results) else 1
    except (KeyError, OSError, ValueError, TypeError):
        print("FAIL: probe unavailable or returned an invalid response")
        return 1


if __name__ == "__main__":
    sys.exit(main())
