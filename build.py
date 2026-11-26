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

Clang.CN trust filter
---------------------
Clang.CN collects by BGP AS registration country, so it also contains IP
space that is *registered* to Chinese entities but physically located
abroad (Hong Kong / Singapore / US datacenters), plus space registered to
"geo-faking" providers such as Malakmadze Web LLC (Georgia) that declare
themselves as CN.

Verified samples that Clang.CN wrongly lists as China:
  162.222.90.0/24  GE  Malakmadze Web LLC
  5.255.61.0/24    GE  Malakmadze Web LLC
  31.222.234.0/24  US  Malakmadze Web LLC
  77.216.50.0/23   SE  Tele2 Sverige AB
  79.175.67.0/24   ID  PT. INDUSTRI KREATIF DIGITAL
  94.118.188.0/23  SG  Datawave Global LLC
  ... and 17 more

Including these makes foreign sites resolve as "domestic" and therefore
bypass the proxy. This broke ip111.cn's overseas probe: us.ip111.cn
resolves to 162.222.90.70 and was routed direct, showing the real ISP IP
instead of the proxy IP.

The other four sources use actual geolocation and do not have this
problem, so a segment is dropped when Clang.CN is the *only* source that
lists it. Measured cost: 171k addresses out of 357M (0.048%).

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

# (cache filename, format, url, trust_level)
#   "trusted"    : geolocation-based source, always accepted
#   "clang"      : BGP-AS based source, only accepted when corroborated
SOURCES = [
    ("china_ip_list.txt", "plain",
     "https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt",
     "trusted"),
    ("chunzhen_cn.txt", "plain",
     "https://raw.githubusercontent.com/metowolf/iplist/master/data/special/china.txt",
     "trusted"),
    ("clang_cn.txt", "plain",
     "https://ispip.clang.cn/all_cn.txt",
     "clang"),
    ("china_operator.txt", "plain",
     "https://raw.githubusercontent.com/gaoyifan/china-operator-ip/ip-lists/china.txt",
     "trusted"),
    ("cloud_cn.list", "clash",
     "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash/Cloud/CloudCN/CloudCN.list",
     "trusted"),
]

UA = {"User-Agent": "sing-geoip-cn-builder/1.1 (+https://github.com/PHCSJC/sing-geoip-cn)"}
CACHE = "cache"
DIST = "dist"


def log(msg):
    print(msg, flush=True)


def fetch(url, dest, attempts=3):
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
    nets = []
    bad = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if kind == "clash":
                if s.startswith("IP-CIDR,"):
                    s = s[len("IP-CIDR,"):].split(",")[0].strip()
                else:
                    continue
            try:
                net = ipaddress.ip_network(s, strict=False)
            except ValueError:
                bad += 1
                continue
            if net.version != 4:
                continue
            nets.append(net)
    if bad:
        log("  note: %d unparseable lines in %s" % (bad, os.path.basename(path)))
    return nets


def to_ranges(nets):
    """Collapse networks into a sorted list of inclusive integer ranges."""
    rs = sorted((int(n.network_address), int(n.broadcast_address)) for n in nets)
    merged = []
    for s, e in rs:
        if merged and s <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def subtract(ranges_a, ranges_b):
    """Return the parts of ranges_a not covered by ranges_b."""
    out = []
    for s, e in ranges_a:
        cur = s
        for bs, be in ranges_b:
            if be < cur:
                continue
            if bs > e:
                break
            if bs > cur:
                out.append((cur, min(bs - 1, e)))
            cur = max(cur, be + 1)
            if cur > e:
                break
        if cur <= e:
            out.append((cur, e))
    return out


def ranges_to_networks(ranges):
    """Expand integer ranges back into minimal CIDR networks."""
    nets = []
    for s, e in ranges:
        nets.extend(ipaddress.summarize_address_range(
            ipaddress.IPv4Address(s), ipaddress.IPv4Address(e)))
    return list(ipaddress.collapse_addresses(nets))


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    trusted_nets = []
    clang_nets = []
    failed = []

    log("== downloading sources ==")
    for name, kind, url, trust in SOURCES:
        path = os.path.join(CACHE, name)
        ok = fetch(url, path)
        if not ok:
            if os.path.exists(path):
                log("  -> using previously cached copy")
            else:
                failed.append(name)
                continue
        nets = parse(path, kind)
        log("  parsed  %-22s %5d IPv4 networks [%s]" % (name, len(nets), trust))
        if trust == "clang":
            clang_nets.extend(nets)
        else:
            trusted_nets.extend(nets)

    if not trusted_nets and not clang_nets:
        log("ERROR: no networks parsed at all")
        return 1
    if failed:
        log("WARN: %d source(s) unavailable: %s" % (len(failed), ", ".join(failed)))

    log("")
    log("== applying Clang.CN trust filter ==")
    if clang_nets and trusted_nets:
        r_trusted = to_ranges(trusted_nets)
        r_clang = to_ranges(clang_nets)
        clang_only = subtract(r_clang, r_trusted)

        kept_clang = subtract(r_clang, clang_only)
        clang_kept = ranges_to_networks(kept_clang)
        clang_dropped = ranges_to_networks(clang_only)

        dropped_addrs = sum(n.num_addresses for n in clang_dropped)
        log("  clang.cn entries          : %d" % len(clang_nets))
        log("  clang.cn kept (corroborated): %d networks" % len(clang_kept))
        log("  clang.cn dropped (only src) : %d networks / %d addresses"
            % (len(clang_dropped), dropped_addrs))
        clang_nets = clang_kept
    else:
        log("  skipped (clang or trusted source unavailable)")

    log("")
    log("== merging ==")
    all_nets = trusted_nets + clang_nets
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
