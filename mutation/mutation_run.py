#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""变异测试（mutation score）：验证 60 项自检**真的能抓错**。

原理：自检全绿只证明"当前代码通过"，不证明"代码错了会被抓住"。
做法：把注入链路的关键语句逐个改坏（语义保持真实缺陷族），重跑自检：
  - 自检失败 ⇒ 该变异被"杀死"（killed）——检查有效；
  - 自检仍全绿 ⇒ 该变异"存活"（survived）——检查有盲区。

用法：
    python mutation_run.py            # 全跑
    python mutation_run.py --only M01,M07
    python mutation_run.py --list

输出：mutation_results.csv + mutation_report.md（含 Wilson CI）
依赖：本机 D:\\py\\python（torch CPU）；不需要 GPU。
"""
import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]              # 39-mutation-20261028
SRC = ROOT.parent / "代码修复-20261012"                  # 被测源树（只读，不修改）
WORK = ROOT / "_work"
PY = r"D:\py\python\python.exe"
TEST = "tests/test_r1_r8_local.py"

# ---------------------------------------------------------------- 变异体
# 每条：id / file / op / old / new / why
MUTANTS = [
    # ===== fault_detector.py::reset_envs（概率分配）=====
    dict(id="M01", file="legged_gym/utils/fault_detector.py",
         op="drop_degrade_prob",
         old="        p2 = p1 + self.fault_prob_weakened",
         new="        p2 = p1",
         why="丢掉 degrade 概率：配置上写了但永远抽不到（D-概率归一化丢失）"),
    dict(id="M02", file="legged_gym/utils/fault_detector.py",
         op="drop_lock_prob",
         old="        p3 = p2 + self.fault_prob_lock",
         new="        p3 = p2",
         why="丢掉 lock 概率：lock 臂退化成空跑"),
    dict(id="M03", file="legged_gym/utils/fault_detector.py",
         op="boundary_le",
         old="        state[r < p1] = MODE_IDS['free_swing']",
         new="        state[r <= p1] = MODE_IDS['free_swing']",
         why="边界从 < 改 <=：零概率时仍注入（空注入的典型写法）"),
    dict(id="M04", file="legged_gym/utils/fault_detector.py",
         op="gap_at_boundary",
         old="        state[(r >= p1) & (r < p2)] = MODE_IDS['degrade']",
         new="        state[(r > p1) & (r < p2)] = MODE_IDS['degrade']",
         why="degrade 区间左端点漏掉：边界样本静默丢失"),
    dict(id="M05", file="legged_gym/utils/fault_detector.py",
         op="stale_state",
         old="        self.fault_states[ids] = 0",
         new="        pass  # mutated: 不清零",
         why="reset 时不清空旧状态：上一回合的故障残留（D-状态泄漏）"),
    dict(id="M06", file="legged_gym/utils/fault_detector.py",
         op="lose_mode",
         old="            self.fault_states[ids[has_fault], fault_leg[has_fault]] = state[has_fault]",
         new="            self.fault_states[ids[has_fault], fault_leg[has_fault]] = 1",
         why="不写真实形态，只写 1：所有故障退化成同一种"),
    dict(id="M07", file="legged_gym/utils/fault_detector.py",
         op="skip_refresh",
         old="        self._refresh_lock_flag()                               # 1 次同步",
         new="        pass  # mutated: 不刷新 lock 标记",
         why="改完状态表不刷新 lock 标志：on_step 按旧标记早退（D-契约违反）"),

    # ===== fault_detector.py::apply（物理量落地）=====
    dict(id="M08", file="legged_gym/utils/fault_detector.py",
         op="free_swing_noop",
         old="                    env.torque_limits[sub.unsqueeze(1), cols] = 0.0",
         new="                    env.torque_limits[sub.unsqueeze(1), cols] = nominal_t[sub.unsqueeze(1), cols]",
         why="free_swing 力矩不置零：标记为故障但物理没变（最经典的静默失效）"),
    dict(id="M09", file="legged_gym/utils/fault_detector.py",
         op="degrade_scale_ignored",
         old="                        nominal_t[sub.unsqueeze(1), cols] * self.degrade_severity",
         new="                        nominal_t[sub.unsqueeze(1), cols] * 1.0",
         why="degrade 忽略 k 系数：衰减形态退化成标称"),
    dict(id="M10", file="legged_gym/utils/fault_detector.py",
         op="lock_gain_ignored",
         old="                    env.p_gains[sub.unsqueeze(1), cols] = \\\n                        env.nominal_p_gains[sub.unsqueeze(1), cols] * self.lock_stiffness_scale",
         new="                    env.p_gains[sub.unsqueeze(1), cols] = \\\n                        env.nominal_p_gains[sub.unsqueeze(1), cols] * 1.0",
         why="lock 不放大 PD 增益：硬约束形态没有刚度变化"),
    dict(id="M11", file="legged_gym/utils/fault_detector.py",
         op="disable_strict_checks",
         old="                if self.strict_checks:",
         new="                if False:  # mutated: 关闭逐腿核对",
         why="关掉逐腿生效核对：检查器本身被绕过"),
    dict(id="M12", file="legged_gym/utils/fault_detector.py",
         op="god_view_wrong",
         old="        env.fault_obs_buf[env_ids, :] = torch.where(\n            (self.fault_states[env_ids] > 0),\n            torch.ones_like(self.fault_states[env_ids], dtype=env.fault_obs_buf.dtype),\n            torch.zeros_like(self.fault_states[env_ids], dtype=env.fault_obs_buf.dtype))",
         new="        env.fault_obs_buf[env_ids, :] = torch.zeros_like(self.fault_states[env_ids], dtype=env.fault_obs_buf.dtype)",
         why="上帝视角全零：策略看不到故障（观测与物理不一致）"),

    # ===== silent_failure_guards.py（检查器自身）=====
    dict(id="M13", file="legged_gym/utils/silent_failure_guards.py",
         op="caliber_tolerance_loose",
         old="    if abs(total - float(declared_total)) > 1e-9:",
         new="    if abs(total - float(declared_total)) > 1.0:",
         why="总注入率容差放到 1.0：配置与声称值再不一致也不报（D6 失效）"),
    dict(id="M14", file="legged_gym/utils/silent_failure_guards.py",
         op="effectiveness_always_pass",
         old="    n_eff = int(changed.sum().item())",
         new="    n_eff = n_req  # mutated: 永远宣告生效",
         why="生效核对恒等于请求数：注入没落地也报成功（D3 失效）"),
    dict(id="M15", file="legged_gym/utils/silent_failure_guards.py",
         op="terrain_ratio_zero",
         old="def assert_terrain_not_degenerate(terrain, generation, min_row_amplitude_ratio=1.05):",
         new="def assert_terrain_not_degenerate(terrain, generation, min_row_amplitude_ratio=0.0):",
         why="地形退化阈值降为 0：退化地形不再算退化（D1 失效）"),
    dict(id="M16", file="legged_gym/utils/silent_failure_guards.py",
         op="energy_tolerance_huge",
         old="    if abs(float(energy_reference) - float(expected_reference)) > 1e-9:",
         new="    if abs(float(energy_reference) - float(expected_reference)) > 1e9:",
         why="能耗基准容差放到 1e9：口径漂移不再报（D5 失效）"),

    # ===== a1_rescue_phase3_env.py::reset_idx（调用链）=====
    dict(id="M17", file="legged_gym/envs/a1_rescue/a1_rescue_phase3_env.py",
         op="no_apply",
         old="            self.fault_injector.apply(self, env_ids)",
         new="            pass  # mutated: 只标记不落地",
         why="标记了故障但不下沉物理量（最经典的静默失效）"),
    dict(id="M18", file="legged_gym/envs/a1_rescue/a1_rescue_phase3_env.py",
         op="no_reset_envs",
         old="            self.fault_injector.reset_envs(env_ids)",
         new="            pass  # mutated: 不重新抽故障",
         why="不重新抽样：沿用上一回合的故障状态"),
    dict(id="M19", file="legged_gym/envs/a1_rescue/a1_rescue_phase3_env.py",
         op="skip_verify",
         old="        if self.fault_enabled and self.strict_checks:",
         new="        if False:  # mutated: 跳过 reset 后自检",
         why="reset 后不跑自检：标记-物理不一致无人发现"),
    dict(id="M20", file="legged_gym/envs/a1_rescue/a1_rescue_phase3_env.py",
         op="no_dr",
         old="            self.domain_randomization.apply_runtime(self, env_ids)",
         new="            pass  # mutated: 不做域随机化",
         why="DR 不落地：环境分布与声称不符（D2 类）"),

    # ===== train.py（协议指纹）=====
    dict(id="M21", file="legged_gym/scripts/train.py",
         op="run_meta_seed_none",
         old='            "seed_effective": effective_seed,',
         new='            "seed_effective": None,',
         why="协议指纹里的种子写成 None：事后无法核种子"),
]


def prepare_work():
    """把源树复制到 _work（缺省树），后续每个变异体都从它恢复。"""
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(SRC, WORK)
    # 把补测脚本放进被测树的 tests/（与原自检并列）
    shutil.copy2(ROOT / "scripts" / "test_guards_meta.py", WORK / "tests" / "test_guards_meta.py")
    # 清掉上一轮产物
    for p in WORK.glob("tests/local_verification_report.json"):
        p.unlink()


def apply_mutation(m):
    """返回 'applied' / 'not_found' / 'ambiguous'"""
    path = WORK / m["file"]
    text = path.read_text(encoding="utf-8")
    n = text.count(m["old"])
    if n == 0:
        return "not_found"
    if n > 1:
        return "ambiguous"
    path.write_text(text.replace(m["old"], m["new"], 1), encoding="utf-8")
    return "applied"


def _run_one(script):
    import os
    env = {"PYTHONIOENCODING": "utf-8", "P1R8_PKG_ROOT": str(WORK)}
    env.update({k: v for k, v in os.environ.items() if k not in env})
    p = subprocess.run([PY, script], cwd=str(WORK), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=600)
    out = (p.stdout or "") + "\n" + (p.stderr or "")
    if "META" in script:
        m = re.search(r"META 合计\s+(\d+)\s+项：PASS\s+(\d+)\s*/\s*FAIL\s+(\d+)", out)
    else:
        m = re.search(r"合计\s+(\d+)\s+项：PASS\s+(\d+)\s*/\s*FAIL\s+(\d+)", out)
    if m:
        total, npass, nfail = map(int, m.groups())
    else:
        total, npass, nfail = -1, -1, -1
    return {"exit": p.returncode, "total": total, "pass": npass, "fail": nfail,
            "out": out}


def run_check():
    """跑原自检 + 补测；任一脚本崩溃或失败即视为该变异体被抓。"""
    parts = [_run_one("tests/test_r1_r8_local.py"), _run_one("tests/test_guards_meta.py")]
    crashed = [x for x in parts if x["total"] == -1]
    if crashed:
        # 崩溃（异常/导入失败）也算被抓，但必须标注，不能静默当成"存活"
        tail = "\n".join(x["out"][-600:] for x in crashed)
        return {"exit": 1, "total": -1, "pass": -1, "fail": -1, "fails": [],
                "crash": (tail.strip().splitlines()[-1] if tail.strip() else "crash")[:200],
                "raw_tail": tail}
    total = sum(x["total"] for x in parts)
    npass = sum(x["pass"] for x in parts)
    nfail = sum(max(x["fail"], 0) for x in parts)
    fails = []
    for x in parts:
        for line in x["out"].splitlines():
            if "[FAIL]" in line:
                fails.append((line.split("[FAIL]")[1].strip()[:60], ""))
    return {"exit": max(x["exit"] for x in parts), "total": total, "pass": npass,
            "fail": nfail, "fails": fails, "crash": "",
            "raw_tail": "\n".join(x["out"][-600:] for x in parts)}


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (p, (c - r) / d, (c + r) / d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    if args.list:
        for m in MUTANTS:
            print(f'{m["id"]}  {m["op"]:24s} {m["why"]}')
        return
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    todo = [m for m in MUTANTS if not only or m["id"] in only]

    prepare_work()
    base = run_check()
    print(f"[baseline] total={base['total']} pass={base['pass']} fail={base['fail']} exit={base['exit']}")
    if base["total"] == -1:
        print("[FATAL] 基线自检没跑起来：", base["crash"])
        for l in base["raw_tail"].splitlines()[-15:]:
            print("   ", l)
        sys.exit(2)

    rows = []
    for m in todo:
        shutil.copy2(SRC / m["file"], WORK / m["file"])     # 恢复
        st = apply_mutation(m)
        if st != "applied":
            rows.append({**{k: m[k] for k in ("id", "file", "op", "why")},
                         "applied": st, "verdict": "n/a",
                         "exit": "", "fails": "", "crash": ""})
            print(f"  {m['id']} {m['op']:24s} {st}")
            continue
        r = run_check()
        if r["total"] == -1:
            verdict = "killed(crash)"
            (ROOT / f"crash_{m['id']}.log").write_text(r["raw_tail"], encoding="utf-8")
        elif r["fail"] > 0:
            verdict = "killed"
        else:
            verdict = "SURVIVED"
        rows.append({**{k: m[k] for k in ("id", "file", "op", "why")},
                     "applied": st, "verdict": verdict, "exit": r["exit"],
                     "fails": ";".join(f"{a} {b[:40]}" for a, b in r["fails"][:4]),
                     "crash": r["crash"][:120]})
        print(f"  {m['id']} {m['op']:24s} -> {verdict:12s} fail={r['fail']} "
              f"{('| ' + r['crash'][:60]) if r['crash'] else ''}")
        shutil.copy2(SRC / m["file"], WORK / m["file"])     # 立即恢复

    # 统计
    valid = [r for r in rows if r["verdict"] in ("killed", "killed(crash)", "SURVIVED")]
    killed = [r for r in valid if r["verdict"].startswith("killed")]
    p, lo, hi = wilson(len(killed), len(valid))
    csv_path = ROOT / "mutation_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summary = {"n_valid": len(valid), "n_killed": len(killed),
               "survived": [r["id"] for r in valid if r["verdict"] == "SURVIVED"],
               "score": p, "ci95": [lo, hi], "baseline": base["pass"]}
    (ROOT / "mutation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
    print(f"\n=== mutation score = {len(killed)}/{len(valid)} = {p*100:.1f}% "
          f"(95% CI {lo*100:.1f}–{hi*100:.1f}%) ===")
    if summary["survived"]:
        print("存活（检查盲区）：", ", ".join(summary["survived"]))
    print("->", csv_path)


if __name__ == "__main__":
    main()
