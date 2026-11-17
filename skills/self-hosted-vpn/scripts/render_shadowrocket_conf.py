#!/usr/bin/env python3
"""Render the machine-neutral Shadowrocket rules config from the Mihomo template.

The Mihomo template is the single source of shared rules. Every rule that targets
the slot group is rewritten to Shadowrocket's built-in PROXY policy, so the output
names no node, IP, or credential and serves every exit machine. Rule order is:
IPv6 reject, local overlay, mobile-only rules, template rules; the first rule for
a given matcher wins and later duplicates are dropped.
"""

import argparse
import re
import sys
from pathlib import Path

SLOT = "FIXED-EXIT"
LIST_KEYS = {"always-real-ip", "skip-proxy", "tun-excluded-routes"}

GENERAL = {
    "ipv6": "false",
    "prefer-ipv6": "false",
    "bypass-system": "true",
    "skip-proxy": "192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 127.0.0.1, localhost, *.local, captive.apple.com",
    "tun-excluded-routes": "10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.168.0.0/16, 224.0.0.0/4, 255.255.255.255/32",
    "dns-server": "https://dns.alidns.com/dns-query, https://doh.pub/dns-query",
    "fallback-dns-server": "https://cloudflare-dns.com/dns-query, https://dns.google/dns-query",
    "dns-direct-system": "false",
    "dns-fallback-system": "false",
    "hijack-dns": "*:53",
    "always-real-ip": "*.lan, *.local, *.arpa, time.*.com, time.*.gov, time.*.apple.com, ntp.*.com, *.msftconnecttest.com, *.msftncsi.com, localhost.ptlogin2.qq.com, *.weixin.qq.com, *.qpic.cn, *.gtimg.cn, *.gtimg.com",
    "proxy-test-url": "http://www.gstatic.com/generate_204",
    "test-timeout": "5",
    "udp-policy-not-supported-behaviour": "REJECT",
}
# Native carrier IPv6 on cellular bypasses the proxy tunnel; reject it ahead of every other rule.
LEADING_RULES = ["IP-CIDR6,::/0,REJECT,no-resolve"]


def template_rules(text: str) -> list[str]:
    body = text.split("\nrules:", 1)[1]
    rules = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        parts = line[2:].strip().strip("\"'").split(",")
        if parts[0].startswith("PROCESS-"):
            continue  # iOS cannot route by process
        if parts[:2] == ["DOMAIN-KEYWORD", "."]:
            continue  # Mihomo catch-all for domains; FINAL already covers it here
        if parts[0] == "MATCH":
            parts[0] = "FINAL"
        target = -2 if parts[-1] == "no-resolve" else -1
        if parts[target] == SLOT:
            parts[target] = "PROXY"
        rules.append(",".join(parts))
    return rules


def fragment_rules(text: str) -> list[str]:
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def first_wins(rules: list[str]) -> list[str]:
    seen: set[tuple[str, str]] = set()
    kept = []
    for rule in rules:
        parts = rule.split(",")
        matcher = (parts[0], parts[1] if len(parts) > 2 else "")
        if matcher not in seen:
            seen.add(matcher)
            kept.append(rule)
    return kept


def parse_overlay(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        header = re.fullmatch(r"\[(.+)\]", line)
        if header:
            current = sections.setdefault(header.group(1), [])
        elif current is None:
            sys.exit(f"overlay line outside a section: {line}")
        else:
            current.append(line)
    unknown = set(sections) - {"General", "Host", "Rule"}
    if unknown:
        sys.exit(f"overlay sections not supported: {sorted(unknown)}")
    return sections


def main() -> None:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--template",
        type=Path,
        default=here.parent / "references" / "clash-subscription-template.yaml",
    )
    ap.add_argument(
        "--mobile-rules",
        type=Path,
        default=here.parent / "references" / "shadowrocket-mobile-rules.conf",
    )
    ap.add_argument(
        "--update-url", required=True, help="HTTPS URL this config is published at"
    )
    ap.add_argument(
        "--overlay",
        type=Path,
        help="local fragment with [General] / [Host] / [Rule] additions",
    )
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()

    overlay = parse_overlay(args.overlay.read_text()) if args.overlay else {}
    general = {"update-url": args.update_url, **GENERAL}
    for line in overlay.get("General", []):
        key, _, value = (p.strip() for p in line.partition("="))
        general[key] = (
            f"{general[key]}, {value}" if key in LIST_KEYS and key in general else value
        )

    rules = first_wins(
        LEADING_RULES
        + overlay.get("Rule", [])
        + fragment_rules(args.mobile_rules.read_text())
        + template_rules(args.template.read_text())
    )
    if rules[-1] != "FINAL,PROXY":
        sys.exit(f"last rule must be FINAL,PROXY, got {rules[-1]}")
    leaked = [r for r in rules if SLOT in r]
    if leaked:
        sys.exit(f"slot name left in output: {leaked[:3]}")

    out = ["[General]", *(f"{k} = {v}" for k, v in general.items()), ""]
    if overlay.get("Host"):
        out += ["[Host]", *overlay["Host"], ""]
    out += ["[Rule]", *rules, ""]
    args.output.write_text("\n".join(out))
    print(f"{args.output}: {len(rules)} rules", file=sys.stderr)


if __name__ == "__main__":
    main()
