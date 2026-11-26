#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build geoip-cn rule-set for sing-box (IPv4 only).

Aggregates the same five public China-IP sources that
alecthw/mmdb_china_ip_list currently uses, then compiles the result into
sing-box native binary rule-set format (.srs).

Sources (IPv4 only, IPv6 variants intentionally skipped):
  1. 17mon/china_ip_list            china_ip_list.txt
  2. metowolf/iplist (纯真 CN)       special/china.txt
  3. ispip.clang.cn (Clang.CN)      all_cn.txt
  4. gaoyifan/china-operator-ip      ip-lists/china.txt
  5. blackmatrix7/ios_rule_script    Cloud/CloudCN/CloudCN.list

Outputs:
  dist/geoip-cn.srs    sing-box binary rule-set
  dist/geoip-cn.txt    plain CIDR list, one per line
  dist/version         build timestamp (UTC, YYYYMMDDHHMM)
"""

import ipaddress
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

SOURCES = [
    # (cache filename, format, url)
    ("china_ip_list.txt", "plain",
     "https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt"),
    ("chunzhen_cn.txt", "plain",
     "https://raw.githubusercontent.com/metowolf/iplist/master/data/special/china.txt"),
    ("clang_cn.txt", "plain",
     "https://ispip.clang.cn/all_cn.txt"),
    ("china_operator.txt", "plain",
     "https://raw.githubusercontent.com/gaoyifan/china-operator-ip/ip-lists/china.txt"),
    ("cloud_cn.list", "clash",
     "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash/Cloud/CloudCN/CloudCN.list"),
]

UA = {"User-Agent": "sing-geoip-cn-builder/1.0 (+https://github.com/PHCSJC/sing-geoip-cn)"}
CACHE = "cache"
DIST = "dist"


def log(msg):
    print(msg, flush=True)


def fetch(url, dest, attempts=3):
    """Download url to dest. Returns True on success."""
    last = None
    for i in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            if not data:
                raise ValueError("empty response")
            with open(dest, "wb") as f:
                f.write(data)
            log("  fetched %-22s %9d bytes" % (os.path.basename(dest), len(data)))
            return True
        except Exception as e:
            last = e
            log("  retry %d/%d %s: %s" % (i, attempts, os.path.basename(dest), e))
    log("  FAILED  %-22s %s" % (os.path.basename(dest), last))
    return False


def parse(path, kind):
    """Parse a source file into a list of IPv4 networks."""
    nets = []
    bad = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if kind == "clash":
                # e.g. "IP-CIDR,1.116.116.0/22,no-resolve"
                if s.startswith("IP-CIDR,"):
                    s = s[len("IP-CIDR,"):].split(",")[0].strip()
                else:
                    # IP-CIDR6, DOMAIN-*, PROCESS-*, etc. are skipped
                    continue
            try:
                net = ipaddress.ip_network(s, strict=False)
            except ValueError:
                bad += 1
                continue
            if net.version != 4:
                continue          # IPv4 only
            nets.append(net)
    if bad:
        log("  note: %d unparseable lines in %s" % (bad, os.path.basename(path)))
    return nets


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    all_nets = []
    failed = []

    log("== downloading sources ==")
    for name, kind, url in SOURCES:
        path = os.path.join(CACHE, name)
        ok = fetch(url, path)
        if not ok:
            if os.path.exists(path):
                log("  -> using previously cached copy")
            else:
                failed.append(name)
                continue
        nets = parse(path, kind)
        log("  parsed  %-22s %5d IPv4 networks" % (name, len(nets)))
        all_nets.extend(nets)

    if not all_nets:
        log("ERROR: no networks parsed at all")
        return 1
    if failed:
        log("WARN: %d source(s) unavailable: %s" % (len(failed), ", ".join(failed)))

    log("")
    log("== merging ==")
    merged = list(ipaddress.collapse_addresses(all_nets))
    merged.sort(key=lambda n: (int(n.network_address), n.prefixlen))

    total = sum(n.num_addresses for n in merged)
    log("  raw entries     : %d" % len(all_nets))
    log("  after collapse  : %d" % len(merged))
    log("  address coverage: %d (%.2f 亿)" % (total, total / 1e8))

    cidrs = [str(n) for n in merged]

    txt_path = os.path.join(DIST, "geoip-cn.txt")
    with open(txt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(cidrs) + "\n")
    log("  wrote %s" % txt_path)

    src = {"version": 3, "rules": [{"ip_cidr": cidrs}]}
    src_path = os.path.join(CACHE, "rule-set-src.json")
    with open(src_path, "w", encoding="utf-8") as f:
        json.dump(src, f, ensure_ascii=False, separators=(",", ":"))
    log("  wrote %s" % src_path)

    ver = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    with open(os.path.join(DIST, "version"), "w", encoding="utf-8", newline="\n") as f:
        f.write(ver + "\n")
    log("  version: %s" % ver)

    return 0


if __name__ == "__main__":
    sys.exit(main())
