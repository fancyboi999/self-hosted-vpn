# VPS Selection, Benchmarking, & Diagnostics

## 1. VPS & IP Selection Principles

- **Route before hardware**: 1–2 vCPU and 512 MiB–1 GiB RAM saturate personal proxy workloads; China-to-VPS return routing, evening packet loss, and IP reputation determine ~80% of actual performance.
  - **Public clouds (`AWS Lightsail`, `DigitalOcean`, `GCP`)**: Clean billing, predictable static IPv4, low cost (`~$4–$5/mo`), non-optimized China return path—pair `VLESS + Reality` (stability) with `Hysteria2` (throughput recovery over lossy links). Verify how the provider meters proxy forwarding (`rx + tx` vs. `tx` only).
  - **China-optimized transit (`CN2 GIA` for Telecom, `CUII/9929` for Unicom, `CMIN2` for Mobile)**: Higher price, markedly lower evening jitter and TCP retransmission.
  - **Datacenter marketing traps**: Skip providers whose ToS forfeits refunds or charges fees when an IP is blocked, or that market datacenter ASNs as "native/ISP" without residential ASN backing. Residential SOCKS proxies (e.g., scraping proxy pools) add multi-second connect latency and are unsuitable as primary daily tunnels.
- **Buy monthly first**: Validate evening latency, UDP reachability, and target AI service login/API responses from the real user ISP before committing to long-term billing.

---

## 2. Isolated E2E Benchmark Protocol

Local workstation benchmarks fail or mislead when traffic traverses an already-active `utun` interface or system proxy. Run benchmarks from an isolated Linux test host (or a clean network namespace) with all `*_PROXY` / `*_proxy` variables unset:

1. Start an isolated `sing-box` or `mihomo` client bound to `127.0.0.1:19871` (`TUN` disabled).
2. **Identity & Reachability Gate** (10 consecutive requests, `0` failures):
   - Exit IP & country check (`https://cloudflare.com/cdn-cgi/trace` → `ip=<SERVER_IP>` and expected `loc=`).
   - Connectivity check (`https://www.gstatic.com/generate_204` → `HTTP 204`).
   - Target AI TLS/HTTP reachability (`https://api.openai.com/v1/models` → `HTTP 401` proves clean network + TLS; `https://claude.ai` → expected TLS handshake without region block).
3. **Sustained Transfer Gate** (3+ runs per protocol, `45s` timeout):
   - Download `25,000,000` bytes (`https://speed.cloudflare.com/__down?bytes=25000000`), requiring `HTTP 200` and exact byte count; record incomplete/timeout runs separately rather than averaging them away.
   - Upload `5,000,000` bytes (`https://speed.cloudflare.com/__up`) to verify upstream path.

---

## 3. Kernel & Protocol Tuning Ledger (Evidence-Driven)

Always snapshot counters (`ss -uam`, `nstat -az UdpRcvbufErrors`, `ss -ti`, NIC `tc -s qdisc`) and write a rollback script before changing server parameters.

| Parameter / Change | Verdict | Empirical Basis |
|---|---|---|
| `net.ipv4.tcp_congestion_control=bbr` + `default_qdisc=fq` | **Keep** | Lifted single-stream cross-Pacific TCP from `< 0.5 Mbps` (cubic on lossy path) to multi-Mbps baseline; zero downside. |
| `net.core.rmem_max` / `wmem_max = 16777216` (`16 MiB`) + `hysteria-server` restart | **Keep** | Eliminated thousands of cumulative `UdpRcvbufErrors` and socket drops on `HY2` (`33–59 Mbps` sustained over 180ms+ RTT). |
| Forcing `16 MiB`–`64 MiB` `tcp_rmem`/`tcp_wmem` caps | **Skip / Revert** | When `ss -ti` shows send-buffer-limited time `< 1%` alongside heavy retransmissions, throughput is loss-bound, not buffer-bound; enlarging TCP buffers showed zero repeatable gain. |
| Replacing cloud NIC multi-queue (`mq` + `fq_codel`) child qdiscs manually | **Skip / Revert** | High run-to-run variance on virtualized `ens5` queues without repeatable throughput gain; risks breaking multi-queue defaults. |
| Blindly setting `HY2` client/server `up_mbps` / `down_mbps` | **Skip unless proven** | Leave congestion on `bbr` unless testing a symmetric, known-bandwidth link where Brutal pacing outperforms BBR. |
| Modifying macOS client `sysctl` / `MTU` / `TFO` | **Skip** | Invasive on the host control plane and unsupported by bottleneck evidence unless client receive-window saturation is measured. |

---

## 4. Troubleshooting Playbooks

### `Hysteria2` Sudden Timeout While `VLESS` Works
- **Symptom**: `HY2` stalls after `30s` timeout (often after Wi-Fi roaming, macOS sleep/wake, or carrier NAT refresh), whereas `VLESS` on the same `<SERVER_IP>:443` stays healthy.
- **Check**: Capture `tcpdump -ni <iface> udp port 443` on the VPS while triggering a client request.
  - *Initial client UDP packets arrive and VPS sends replies, followed by silence from client*: Server is healthy; the local client's QUIC/UDP session state is wedged, carrier NAT dropped UDP mapping, or return UDP packets are throttled/dropped locally. Switch `FIXED-EXIT` to `Exit-VLESS` immediately for uninterrupted TCP work; test a mobile hotspot later to separate local ISP/router UDP filtering from client core state.
  - *Zero UDP packets reach the VPS*: Check cloud security group `UDP 443` and ISP UDP blocking on `:443`.

### SSH Timeout vs. Proxy Outage
- **Rule**: Separate management-plane (`TCP 22`) failures from data-plane (`TCP/UDP 443`) failures.
- **Check**: Probe `TCP 22`, `TCP 443`, and `TCP 8443` from both local and an independent remote Linux host before declaring the node dead or rotating IPs. Cloud firewall rules, `sshd` state, or ISP port-22 throttling can fail independently while `sing-box` `:443` remains online.

### Subscription Fetch or Renewal Failure
- **Check 1 (Cloud Firewall)**: Verify `TCP 80` (required every ~4–5 days for Let's Encrypt `shortlived` HTTP-01 renewal) and `TCP 8443` are open in the **cloud console firewall**, not only inside Debian `ufw`/`nftables`.
- **Check 2 (Certificate Validity & IP SAN)**: Run `/usr/local/sbin/vpn-subscription-cert-check`. Standard domain certificates fail when clients connect to an IP URL; the certificate must carry an `IP Address:<SERVER_IP>` Subject Alternative Name from `--ip-address <SERVER_IP> --preferred-profile shortlived`.

### AI Service Region Block or Account Risk (`Claude` / `OpenAI` / `X`)
- Verify single-IP consistency: confirm both browser and terminal CLI exit from `<SERVER_IP>` (`curl -s https://cloudflare.com/cdn-cgi/trace`), and confirm DNS queries for the AI domain hit `#FIXED-EXIT` rather than domestic resolvers.
- If `X` checkout (`DependencyError`) or AI login rejects a clean datacenter IP, compare against a known-working exit before blaming upstream service outages—datacenter ASN risk scoring can block payment/auth flows selectively even when general HTTPS returns `200`.
