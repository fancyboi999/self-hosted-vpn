# Self-Hosted VPN Skill

**One static exit. One shared rule source. Verifiable end to end.**

An Agent Skill for building, auditing, and maintaining a domainless single-tenant overseas proxy stack on Debian 12+ (`sing-box` `VLESS + Reality` on `TCP 443` and standalone `Hysteria2` on `UDP 443`), paired with Let's Encrypt `shortlived` IP-certificate HTTPS subscriptions and slot-decoupled desktop/mobile routing profiles.

[中文说明](README.zh-CN.md) · [Skill](skills/self-hosted-vpn/SKILL.md)

## Install

```sh
npx skills add fancyboi999/self-hosted-vpn --skill self-hosted-vpn
```

For manual installation, copy `skills/self-hosted-vpn/` into your coding agent's skills directory (`~/.agents/skills/self-hosted-vpn/` or `~/.claude/skills/self-hosted-vpn/`). The skill sets `disable-model-invocation: true` so agents run it only when you explicitly invoke it.

## Architecture

- **Dual-protocol core (`TCP 443` + `UDP 443`)**: `sing-box` `VLESS + Reality` (`xtls-rprx-vision`, `uTLS` `chrome` fingerprint, separate desktop and mobile UUIDs) handles daily reliable sessions; standalone `Hysteria2` (`16 MiB` socket buffers, `fq + bbr`, SHA-256 certificate pinning) handles lossy links when UDP is healthy.
- **Domainless HTTPS subscriptions (`TCP 80` + `TCP 8443`)**: Certbot `>= 5.x` issues a Let's Encrypt `shortlived` certificate directly for `<SERVER_IP>` (`IP Address` SAN), served by Nginx behind high-entropy token paths with a 6-hour renewal timer and NIC traffic headers.
- **Slot-decoupled routing**: Every rule targets an abstract slot (`FIXED-EXIT` manual `select` group in Mihomo, `PROXY` in Shadowrocket) rather than a server name. A single pre-compiled ~9,200-rule template (`fake-ip` + split DoH + `no-resolve` CIDRs) renders desktop `clash.yaml` and converts via `scripts/render_shadowrocket_conf.py` into a node-free mobile remote config (`shadowrocket.conf`). Adding or rotating a VPS adds a node subscription only, without touching routing rules.
- **Host control-plane safety**: Verification runs inside an isolated client process or separate remote host without restarting or mutating the workstation's active proxy client, TUN interface, or system DNS.

## Repository layout

- [`skills/self-hosted-vpn/SKILL.md`](skills/self-hosted-vpn/SKILL.md) — workflow, safety rules, and verification gates
- [`skills/self-hosted-vpn/scripts/render_shadowrocket_conf.py`](skills/self-hosted-vpn/scripts/render_shadowrocket_conf.py) — converts the shared Mihomo template + optional local overlay into a node-free Shadowrocket rules config
- [`skills/self-hosted-vpn/references/server-configs.md`](skills/self-hosted-vpn/references/server-configs.md) — `sysctl`, `sing-box` `VLESS + Reality`, and standalone `Hysteria2` units
- [`skills/self-hosted-vpn/references/https-subscription.md`](skills/self-hosted-vpn/references/https-subscription.md) — Let's Encrypt IP certificate, Nginx `:8443`, renewal timer, and `Subscription-Userinfo` daemon
- [`skills/self-hosted-vpn/references/client-profiles.md`](skills/self-hosted-vpn/references/client-profiles.md) — `clash.yaml` rendering, local intranet overlays, Shadowrocket subscriptions, and QR generation
- [`skills/self-hosted-vpn/references/clash-subscription-template.yaml`](skills/self-hosted-vpn/references/clash-subscription-template.yaml) — zero-dependency pre-compiled Mihomo template
- [`skills/self-hosted-vpn/references/shadowrocket-mobile-rules.conf`](skills/self-hosted-vpn/references/shadowrocket-mobile-rules.conf) — mobile-specific telemetry ingestion `REJECT`, AI/checkout/STUN slot rules
- [`skills/self-hosted-vpn/references/tuning-and-diagnostics.md`](skills/self-hosted-vpn/references/tuning-and-diagnostics.md) — E2E benchmark gates, evidence-backed kernel ledger, and troubleshooting playbooks

## License

[MIT](LICENSE)
