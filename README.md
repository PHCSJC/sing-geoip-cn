# sing-geoip-cn

自动更新的 [sing-box](https://github.com/SagerNet/sing-box) `geoip-cn` 规则集，**仅含 IPv4**。

数据聚合自 [alecthw/mmdb_china_ip_list](https://github.com/alecthw/mmdb_china_ip_list) 当前使用的同一批公开源，
去重合并后编译为 sing-box 原生二进制格式 `.srs`。

## 文件

| 文件 | 说明 |
|---|---|
| `dist/geoip-cn.srs` | sing-box 二进制规则集 |
| `dist/geoip-cn.txt` | 纯文本 CIDR 列表，一行一条 |
| `dist/version` | 构建时间戳（UTC, YYYYMMDDHHMM） |

**固定下载地址：**

```
https://raw.githubusercontent.com/PHCSJC/sing-geoip-cn/main/dist/geoip-cn.srs
```

## 数据来源

与 alecthw 的 `buildLite()` 完全一致，仅取 IPv4：

| 来源 | 文件 |
|---|---|
| [17mon/china_ip_list](https://github.com/17mon/china_ip_list) | `china_ip_list.txt` |
| [metowolf/iplist](https://github.com/metowolf/iplist)（纯真 CN） | `data/special/china.txt` |
| [ispip.clang.cn](https://ispip.clang.cn)（Clang.CN） | `all_cn.txt` |
| [gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip) | `ip-lists/china.txt` |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | `Cloud/CloudCN/CloudCN.list` |

> alecthw README 提到的 `ali AS37963` 已于 2022-10（commit `2d2ec8f9`）注释停用，
> 其抓取方式是解析 `whois.ipip.net` 的 HTML，不稳定。本仓库同样不收录。

## 用法

### 远程自动更新（推荐）

sing-box 1.14+ 用 `http_clients`：

```json
{
  "http_clients": [
    { "tag": "rs-client" }
  ],
  "route": {
    "default_http_client": "rs-client",
    "rule_set": [
      {
        "type": "remote",
        "tag": "geoip-cn",
        "format": "binary",
        "url": "https://raw.githubusercontent.com/PHCSJC/sing-geoip-cn/main/dist/geoip-cn.srs",
        "update_interval": "3d",
        "http_client": "rs-client"
      }
    ],
    "rules": [
      { "action": "sniff" },
      { "protocol": "dns", "action": "hijack-dns" },
      { "ip_is_private": true, "outbound": "direct" },
      { "rule_set": "proxy-domain", "outbound": "proxy" },
      { "action": "resolve" },
      { "rule_set": "geoip-cn", "outbound": "direct" }
    ],
    "final": "proxy"
  }
}
```

**sing-box 1.13 及更早**用旧写法：

```json
{
  "type": "remote",
  "tag": "geoip-cn",
  "format": "binary",
  "url": "https://raw.githubusercontent.com/PHCSJC/sing-geoip-cn/main/dist/geoip-cn.srs",
  "download_detour": "direct",
  "update_interval": "3d"
}
```

> `download_detour` 在 sing-box 1.14.0 标记废弃，1.16.0 移除。
> `http_client` 里不能写 `"detour": "direct"`，会报 `detour to an empty direct outbound makes no sense`。

### 本地文件

```json
{
  "type": "local",
  "tag": "geoip-cn",
  "format": "binary",
  "path": "/data/adb/sing-box/geoip-cn.srs"
}
```

## 构建

无第三方依赖，仅 Python 标准库：

```bash
python3 build.py
sing-box rule-set compile cache/rule-set-src.json -o dist/geoip-cn.srs
```

GitHub Actions 每周一、周四 03:00 UTC 自动构建并提交到 `dist/`。

## 与 alecthw 的差异

两者用同一批源，但**不同时间点抓取**，产物会有细微差异（通常 < 0.01%）。
这不是错误——上游源站本身在增删 IP 段。

输出格式不同：

| 项目 | alecthw | 本仓库 |
|---|---|---|
| 格式 | MaxMind mmdb | sing-box srs |
| sing-box 1.12+ 可用 | ❌ mmdb 已被移除 | ✅ |
| IPv6 | 含 | 不含 |
| 额外依赖 | 需要 mmdb 库 | 无 |

## 注意

- **仅 IPv4**。如需 IPv6 请改 `build.py` 中的 `if net.version != 4: continue`。
- 收录口径是"中国实体持有的 IP"，包含阿里云、腾讯云等厂商的**海外节点**（物理位置在美国、新加坡、德国等），这些 IP 会走直连。
- 收录了 Cloudflare `104.28.0.0/16` 等段（国内有节点），该段内同时存在需要代理的站点，可能被误判为直连。

## License

数据来自上述公开项目，遵循各自许可证。本仓库脚本为 MIT。
