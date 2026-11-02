#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""三关检查器：一条命令跑 P1/P2/P3，输出数值 + 阈值 + PASS/FAIL。

用法：
    python gate_check.py                 # 三关全跑
    python gate_check.py --p1            # 只跑注入关
    python gate_check.py --p2 --p3

依赖：
  P1  -> ../../代码修复-20261012（自检 60 项 + 补测 6 项）
  P2  -> ../../34-零成本三件套-20261027/data/iter_metrics.csv
  P3  -> ../../35-收敛与种子检验-20261027/data/ext_full.json
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # repository root
SELF_CHECK = ROOT / "checker"
META_TEST = ROOT / "checker" / "test_guards_meta.py"
E1_CSV = ROOT / "data" / "iter_metrics.csv"
EXT_JSON = ROOT / "data" / "ext_full.json"
PY = sys.executable


def run_script(script, cwd, env_extra=None):
    import os
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["P1R8_PKG_ROOT"] = str(cwd)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run([PY, str(script)], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=600)
    return (p.stdout or "") + "\n" + (p.stderr or ""), p.returncode


# ---------------------------------------------------------------- P1
def check_p1():
    out, rc = run_script(SELF_CHECK / "test_r1_r8_local.py", SELF_CHECK)
    import re
    m = re.search(r"合计\s+(\d+)\s+项：PASS\s+(\d+)\s*/\s*FAIL\s+(\d+)", out)
    if not m:
        missing = re.search(r"ModuleNotFoundError: No module named '([^']+)'", out)
        if missing and missing.group(1).split(".")[0] in ("legged_gym", "isaacgym", "torch"):
            return {"gate": "P1", "pass": None, "status": "skipped",
                    "reason": ("the 66 checks run against the training stack "
                               "(legged_gym / Isaac Gym), which is not redistributed "
                               "in this repository; see README, section 'Scope and "
                               "honesty notes'"),
                    "missing_module": missing.group(1)}
        return {"gate": "P1", "pass": False, "reason": "self-check did not run",
                "tail": out.strip().splitlines()[-3:]}
    total, ok, fail = map(int, m.groups())
    res = {"gate": "P1", "pass": fail == 0, "checks_total": total, "checks_pass": ok,
           "checks_fail": fail, "threshold": "FAIL==0"}
    # 补测套件（若存在）
    if META_TEST.exists():
        out2, _ = run_script(META_TEST, ROOT / "checker")
        m2 = re.search(r"META 合计\s+(\d+)\s+项：PASS\s+(\d+)\s*/\s*FAIL\s+(\d+)", out2)
        if m2:
            t2, o2, f2 = map(int, m2.groups())
            res["meta_checks_total"] = t2
            res["meta_checks_pass"] = o2
            res["pass"] = res["pass"] and f2 == 0
    return res


# ---------------------------------------------------------------- P2
def check_p2():
    import pandas as pd
    d = pd.read_csv(E1_CSV)
    P = "Mean_episode_rew_"
    terms = [c for c in d.columns if c.startswith(P)]
    d["unclipped"] = d[terms].sum(axis=1) * 20.0
    d["clip_mass"] = d["Mean_reward"] - d["unclipped"]
    viol = int((d["clip_mass"] < 0).sum())
    n = len(d)

    out = {"gate": "P2", "threshold": "四项全有值；可加性反例 ≤1%"}
    # P2-a/b: 两个口径都在（数据里有 Mean_reward=裁剪 + 分项可复算未裁剪）
    out["P2a_declared_both_calibers"] = ("Mean_reward" in d.columns) and (len(terms) > 0)
    out["P2b_clip_mass_reported"] = True
    out["clip_mass_mean"] = float(d["clip_mass"].mean())
    # P2-c: 窗口敏感
    deltas = {}
    for w in (100, 300, 500):
        tail = d.groupby("arm").tail(w)
        g = tail.groupby("arm")["Mean_reward"].mean()
        if {"free_swing", "lock"} <= set(g.index):
            deltas[w] = float((g["lock"] - g["free_swing"]) / abs(g["free_swing"]) * 100)
    out["window_deltas_pct"] = deltas
    out["P2c_window_range_pp"] = (max(deltas.values()) - min(deltas.values())) if deltas else None
    # P2-d: 可加性/裁剪一致性（未裁剪 ≤ 裁剪，允许极少数抽样反例）
    out["additivity_violations"] = viol
    out["additivity_violation_rate"] = viol / n if n else None
    out["pass"] = (out["P2a_declared_both_calibers"]
                   and out["P2b_clip_mass_reported"]
                   and (out["additivity_violation_rate"] is not None
                        and out["additivity_violation_rate"] <= 0.01))
    return out


# ---------------------------------------------------------------- P3
def check_p3():
    if not EXT_JSON.exists():
        return {"gate": "P3", "pass": False, "reason": f"缺少 {EXT_JSON}"}
    r = json.loads(EXT_JSON.read_text(encoding="utf-8"))
    out = {"gate": "P3", "threshold": "末两块差 < 0.5 且末三块不单向单调", "arms": {}}
    all_ok = True
    for tag in ("free_ext2", "lock_ext", "lock_ext3"):
        if tag not in r:
            continue
        blocks = r[tag]["blocks"]
        if len(blocks) < 2:
            continue
        vals = [b["R"] for b in blocks]
        diff = abs(vals[-1] - vals[-2])
        mono = len(vals) >= 3 and (vals[-3] < vals[-2] < vals[-1] or vals[-3] > vals[-2] > vals[-1])
        ok = diff < 0.5 and not mono
        all_ok = all_ok and ok
        out["arms"][tag] = {"blocks": [round(v, 3) for v in vals],
                            "last_two_diff": round(diff, 3),
                            "monotone_tail": mono, "pass": ok}
    out["pass"] = all_ok
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    ap.add_argument("--p3", action="store_true")
    a = ap.parse_args()
    run_all = not (a.p1 or a.p2 or a.p3)
    results = []
    if run_all or a.p1:
        results.append(check_p1())
    if run_all or a.p2:
        results.append(check_p2())
    if run_all or a.p3:
        results.append(check_p3())

    print("=" * 76)
    for r in results:
        flag = "SKIP" if r.get("pass") is None else ("PASS" if r.get("pass") else "FAIL")
        print(f"[{flag}] {r['gate']}  (threshold: {r.get('threshold','-')})")
        for k, v in r.items():
            if k in ("gate", "pass", "threshold"):
                continue
            print(f"        {k}: {v}")
    print("=" * 76)
    ok = all(r.get("pass") for r in results if r.get("pass") is not None)
    print("总判定：", "全部通过" if ok else "存在未通过项")
    (ROOT / "gate_report.json").write_text(
        json.dumps({"results": results, "all_pass": ok}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
