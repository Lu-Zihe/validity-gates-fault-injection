# -*- coding: utf-8 -*-
"""三种子合并分析：每种子两臂的摔倒率差、区间、以及合并估计。

用法：python seed_analysis.py <data_dir>
data_dir 内含：
  r1r_aware.json / r1r_broken.json     种子 42
  seed7_aware.json / seed7_broken.json
  seed2026_aware.json / seed2026_broken.json
"""
import json
import math
import os
import sys

SEEDS = [("42", "r1r"), ("7", "seed7"), ("2026", "seed2026")]


def load(d, prefix, arm):
    p = os.path.join(d, "%s_%s.json" % (prefix, arm))
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def ci(k, n):
    p = k / n
    se = math.sqrt(p * (1 - p) / n)
    return p, se, p - 1.96 * se, p + 1.96 * se


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    rows = []
    for name, prefix in SEEDS:
        a, b = load(d, prefix, "aware"), load(d, prefix, "broken")
        if not a or not b:
            print("缺数据：seed", name)
            continue
        pa, sea, la, ha = ci(a["n_falls"], a["n_episodes"])
        pb, seb, lb, hb = ci(b["n_falls"], b["n_episodes"])
        diff = pb - pa
        sed = math.sqrt(sea ** 2 + seb ** 2)
        z = diff / sed
        rows.append(dict(seed=name, na=a["n_episodes"], ka=a["n_falls"], pa=pa,
                         nb=b["n_episodes"], kb=b["n_falls"], pb=pb,
                         diff=diff, lo=diff - 1.96 * sed, hi=diff + 1.96 * sed,
                         z=z, rmst_a=a["rmst_steps"], rmst_b=b["rmst_steps"]))

    if not rows:
        print("无可用数据")
        return

    print("%-6s %-18s %-18s %-22s %-7s" % ("种子", "注入落地", "静默失效", "差值 [95%CI] pp", "z"))
    for r in rows:
        print("%-6s %5.1f%% (%d/%d)   %5.1f%% (%d/%d)   %+5.1f [%+5.1f, %+5.1f]   %5.2f" % (
            r["seed"], r["pa"] * 100, r["ka"], r["na"],
            r["pb"] * 100, r["kb"], r["nb"],
            r["diff"] * 100, r["lo"] * 100, r["hi"] * 100, r["z"]))

    diffs = [r["diff"] for r in rows]
    mean = sum(diffs) / len(diffs)
    print("\n差值均值 %.1f pp，极差 %.1f–%.1f pp" % (
        mean * 100, min(diffs) * 100, max(diffs) * 100))
    print("RMST 差（步）: " + ", ".join(
        "%s: %+.0f" % (r["seed"], r["rmst_b"] - r["rmst_a"]) for r in rows))

    # 固定效应合并（仅作参考，不替代随机效应）
    wsum = sum(1 / (r["lo"] and ((r["hi"] - r["lo"]) / 3.92) ** 2) for r in rows)
    est = sum(r["diff"] / ((r["hi"] - r["lo"]) / 3.92) ** 2 for r in rows) / wsum
    se = math.sqrt(1 / wsum)
    print("固定效应合并估计 %.1f pp [%.1f, %.1f]（异质性未校正，仅供参考）" % (
        est * 100, (est - 1.96 * se) * 100, (est + 1.96 * se) * 100))


if __name__ == "__main__":
    main()
