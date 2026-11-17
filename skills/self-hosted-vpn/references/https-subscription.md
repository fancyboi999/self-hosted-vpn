# Domainless HTTPS Subscription Service (`TCP 80` + `TCP 8443`)

Deliver Clash (`clash.yaml`) and Shadowrocket (`shadowrocket.txt` nodes, plus `shadowrocket.conf` rules on the designated rules host) subscriptions over CA-trusted HTTPS directly on `<SERVER_IP>:8443` without buying or binding a domain name.

## Architecture

1. **Let's Encrypt `shortlived` IP Certificate**: Certbot `>= 5.x` in an isolated virtualenv (`/opt/vpn-certbot`) authenticates `<SERVER_IP>` via `http-01` webroot on `TCP 80`. Everything outside `/.well-known/acme-challenge/` on `:80` returns `404`.
2. **Nginx `:8443` TLS Termination**: Serves only exact-match paths gated by a high-entropy token (`/sub/<SUB_TOKEN>/clash.yaml`, `/sub/<SUB_TOKEN>/shadowrocket.txt`, and on the rules host `/sub/<SUB_TOKEN>/shadowrocket.conf`), `GET`/`HEAD` only, rate-limited, `access_log off`, `/` returning `404`.
3. **Loopback Usage Server (`127.0.0.1:19890`)**: Reads the payloads in `/srv/vpn-subscriptions/` and attaches `Subscription-Userinfo` (monthly NIC `rx`/`tx` bytes across reboots) plus `Profile-Update-Interval: 6`.
4. **6-Hour Renewal & Verification Timer**: Short-lived IP certificates last ~6 days; a systemd timer checks renewal every 6 hours, reloads Nginx without touching `:443` proxy daemons, and verifies the live `:8443` certificate chain against `-verify_ip <SERVER_IP>`.

---

## 1. Certbot `>= 5.x` & Initial IP Certificate

Debian system packages often ship older Certbot releases that lack `--preferred-profile shortlived` IP certificate support. Install Certbot `>= 5.x` inside `/opt/vpn-certbot`:

```bash
apt-get update && apt-get install -y python3-venv nginx openssl
python3 -m venv /opt/vpn-certbot
/opt/vpn-certbot/bin/pip install --upgrade pip certbot
install -d -m 0755 /var/lib/letsencrypt/.well-known/acme-challenge
```

Bootstrap Nginx with the `:80` server block first, then request the IP certificate:

```bash
/opt/vpn-certbot/bin/certbot certonly \
  --non-interactive \
  --agree-tos \
  --register-unsafely-without-email \
  --authenticator webroot \
  --webroot-path /var/lib/letsencrypt \
  --ip-address <SERVER_IP> \
  --preferred-profile shortlived \
  --key-type ecdsa
```

---

## 2. Nginx Gateway (`/etc/nginx/sites-available/vpn-subscription`)

Generate `<SUB_TOKEN>` via `openssl rand -base64 32 | tr '+/' '-_' | tr -d '='`.

```nginx
server {
    listen 80 default_server;
    server_name <SERVER_IP>;
    server_tokens off;
    access_log off;
    error_log /var/log/nginx/vpn-sub-error.log crit;

    location ^~ /.well-known/acme-challenge/ {
        root /var/lib/letsencrypt;
        default_type text/plain;
        try_files $uri =404;
    }
    location / { return 404; }
}

limit_req_zone $binary_remote_addr zone=vpn_sub_rate:1m rate=5r/s;

server {
    listen 8443 ssl;
    server_name <SERVER_IP>;
    server_tokens off;

    ssl_certificate /etc/letsencrypt/live/<SERVER_IP>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<SERVER_IP>/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:VPN_SUB_TLS:1m;

    access_log off;
    error_log /var/log/nginx/vpn-sub-error.log crit;
    add_header Cache-Control "private, no-store" always;
    add_header X-Content-Type-Options nosniff always;

    location / { return 404; }

    location = /sub/<SUB_TOKEN>/clash.yaml {
        limit_except GET { deny all; }
        limit_req zone=vpn_sub_rate burst=10 nodelay;
        proxy_pass http://127.0.0.1:19890/clash.yaml;
        default_type text/plain;
        add_header Content-Disposition 'attachment; filename="SelfHosted-Exit.yaml"';
        add_header Cache-Control "private, no-store" always;
        add_header X-Content-Type-Options nosniff always;
    }

    location = /sub/<SUB_TOKEN>/shadowrocket.txt {
        limit_except GET { deny all; }
        limit_req zone=vpn_sub_rate burst=10 nodelay;
        proxy_pass http://127.0.0.1:19890/shadowrocket.txt;
        default_type text/plain;
        add_header Content-Disposition 'attachment; filename="SelfHosted-Shadowrocket.txt"';
        add_header Cache-Control "private, no-store" always;
        add_header X-Content-Type-Options nosniff always;
    }
}
```

On the rules host, add a third `location` block for `/sub/<SUB_TOKEN>/shadowrocket.conf` with the same body, proxying to `http://127.0.0.1:19890/shadowrocket.conf`.

Remove `/etc/nginx/sites-enabled/default`, symlink `vpn-subscription`, and validate with `nginx -t && systemctl reload nginx`.

---

## 3. NIC Traffic Accounting & Subscription Daemon

Store subscription payloads in `/srv/vpn-subscriptions/` (`chown root:www-data`, `chmod 0640`); a payload absent from the directory answers `503`. Adjust `IFACE` (e.g., `ens5` or `eth0`) and `TOTAL` (e.g., `1024**4` for 1 TiB, `4 * 1024**4` for 4 TiB) to match the VPS plan's monthly quota. Note whether the cloud provider meters both inbound + outbound or outbound-only.

### `/usr/local/sbin/vpn-subscription-usage.py`

```python
#!/usr/bin/python3
import datetime as dt
import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE = Path("/var/lib/vpn-subscription-usage/state.json")
IFACE = "<PRIMARY_IFACE>"       # e.g. ens5
TOTAL = 1024 ** 4               # bytes; adjust to plan quota
LOCK = threading.Lock()


def read_counter():
    stats = Path(f"/sys/class/net/{IFACE}/statistics")
    return {
        "rx": int((stats / "rx_bytes").read_text()),
        "tx": int((stats / "tx_bytes").read_text()),
        "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    }


def advance(state, counter, now):
    month = now.strftime("%Y-%m")
    if state is None:
        return {
            "month": month,
            "rx": counter["rx"],
            "tx": counter["tx"],
            "last": counter,
            "started_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "monthly_history": {},
        }
    if state["month"] != month:
        state["monthly_history"][state["month"]] = {"rx": state["rx"], "tx": state["tx"]}
        state["monthly_history"] = dict(sorted(state["monthly_history"].items())[-12:])
        state["month"] = month
        state["rx"] = 0
        state["tx"] = 0
    prev = state["last"]
    for key in ("rx", "tx"):
        delta = (
            counter[key] - prev[key]
            if counter["boot"] == prev["boot"] and counter[key] >= prev[key]
            else counter[key]
        )
        state[key] += delta
    state["last"] = counter
    state["updated_at"] = now.isoformat()
    return state


state = json.loads(STATE.read_text()) if STATE.exists() else None


def sample():
    global state
    with LOCK:
        state = advance(state, read_counter(), dt.datetime.now(dt.timezone.utc))
        STATE.parent.mkdir(parents=True, exist_ok=True)
        temp = STATE.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, STATE)
        return state["rx"], state["tx"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.reply(head=False)

    def do_HEAD(self):
        self.reply(head=True)

    def reply(self, head):
        paths = {
            "/clash.yaml": "/srv/vpn-subscriptions/clash.yaml",
            "/shadowrocket.txt": "/srv/vpn-subscriptions/shadowrocket.txt",
            "/shadowrocket.conf": "/srv/vpn-subscriptions/shadowrocket.conf",
        }
        if self.path not in paths:
            self.send_error(404)
            return
        try:
            rx, tx = sample()
            data = Path(paths[self.path]).read_bytes()
        except Exception:
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Subscription-Userinfo", f"upload={rx}; download={tx}; total={TOTAL}")
        self.send_header("Profile-Update-Interval", "6")
        self.send_header("Cache-Control", "private, no-store")
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    sample()
    server = ThreadingHTTPServer(("127.0.0.1", 19890), Handler)
    stop = threading.Event()

    def periodic():
        while not stop.wait(10):
            try:
                sample()
            except Exception:
                os._exit(1)

    threading.Thread(target=periodic, daemon=True).start()

    def shutdown(*_args):
        stop.set()
        sample()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    server.serve_forever()
    server.server_close()
```

### `/etc/systemd/system/vpn-subscription-usage.service`

```ini
[Unit]
Description=Machine traffic accounting and subscription usage headers
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
StateDirectory=vpn-subscription-usage
StateDirectoryMode=0700
ExecStart=/usr/bin/python3 /usr/local/sbin/vpn-subscription-usage.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
UMask=0077

[Install]
WantedBy=multi-user.target
```

---

## 4. 6-Hour Certificate Renewal & Live Verification

### `/usr/local/sbin/vpn-subscription-reload` (`0755`)

```sh
#!/bin/sh
set -eu
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
/usr/bin/logger -p daemon.notice -t vpn-subscription 'Renewed IP certificate loaded by nginx; proxy services unchanged'
```

### `/usr/local/sbin/vpn-subscription-cert-check` (`0755`)

Asserts both disk certificate and served `:8443` TLS IP SAN certificate have at least 48 hours (`172800s`) of remaining validity:

```bash
#!/bin/bash
set -euo pipefail
/usr/bin/openssl x509 -in /etc/letsencrypt/live/<SERVER_IP>/cert.pem -noout -checkend 172800 >/dev/null
/usr/bin/timeout 15 /usr/bin/openssl s_client \
  -connect 127.0.0.1:8443 \
  -verify_ip <SERVER_IP> \
  -verify_return_error \
  -CApath /etc/ssl/certs </dev/null 2>/dev/null \
  | /usr/bin/openssl x509 -noout -checkend 172800 >/dev/null
```

### `/etc/systemd/system/vpn-subscription-renew.service` & `.timer`

```ini
# /etc/systemd/system/vpn-subscription-renew.service
[Unit]
Description=Renew VPN subscription IP certificate and verify served certificate
Wants=network-online.target
After=network-online.target nginx.service

[Service]
Type=oneshot
ExecStart=/opt/vpn-certbot/bin/certbot renew --non-interactive --no-random-sleep-on-renew --deploy-hook /usr/local/sbin/vpn-subscription-reload
ExecStartPost=/usr/local/sbin/vpn-subscription-cert-check
TimeoutStartSec=300
PrivateTmp=true
UMask=0077
```

```ini
# /etc/systemd/system/vpn-subscription-renew.timer
[Unit]
Description=Check VPN subscription certificate renewal every six hours

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with `systemctl daemon-reload && systemctl enable --now vpn-subscription-usage.service vpn-subscription-renew.timer` and test immediately via `systemctl start vpn-subscription-renew.service`.
