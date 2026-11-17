# Self-Hosted VPN Skill

**固定单一出口，一份规则源同时喂给桌面与手机，全程可命令验证。**

这是一个面向 Coding Agent（Claude Code、Codex、Antigravity 等）的自建海外代理与分流维护 Skill。基于 Debian 12+ 单租户 VPS，提供无域名双协议核心（`TCP 443` `sing-box` `VLESS + Reality` 与 `UDP 443` 独立 `Hysteria2`）、Let's Encrypt 短期 IP 证书 HTTPS 订阅，以及规则与节点解耦的“槽位（Slot）”客户端分流体系。

[English](README.md) · [Skill 正文](skills/self-hosted-vpn/SKILL.md)

## 安装

```sh
npx skills add fancyboi999/self-hosted-vpn --skill self-hosted-vpn
```

手动安装时，将 `skills/self-hosted-vpn/` 目录复制到你的 Agent 技能目录（如 `~/.agents/skills/self-hosted-vpn/` 或 `~/.claude/skills/self-hosted-vpn/`）。本技能默认设置 `disable-model-invocation: true`，仅在你显式点名调用时执行，不会在后台自动触发。

## 核心设计

- **无域名双协议服务端（`TCP 443` + `UDP 443`）**：`sing-box` `VLESS + Reality`（`xtls-rprx-vision`、`uTLS` `chrome` 指纹、桌面与手机独立 UUID）负责稳定日常连接；独立 `Hysteria2` 进程（`16 MiB` UDP 缓冲区、`fq + bbr`、自签证书 SHA-256 指纹绑定）负责高丢包跨洋链路提速。
- **无域名可信 HTTPS 订阅（`TCP 80` + `TCP 8443`）**：使用 Certbot `>= 5.x` 直接为服务器公网 IPv4 签发 Let's Encrypt `shortlived` 短期 IP 证书（含 `IP Address` SAN），在 `:8443` 高熵随机路径下分发订阅，配合 6 小时自动续期检查与网卡流量统计头，无需购买域名，也不重启 `:443` 转发服务。
- **“槽位”解耦分流（一份规则适配多台机器）**：所有分流规则只指向抽象槽位（桌面 Mihomo 的手动 `select` 组 `FIXED-EXIT`，手机 Shadowrocket 的内置 `PROXY`），不写死机器名或节点名。桌面 `clash.yaml` 与手机远程规则配置 `shadowrocket.conf` 由脚本 `scripts/render_shadowrocket_conf.py` 从同一份约 9,200 条预编译模板生成（含 `fake-ip`、海外 AI 与 `pay.apple.com` 远端 DoH、全量 `no-resolve` 网段及移动端崩溃遥测拦截）。新增或更换出口机只需多扫一张节点订阅码，分流规则无需改动。
- **宿主机网络控制面隔离**：所有握手探测、订阅拉取和吞吐测试均在独立临时端口或远端测试机完成，不重启、不切换本机正在运行的代理客户端、TUN 网卡与系统 DNS。

## 目录结构

- [`skills/self-hosted-vpn/SKILL.md`](skills/self-hosted-vpn/SKILL.md)：分阶段部署、安全红线与完成标准
- [`skills/self-hosted-vpn/scripts/render_shadowrocket_conf.py`](skills/self-hosted-vpn/scripts/render_shadowrocket_conf.py)：从共享 Mihomo 模板与可选本地叠加文件生成不含节点信息的 Shadowrocket 规则配置
- [`skills/self-hosted-vpn/references/server-configs.md`](skills/self-hosted-vpn/references/server-configs.md)：内核 `sysctl`、`sing-box` 与独立 `Hysteria2` 配置模板
- [`skills/self-hosted-vpn/references/https-subscription.md`](skills/self-hosted-vpn/references/https-subscription.md)：Let's Encrypt 短期 IP 证书、Nginx `:8443` 与自动续期配置
- [`skills/self-hosted-vpn/references/client-profiles.md`](skills/self-hosted-vpn/references/client-profiles.md)：`clash.yaml` 渲染、私有内网叠加层、手机端双码分离与二维码生成
- [`skills/self-hosted-vpn/references/clash-subscription-template.yaml`](skills/self-hosted-vpn/references/clash-subscription-template.yaml)：零外部依赖的预编译 Mihomo 分流订阅模板
- [`skills/self-hosted-vpn/references/shadowrocket-mobile-rules.conf`](skills/self-hosted-vpn/references/shadowrocket-mobile-rules.conf)：移动端专属规则（遥测接收端 `REJECT`、AI/内购/WebRTC STUN 锁定槽位）
- [`skills/self-hosted-vpn/references/tuning-and-diagnostics.md`](skills/self-hosted-vpn/references/tuning-and-diagnostics.md)：隔离压测标准、内核参数实证台账与常见排障手册

## 许可

[MIT](LICENSE)
