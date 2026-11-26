# sing-geoip-cn

自动更新的 [sing-box](https://github.com/SagerNet/sing-box) `geoip-cn` 规则集，**仅含 IPv4**。

数据聚合自多个公开的中国 IP 列表，去重合并后编译为 sing-box 原生二进制格式 `.srs`。

## 文件

| 文件 | 说明 |
|---|---|
| `dist/geoip-cn.srs` | sing-box 二进制规则集，直接给 `type: local` 用 |
| `dist/geoip-cn.json` | 纯文本 CIDR 列表，一行一条 |
| `dist/version` | 构建时间戳 |

## 数据来源

| 来源 | 说明 |
|---|---|
| [17mon/china_ip_list](https://github.com/17mon/china_ip_list) | 国内 IP 段 |
| [metowolf/iplist](https://github.com/metowolf/iplist) | special/china.txt |
| [ispip.clang.cn](https://ispip.clang.cn) | all_cn.txt |
| [gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip) | 三大运营商 IP |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | CloudCN 云厂商 IP |

聚合方式与 [alecthw/mmdb_china_ip_list](https://github.com/alecthw/mmdb_china_ip_list) 一致，但输出 sing-box 原生格式而非 mmdb。

## 用法

### 方式一：远程自动更新（推荐）

```json
{
  "route": {
    "rule_set": [
      {
        "type": "remote",
        "tag": "geoip-cn",
        "format": "binary",
        "url": "https://raw.githubusercontent.com/PHCSJC/sing-geoip-cn/main/dist/geoip-cn.srs",
        "download_detour": "direct",
        "update_interval": "3d"
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

> `download_detour: "direct"` 让它走直连更新，不依赖代理。GitHub raw 在国内通常可直连；若不通可改成 `"proxy"`。

### 方式二：本地文件

```json
{
  "type": "local",
  "tag": "geoip-cn",
  "format": "binary",
  "path": "/data/adb/sing-box/geoip-cn.srs"
}
```

## 构建

```bash
pip install -r requirements.txt   # 无第三方依赖，仅标准库
python3 build.py                  # 下载并聚合，生成 dist/geoip-cn.json
sing-box rule-set compile cache/rule-set-src.json -o dist/geoip-cn.srs
```

GitHub Actions 每周一、周四 03:00 UTC 自动构建并提交。

## 注意

- **仅 IPv4**。如需 IPv6 请自行修改 `build.py` 中的过滤条件。
- 收录口径是"中国实体持有的 IP"，包含阿里云、腾讯云等厂商的**海外节点**（物理位置在美国、新加坡、德国等）。这些 IP 会走直连。
- 收录了 Cloudflare 的 `104.28.0.0/16` 等段（国内有节点），该段内同时存在需要代理的站点，可能被误判为直连。

## License

数据来自上述公开项目，遵循各自许可证。本仓库脚本为 MIT。
