# Client Profiles (`clash.yaml`, `shadowrocket.txt`, `shadowrocket.conf`)

## Design Invariants

1. **Rules target the slot, never a node**: In Mihomo the slot is the `type: select` group `FIXED-EXIT`, listing `Exit-HY2` and `Exit-VLESS`; in Shadowrocket it is the built-in `PROXY` policy, filled by the node selected on the home screen. Nodes from several machines may share the slot, and the user picks one by hand; `url-test` or `load-balance` across machines would move AI web sessions and CLI tokens between IPs.
2. **Certificate pinning on `HY2`**: In Mihomo, pair `skip-cert-verify: true` with `fingerprint: <HY2_CERT_SHA256_HEX64>` (64-char lowercase SHA-256 hex of `server.crt`). In Hysteria2 URIs, pass `pinSHA256=<HY2_CERT_SHA256_COLON_HEX>`.
3. **Split DNS without leaks**:
   - `enhanced-mode: fake-ip`, `ipv6: false`.
   - Domestic `nameserver` (`dns.alidns.com`, `doh.pub`) and `720+` domestic `nameserver-policy` entries resolve `CN` and CDN traffic locally; `fake-ip-filter` excludes `+.local` and WeChat media hosts (`+.qpic.cn`, `+.gtimg.cn`, `+.gtimg.com`, `+.weixin.qq.com`).
   - AI and overseas checkout domains (`+.claude.ai`, `+.claude.com`, `+.anthropic.com`, `+.chatgpt.com`, `+.openai.com`, `+.gemini.google.com`, `+.aistudio.google.com`, `+.generativelanguage.googleapis.com`, `pay.apple.com`, `paymentrelayservice.apple.com`) and `fallback` (`1.1.1.1`, `8.8.8.8`) query DoH via `#FIXED-EXIT` so DNS answers originate from the proxy exit (overriding `+.apple.com` domestic DoH for Apple Pay).
4. **Zero-dependency pre-compiled routing**: [`clash-subscription-template.yaml`](clash-subscription-template.yaml) embeds `~9,200` inline rules so clients boot cleanly without fetching external `rule-providers`:
   - Private/LAN CIDRs, `~800` domestic app/CDN rules, and bulk game download CDNs (`Steam` / `Epic` / `Microsoft` delivery) go `DIRECT`.
   - `~1,600` ad/tracker domains hit `REJECT`.
   - Apple Pay (`pay.apple.com`, `paymentrelayservice.apple.com`), AI platforms, and `~6,800` overseas domains/CIDRs match `FIXED-EXIT` **before** `GEOIP,CN,DIRECT`, preventing domestic DNS queries on known overseas hosts, followed by `GEOIP,CN,DIRECT` and catch-all `MATCH,FIXED-EXIT`.

---

## 1. Rendering `/srv/vpn-subscriptions/clash.yaml`

[`clash-subscription-template.yaml`](clash-subscription-template.yaml) (`~10,000` lines) is the authoritative Mihomo template. Render its placeholders programmatically rather than reading the entire file into context:

| Placeholder | Value |
|---|---|
| `<SERVER_IP>` | Static public IPv4 of the VPS |
| `<HY2_PASSWORD>` | Hysteria2 auth password from `/etc/hysteria/config.yaml` |
| `<HY2_CERT_SHA256_HEX64>` | 64-char lowercase SHA-256 hex digest of `/etc/hysteria/server.crt` |
| `<DESKTOP_UUID>` | Desktop VLESS UUID from `/etc/sing-box/config.json` |
| `<REALITY_SNI>` | Reality SNI hostname configured on the server (a reputable TLS 1.3 + H2 domain proximate to the VPS) |
| `<REALITY_PUBLIC_KEY>` | Reality X25519 public key |
| `<REALITY_SHORT_ID>` | Reality `short_id` hex string |

```bash
python3 - <<'PY'
import re
from pathlib import Path

src = Path("references/clash-subscription-template.yaml").read_text()
replacements = {
    "<SERVER_IP>": "...",
    "<HY2_PASSWORD>": "...",
    "<HY2_CERT_SHA256_HEX64>": "...",
    "<DESKTOP_UUID>": "...",
    "<REALITY_SNI>": "...",
    "<REALITY_PUBLIC_KEY>": "...",
    "<REALITY_SHORT_ID>": "...",
}
for k, v in replacements.items():
    src = src.replace(k, v)

leftover = set(re.findall(r"<[A-Z0-9_]+>", src))
assert not leftover, f"Unreplaced placeholders: {leftover}"
Path("/srv/vpn-subscriptions/clash.yaml").write_text(src)
PY
chown root:www-data /srv/vpn-subscriptions/clash.yaml
chmod 0640 /srv/vpn-subscriptions/clash.yaml
```

Validate syntax offline with an isolated Mihomo check before publishing:

```bash
mihomo -t -f /srv/vpn-subscriptions/clash.yaml
```

---

## 2. Machine-Private Rules (Local Overlay)

Intranet `hosts` mappings, direct rules for remote-desktop clients (preventing UDP relay loops), and similar rules belong to one user's environment. Keep them in a local **overlay** outside this skill and outside any repository, so the published templates stay neutral and a re-render never loses them.

- **Mihomo desktop**: a Clash client Profile Enhancement Script (`.js`) applied after each subscription update:

```javascript
function main(config) {
  const intranetHost = "intranet.example.internal";
  const intranetIp = "10.20.30.40";
  const localDirectRules = [
    `DOMAIN,${intranetHost},DIRECT`,
    `IP-CIDR,${intranetIp}/32,DIRECT,no-resolve`,
    // Optional: bypass local remote-desktop processes to avoid UDP relay loops
    // "PROCESS-NAME,<REMOTE_DESKTOP_PROCESS>,DIRECT",
  ];

  const dns = config.dns ?? {};
  const fakeIpFilter = Array.isArray(dns["fake-ip-filter"]) ? dns["fake-ip-filter"] : [];
  dns["fake-ip-filter"] = [intranetHost, ...fakeIpFilter.filter((x) => x !== intranetHost)];
  // Optional: bind a local loopback DNS port when another tunnel owns system DNS
  // dns.listen = "127.0.0.1:1053";
  config.dns = dns;
  config.hosts = { ...(config.hosts ?? {}), [intranetHost]: intranetIp };

  const rules = Array.isArray(config.rules) ? config.rules : [];
  config.rules = [
    ...localDirectRules,
    ...rules.filter((r) => !localDirectRules.includes(r)),
  ];
  return config;
}
```

- **Shadowrocket mobile**: iOS has no post-update script, so the overlay is merged when the rules config is rendered (section 3). The overlay is a fragment with any of `[General]`, `[Host]`, `[Rule]`; its rules go ahead of the template rules, and list-valued `[General]` keys (`always-real-ip`, `skip-proxy`) extend the defaults:

```ini
[General]
always-real-ip = intranet.example.internal
private-ip-answer = true
[Host]
intranet.example.internal = 10.20.30.40
[Rule]
DOMAIN,intranet.example.internal,DIRECT
```

---

## 3. Shadowrocket (Mobile)

Shadowrocket keeps nodes and rules in two separate objects, each with its own update cycle. Publish them separately: nodes per machine, rules once.

| Object | File | Published by | Contains | Phone imports it |
|---|---|---|---|---|
| Node subscription | `shadowrocket.txt` | every machine | that machine's node URIs | once per machine |
| Rules config | `shadowrocket.conf` | one designated machine | `[General]` + rules targeting `PROXY` / `DIRECT` / `REJECT` | once in total |

### Node subscription (`/srv/vpn-subscriptions/shadowrocket.txt`)

Use `<MOBILE_UUID>` so mobile connections can be audited and rotated independently of desktop credentials. Encode the newline-joined URI list as single-line Base64 (`base64 -w 0` on Linux):

```text
hysteria2://<URLENCODED_HY2_PASSWORD>@<SERVER_IP>:443/?sni=<SERVER_IP>&pinSHA256=<HY2_CERT_SHA256_COLON_HEX>#Exit-HY2
vless://<MOBILE_UUID>@<SERVER_IP>:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=<REALITY_SNI>&fp=chrome&pbk=<REALITY_PUBLIC_KEY>&sid=<REALITY_SHORT_ID>&type=tcp&headerType=none#Exit-VLESS
```

With several machines, give each node a name that tells the machines apart (for example a region or role suffix); the name is only a label, since no rule refers to it.

### Rules config (`/srv/vpn-subscriptions/shadowrocket.conf`)

[`clash-subscription-template.yaml`](clash-subscription-template.yaml) is the single source of shared rules. [`../scripts/render_shadowrocket_conf.py`](../scripts/render_shadowrocket_conf.py) converts it: slot targets become `PROXY`, `MATCH` becomes `FINAL`, a leading `IP-CIDR6,::/0,REJECT` closes native IPv6 on cellular, the mobile-only rules in [`shadowrocket-mobile-rules.conf`](shadowrocket-mobile-rules.conf) (telemetry ingestion `REJECT`, AI / payment / STUN hosts on the slot) go ahead of the template rules, and `[General]` disables IPv6, hijacks port-53 DNS, and rejects UDP rather than falling back to direct.

```bash
python3 scripts/render_shadowrocket_conf.py \
  --update-url "https://<SERVER_IP>:8443/sub/<SUB_TOKEN>/shadowrocket.conf" \
  --overlay <LOCAL_OVERLAY_FILE> \
  -o shadowrocket.conf          # omit --overlay when there are no machine-private rules
```

Install the output on the rules host with the same ownership as the other payloads (`root:www-data`, `0640`). The `update-url` embeds `<SUB_TOKEN>`, so the rendered file is as sensitive as the URL.

### QR codes and import

Generate PNG QR codes locally (`0600`) with `qrencode -o <name>.png "<CONTENT>"`:

| QR | Content | Result on the phone |
|---|---|---|
| Nodes, one per machine | `https://<SERVER_IP>:8443/sub/<SUB_TOKEN>/shadowrocket.txt` | adds a node subscription |
| Rules, one in total | `shadowrocket://config/add/https://<SERVER_IP>:8443/sub/<SUB_TOKEN>/shadowrocket.conf` | adds a remote config |

- *Done when*: each QR decodes back to its intended content, and on the phone the rules config is the one in use, global routing is set to config mode, a node is selected by hand, and `https://cloudflare.com/cdn-cgi/trace` opened on the phone reports the selected machine's `<SERVER_IP>`. Report any of these the user has not confirmed as unverified.
