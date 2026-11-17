# Server Configurations (`TCP 443` + `UDP 443`)

Target OS: Debian 12 (Bookworm) or newer with a dedicated static IPv4 (`<SERVER_IP>`).

## 1. Kernel Baseline (`/etc/sysctl.d/`)

Persist BBR congestion control and `16 MiB` UDP socket buffer caps (prevents QUIC receive/send buffer drops under high BDP cross-Pacific links):

```ini
# /etc/sysctl.d/99-bbr.conf
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
```

```ini
# /etc/sysctl.d/99-hysteria-buffers.conf
net.core.rmem_max=16777216
net.core.wmem_max=16777216
```

Apply with `sysctl --system`. Existing UDP sockets keep their creation-time buffer sizes, so restart `hysteria-server` whenever `99-hysteria-buffers.conf` changes, then verify live socket allocations (`rb` and `tb` equal `16777216`):

```bash
ss -uam sport = :443
```

---

## 2. `sing-box` `VLESS + Reality` (`TCP 443`)

Install `sing-box` from the official package repository (`https://sing-box.sagernet.org/installation/package-manager/`) rather than third-party shell wrappers.

### Generate Credentials

```bash
sing-box generate uuid                  # run twice: <DESKTOP_UUID> and <MOBILE_UUID>
sing-box generate reality-keypair       # outputs PrivateKey (<REALITY_PRIVATE_KEY>) and PublicKey (<REALITY_PUBLIC_KEY>)
openssl rand -hex 8                     # outputs 16-hex-char <REALITY_SHORT_ID>
```

### `/etc/sing-box/config.json` (Compatible with `sing-box` `1.13.x` and `1.14.x`)

```json
{
  "log": {
    "level": "info",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "vless",
      "tag": "vless-in",
      "listen": "::",
      "listen_port": 443,
      "users": [
        {
          "name": "desktop",
          "uuid": "<DESKTOP_UUID>",
          "flow": "xtls-rprx-vision"
        },
        {
          "name": "mobile",
          "uuid": "<MOBILE_UUID>",
          "flow": "xtls-rprx-vision"
        }
      ],
      "tls": {
        "enabled": true,
        "server_name": "<REALITY_SNI>",
        "reality": {
          "enabled": true,
          "handshake": {
            "server": "<REALITY_SNI>",
            "server_port": 443
          },
          "private_key": "<REALITY_PRIVATE_KEY>",
          "short_id": [
            "<REALITY_SHORT_ID>"
          ],
          "max_time_difference": "1m"
        }
      }
    }
  ],
  "outbounds": [
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "route": {
    "final": "direct"
  }
}
```

### Operational Notes
- Validate before reload: `sing-box check -c /etc/sing-box/config.json && systemctl enable --now sing-box`.
- `sing-box` `>= 1.13` Reality clients enforce `uTLS`; always set client fingerprint to `chrome` (`client-fingerprint: chrome` in Mihomo, `fp=chrome` in URI, `utls.fingerprint: "chrome"` in `sing-box` client).
- Pick `<REALITY_SNI>` as a reputable TLS 1.3 + H2 domain hosted close to the VPS; verify `curl -I --tlsv1.3 https://<REALITY_SNI>` from the VPS completes handshake in `< 20ms`.

---

## 3. Standalone `Hysteria2` (`UDP 443`)

Run the official standalone `hysteria` binary on `UDP 443` alongside `sing-box` on `TCP 443` so version upgrades and restarts stay decoupled.

### Non-Root User & Self-Signed Certificate Pinning

```bash
useradd --system --home-dir /var/lib/hysteria --create-home --shell /usr/sbin/nologin hysteria
install -d -m 0750 -o root -g hysteria /etc/hysteria

openssl req -x509 -nodes -newkey ec:<(openssl ecparam -name prime256v1) \
  -keyout /etc/hysteria/server.key \
  -out /etc/hysteria/server.crt \
  -subj "/CN=<SERVER_IP>" \
  -days 3650

chown root:hysteria /etc/hysteria/server.key /etc/hysteria/server.crt
chmod 0640 /etc/hysteria/server.key /etc/hysteria/server.crt
```

Extract the certificate SHA-256 digests used for client pinning:

```bash
# 64-char lowercase hex for Mihomo `fingerprint:`
openssl x509 -in /etc/hysteria/server.crt -noout -fingerprint -sha256 | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f'

# Colon-separated uppercase hex for Hysteria2 URI `pinSHA256=`
openssl x509 -in /etc/hysteria/server.crt -noout -fingerprint -sha256 | cut -d= -f2
```

### `/etc/hysteria/config.yaml`

Generate `<HY2_PASSWORD>` via `openssl rand -base64 24`.

```yaml
listen: :443

tls:
  cert: /etc/hysteria/server.crt
  key: /etc/hysteria/server.key
  sniGuard: disable

auth:
  type: password
  password: <HY2_PASSWORD>

congestion:
  type: bbr
  bbrProfile: standard

speedTest: true
disableUDP: false

masquerade:
  type: proxy
  proxy:
    url: https://<REALITY_SNI>/
    rewriteHost: true
```

`sniGuard: disable` is required when clients connect directly to `<SERVER_IP>` with IP SNI rather than a domain name.

### `/etc/systemd/system/hysteria-server.service`

```ini
[Unit]
Description=Hysteria Server Service (config.yaml)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/hysteria server --config /etc/hysteria/config.yaml
WorkingDirectory=~
User=hysteria
Group=hysteria
Environment=HYSTERIA_LOG_LEVEL=info
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
NoNewPrivileges=true
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```
