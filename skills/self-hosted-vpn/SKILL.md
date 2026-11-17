---
name: self-hosted-vpn
description: 在海外 Linux VPS 上部署、配置无域名 HTTPS 订阅或排查自建 VPN 节点（VLESS Reality + Hysteria2）。
disable-model-invocation: true
---

# Self-Hosted VPN

Build and maintain a domainless, single-tenant overseas proxy exit modeled on a production Debian 12 VPS stack. Route quality and IP reputation govern ~80% of real-world experience; protocol choice and kernel parameters govern the remaining ~20%.

## Architecture Baseline

- **Domainless dual-protocol core** on Debian 12+ with a static IPv4:
  - **`TCP 443` (`sing-box` `VLESS + Reality`)**: `xtls-rprx-vision`, region-proximate `<REALITY_SNI>` (a reputable TLS 1.3 + H2 domain proximate to the VPS), `uTLS` `chrome` client fingerprint, and separate UUIDs per device (`desktop`, `mobile`). Serves as the daily reliable channel resilient to ISP UDP throttling and NAT state drops.
  - **`UDP 443` (standalone `Hysteria2`)**: Runs as unprivileged user `hysteria` (`CAP_NET_BIND_SERVICE`), `bbr` congestion, masquerade proxy, and a self-signed certificate pinned by SHA-256 digest (`fingerprint` in Mihomo, `pinSHA256` in URI). Serves as the high-throughput QUIC channel when the local UDP path is healthy.
- **Domainless trusted HTTPS subscription** (`TCP 80` + `TCP 8443`): Certbot `>= 5.x` issues a Let's Encrypt `shortlived` IP certificate via `http-01` webroot on `:80`; Nginx on `:8443` exposes only exact-match high-entropy token paths, backed by a 6-hour renewal timer and a `boot_id`-aware NIC traffic daemon (`Subscription-Userinfo`).
- **Rules target a slot, nodes fill it**: Every rule names a **slot** (the manual `select` group `FIXED-EXIT` in Mihomo, the built-in `PROXY` policy in Shadowrocket), so one rule set serves every exit machine and a new machine adds nodes only. Each machine publishes its own nodes (`clash.yaml` for desktop, `shadowrocket.txt` for mobile); one designated machine also publishes the node-free mobile rules config (`shadowrocket.conf`). The user fills the slot by hand rather than through `url-test` or `load-balance`, keeping web OAuth and CLI API traffic on one static IP. AI domains and DNS fallback resolve via proxied DoH through `FIXED-EXIT`; private CIDRs, domestic domains/CDNs, and bulk game downloads (`Steam` / `Epic`) bypass via `DIRECT`, and ad/tracker hosts hit `REJECT`.

## Host & Credential Safety

- **Isolated verification**: Execute all proxy handshakes, subscription fetches, and throughput benchmarks from a separate remote Linux host or an isolated local `mihomo`/`sing-box` process (`TUN` disabled, independent port, `*_PROXY` env vars cleared). Leave the workstation's running Clash client, TUN interface, system proxy, and DNS untouched.
- **Client delivery**: Output generated `.yaml` profiles, subscription URLs, and QR codes to local `0600` files for manual import. Only register a profile into a local client when explicitly instructed in the current turn, without switching active profiles or restarting the proxy core.
- **Credential hygiene**: Generate fresh UUIDs, X25519 Reality keypairs, Hysteria2 passwords, and `>= 192-bit` URL-safe `<SUB_TOKEN>` paths per deployment. Keep private keys on the server (`0600`) and redact secrets, UUIDs, and token URLs from logs, commits, and chat responses.

## Build & Verification Sequence

Run only the phases matching the task; verify each phase's completion criterion before advancing.

1. **Preflight & Kernel Baseline**
   Verify monthly billing (avoid untested annual lock-in), static IPv4, key-only SSH, and cloud security group + OS firewall parity (`TCP 22, 443` + `UDP 443`; add `TCP 80, 8443` when deploying HTTPS subscriptions). Persist `fq + bbr` and `16 MiB` UDP buffer caps (`16777216`) from [`references/server-configs.md`](references/server-configs.md).
   - *Done when*: `sysctl net.ipv4.tcp_congestion_control net.core.default_qdisc net.core.rmem_max net.core.wmem_max` matches `/etc/sysctl.d/`, and external probes confirm cloud firewall rules match intended ports.

2. **Dual-Protocol Proxy Core (`TCP 443` + `UDP 443`)**
   Install official `sing-box` and standalone `hysteria` packages/binaries, apply configs from [`references/server-configs.md`](references/server-configs.md), and restart `hysteria-server` after `sysctl` changes so sockets allocate the `16 MiB` buffers.
   - *Done when*: `sing-box` and `hysteria-server` are `active`, `ss -tulnp` shows `TCP :443` (`sing-box`) and `UDP :443` (`hysteria`), `ss -uam` confirms `rb`/`tb = 16777216` on `:443`, and an isolated client completes real requests over **both** protocols—returning `<SERVER_IP>` as exit IP and expected HTTP statuses on target overseas/AI endpoints.

3. **Domainless HTTPS Subscription (`TCP 80` + `TCP 8443`)**
   Provision the Let's Encrypt `shortlived` IP certificate, Nginx `:80/:8443` gateway, `vpn-subscription-usage` loopback service, and 6-hour renewal + TLS IP-verification timer from [`references/https-subscription.md`](references/https-subscription.md), serving profiles rendered from [`references/client-profiles.md`](references/client-profiles.md).
   - *Done when*: `openssl s_client -connect <SERVER_IP>:8443 -verify_ip <SERVER_IP> -verify_return_error` passes with `>= 48h` validity remaining, external HTTPS `GET` returns `200` with `Subscription-Userinfo` on every published token path and `404` on `/`, `mihomo -t` validates the fetched `clash.yaml`, the fetched `shadowrocket.conf` contains no `[Proxy]` section or node name, and a manual run of `vpn-subscription-renew.service` succeeds without restarting `:443` proxy services.

4. **Benchmarking & Diagnostics**
   Measure isolated 25 MB HTTP transfers and kernel socket counters (`RcvbufErrors`, TCP retransmits, RTT) per [`references/tuning-and-diagnostics.md`](references/tuning-and-diagnostics.md) before and after any tuning change; revert changes lacking repeatable gains.
   - *Done when*: every retained change has paired before/after evidence and an executable rollback script on the server, and unverified conditions (peak-hour ISP congestion, mobile carrier UDP, local client import) are explicitly reported.

## References

- [`references/server-configs.md`](references/server-configs.md) — Read when configuring or auditing `sysctl`, `sing-box` `VLESS + Reality`, standalone `Hysteria2`, self-signed cert SHA-256 pinning, or non-root `systemd` units.
- [`references/https-subscription.md`](references/https-subscription.md) — Read when deploying or troubleshooting Let's Encrypt `shortlived` IP certificates, Nginx `:80/:8443`, 6-hour renewal checks, or `Subscription-Userinfo` NIC traffic accounting.
- [`references/client-profiles.md`](references/client-profiles.md) — Read when rendering `clash.yaml` from [`references/clash-subscription-template.yaml`](references/clash-subscription-template.yaml), merging a local overlay of machine-private rules, or producing the mobile node subscription, rules config, and their QR codes.
- [`references/clash-subscription-template.yaml`](references/clash-subscription-template.yaml) — Pre-compiled ~10,000-line Mihomo subscription template (split DoH + ~9,200 `DIRECT` / `REJECT` / `FIXED-EXIT` rules); render placeholders programmatically rather than reading the entire file into context.
- [`references/shadowrocket-mobile-rules.conf`](references/shadowrocket-mobile-rules.conf) — Read when adding or auditing rules that apply to phones only; `scripts/render_shadowrocket_conf.py` places them ahead of the template rules.
- [`references/tuning-and-diagnostics.md`](references/tuning-and-diagnostics.md) — Read when selecting a VPS/IP, running isolated throughput benchmarks, evaluating kernel/protocol tweaks, or diagnosing `HY2` UDP stalls, SSH vs. `:443` reachability, and AI account risk.
