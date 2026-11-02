#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verify_numbers.py —— 只用标准库，把论文里引用的关键数字从随包数据里重算一遍。

为什么有这个文件：论文/README 里出现的每个数字都必须能指到磁盘上的一个文件。
本脚本不调用任何模型、不联网、不依赖 numpy/pandas/torch（Python 3.8+ 可跑）。

用法::

    python verify_numbers.py            # 全部重算 + 一致性断言
    python verify_numbers.py -v         # 额外打印明细

退出码：0 = 所有一致性断言通过；1 = 有断言失败（会打印失败的断言）。
注意：本脚本核的是**数字与文件的一致性**，不是重跑实验。重跑见 USAGE.md。
"""
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE / "audit"
MUT = HERE / "mutation"
FIGS = HERE / "figs" / "data"
DATA = HERE / "data"

VERBOSE = "-v" in sys.argv
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    flag = "PASS" if cond else "FAIL"
    print(f"  [{flag}] {name}{('  ' + detail) if detail else ''}")
    return bool(cond)


def pct(a, b):
    return f"{a}/{b} = {a / b * 100:.1f}%"


# ---------------------------------------------------------------- 1. 仓库审计
def sec_audit():
    print("[1] 仓库审计（21 仓库，C1/C2/C3）")
    rows = list(csv.DictReader((AUDIT / "audit_21repos.csv").open(encoding="utf-8")))
    check("audit_21repos.csv 行数 = 21", len(rows) == 21, f"实际 {len(rows)}")

    app = [r for r in rows if r["C1_applicable"] == "True"]
    mis = [r for r in app if r["C1"].startswith("MISROUTED")]
    check("C1 判据适用（legged_gym 式）仓库数 = 5", len(app) == 5,
          "、".join(r["repo"] for r in app))
    check("其中 MISROUTED = 2", len(mis) == 2,
          "、".join(r["repo"] for r in mis))

    idiom = {}
    for r in rows:
        idiom[r["idiom"]] = idiom.get(r["idiom"], 0) + 1
    if VERBOSE:
        print("        idiom 分布:", idiom)
    check("legged_gym-like 血统仓库数 = 5", idiom.get("legged_gym-like") == 5, str(idiom))

    # 首轮 9 仓库：legged_gym 血统 5 个里 4 个误路由（报告正文表格）
    rep9 = (AUDIT / "reports" / "报告-首轮9仓库-20261028.md").read_text(encoding="utf-8")
    n_mis9 = len(re.findall(r"^\|\s*\w[\w.\-]*\s*\|\s*\d+\s*\|\s*\*\*MISROUTED\*\*", rep9, re.M))
    n_app9 = len(re.findall(r"\|\s*seed_applied", rep9, re.M)) + n_mis9
    check("首轮 9 仓库报告中 MISROUTED 行 = 4", n_mis9 == 4, f"实际 {n_mis9}")
    check("首轮 legged_gym 血统 5 个（4 误路由 + 1 已修）", n_app9 == 5, f"实际 {n_app9}")

    # 合并口径：6/10 = 首轮 4 + 新抓 2；5 + 5 = 10
    total_mis, total_app = n_mis9 + len(mis), n_app9 + len(app)
    check("合并口径 6/10", (total_mis, total_app) == (6, 10),
          f"{total_mis}/{total_app}")
    print(f"        => 6/10（{pct(6, 10)}）的来源：首轮 4/5 + 新抓 2/5；"
          f"注意 21 仓库 CSV 单独只给出 2/5")

    c3 = {}
    for r in rows:
        c3[r["C3"]] = c3.get(r["C3"], 0) + 1
    if VERBOSE:
        print("        C3 分布:", c3)
    # 唯一专门做故障注入的仓库：提及注入的文件 29 个、有核对的 0 个
    iit = [r for r in rows if r["repo"].startswith("iit-DLSLab/")]
    check("iit-DLSLab/fault-locomotion-isaaclab 在表中", len(iit) == 1)
    if iit:
        check("其 C3_inject_files = 29", iit[0]["C3_inject_files"] == "29",
              f"实际 {iit[0]['C3_inject_files']}")
        check("其 C3 判定 = no_audit_signal（29 文件 0 核对）",
              iit[0]["C3"] == "no_audit_signal", iit[0]["C3"])

    lines = [l for l in (AUDIT / "shas.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    check("shas.txt 记录 21 个 repo@sha", len(lines) == 21, f"实际 {len(lines)}")
    bad = [l for l in lines if not re.search(r"\b[0-9a-f]{40}$", l.strip())]
    check("shas.txt 每行都以 40 位 sha 结尾", not bad, f"异常 {len(bad)} 行")
    n_py = sum(int(r["n_py"]) for r in rows)
    print(f"        21 仓库 .py 文件合计 = {n_py}")
    return {"n_py": n_py}


# ---------------------------------------------------------------- 2. 变异测试
def sec_mutation():
    print("[2] 变异测试（mutation score）")
    rows = list(csv.DictReader((MUT / "mutation_results.csv").open(encoding="utf-8")))
    check("mutation_results.csv 行数 = 21", len(rows) == 21, f"实际 {len(rows)}")

    killed = [r for r in rows if r["verdict"].startswith("killed")]
    crash = [r for r in rows if r["verdict"] == "killed(crash)"]
    surv = [r for r in rows if r["verdict"] == "SURVIVED"]
    valid = killed + surv
    check("被捕获（killed + killed(crash)）= 19", len(killed) == 19, f"实际 {len(killed)}")
    check("其中以崩溃形式被抓（killed(crash)）= 4", len(crash) == 4,
          "、".join(r["id"] for r in crash))
    check("存活（SURVIVED）= 2", len(surv) == 2, "、".join(r["id"] for r in surv))
    check("有效变异体 = 21", len(valid) == 21, f"实际 {len(valid)}")
    score = len(killed) / len(valid)
    print(f"        => mutation score = {pct(len(killed), len(valid))}")

    s = json.loads((MUT / "mutation_summary.json").read_text(encoding="utf-8"))
    check("summary.n_valid = 21", s["n_valid"] == 21, str(s["n_valid"]))
    check("summary.n_killed = 19", s["n_killed"] == 19, str(s["n_killed"]))
    check("summary.survived = [M03, M04]",
          s["survived"] == ["M03", "M04"], str(s["survived"]))
    check("summary.score 与 CSV 重算一致（±1e-9）", abs(s["score"] - score) < 1e-9,
          f"json={s['score']:.6f} csv={score:.6f}")
    check("summary.baseline = 66（基线 60+6 全绿）", s["baseline"] == 66, str(s["baseline"]))
    lo, hi = s["ci95"]
    print(f"        95% CI（Wilson）= {lo * 100:.1f}–{hi * 100:.1f}%")
    return score


# ---------------------------------------------------------------- 3. 图数据
def _flatten_numbers(obj, out):
    """把任意 JSON 里出现的数字掏出来；不强绑 schema。"""
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_numbers(v, out)
    return out


def _all_lists(obj, out):
    """把所有数字列表掏出来（用于"某个图里有一组 [6,1,3]"这类判断）。"""
    if isinstance(obj, dict):
        for v in obj.values():
            _all_lists(v, out)
    elif isinstance(obj, list):
        if obj and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in obj):
            out.append(list(obj))
        else:
            for v in obj:
                _all_lists(v, out)
    return out


def sec_figs():
    """图数据是**可选**的：本包不发布图数据（图由论文流程单独维护，见 ../发布说明.md）。

    存在 figs/data/*.json 时才做"关键数字是否存在"的弱检查；不存在就明说跳过，
    **不当作通过**。严格的一致性由 sec_audit / sec_mutation / sec_gate_inputs 从 CSV/JSON 侧保证。
    """
    print("[3] 图数据（可选；本包默认不含）")
    if not FIGS.exists():
        print("        跳过：figs/data 不存在。")
        print("        76.9× 的源在 gates/三关定义与矩阵.md §2：配置 10% vs 实测 0.13%（n=77，"
              "精确二项 p=0.00286）。")
        return
    files = sorted(FIGS.glob("*.json"))
    if not files:
        print("        跳过：figs/data 里没有 json。")
        return
    check("figs/data 至少有 4 个 json", len(files) >= 4,
          f"{len(files)} 个: " + "、".join(f.name for f in files))
    pool, lists_by_file = [], {}
    for f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:                                   # 坏文件要报出来，不能静默
            check(f"{f.name} 可解析", False, f"{type(e).__name__}: {e}")
            continue
        pool += _flatten_numbers(doc, [])
        lists_by_file[f.name] = _all_lists(doc, [])

    for label, val in [("配置声称注入率 10.0", 10.0), ("实测（修复前）0.13", 0.13),
                       ("实测（修复后）8.94", 8.94), ("free 末两块差 0.587", 0.587),
                       ("lock 末两块差 0.251", 0.251)]:
        check(f"图数据含 {label}", val in pool,
              "" if val in pool else f"所有 fig json 里都没找到 {val}")

    ratio1 = 10.0 / 0.13
    check("由三值可复算 76.9×（配置/实测）", round(ratio1, 1) == 76.9, f"{ratio1:.2f}")

    check("某图含 [6, 1, 3]（误路由/正常/无法判定，合 10）",
          any(l == [6, 1, 3] for ls in lists_by_file.values() for l in ls),
          "这是 21 仓库里 C1 判据适用的分母 10")


# ---------------------------------------------------------------- 4. 三关输入
def sec_gate_inputs():
    print("[4] 三关检查器的输入数据")
    ext = json.loads((DATA / "ext_full.json").read_text(encoding="utf-8"))
    arms = [k for k in ("free_ext2", "lock_ext", "lock_ext3") if k in ext]
    check("ext_full.json 含 free_ext2 / lock_ext / lock_ext3",
          len(arms) == 3, "、".join(arms))
    d = {}
    for tag in arms:
        blk = ext[tag]["blocks"]
        vals = [b["R"] for b in blk]
        d[tag] = round(abs(vals[-1] - vals[-2]), 3) if len(vals) >= 2 else None
    if VERBOSE:
        print("        各臂末两块差:", d)
    check("free_ext2 末两块差 = 0.587", d.get("free_ext2") == 0.587, str(d.get("free_ext2")))
    check("lock_ext3 末两块差 = 0.251", d.get("lock_ext3") == 0.251, str(d.get("lock_ext3")))

    rows = list(csv.DictReader((DATA / "iter_metrics.csv").open(encoding="utf-8")))
    terms = [c for c in rows[0] if c.startswith("Mean_episode_rew_")]
    check("iter_metrics.csv 有 Mean_reward 列", "Mean_reward" in rows[0])
    check("iter_metrics.csv 有分项列 Mean_episode_rew_*（>0）", len(terms) > 0, f"{len(terms)} 列")
    arms_csv = sorted({r["arm"] for r in rows})
    check("iter_metrics.csv 两臂 = free_swing / lock",
          arms_csv == ["free_swing", "lock"], str(arms_csv))
    print(f"        iter_metrics.csv 行数 = {len(rows)}，分项 {len(terms)} 列")
    return len(rows)


def main():
    print("=" * 78)
    print("重算论文关键数字（纯标准库，无网络，无 GPU）")
    print("=" * 78)
    sec_audit()
    print()
    sec_mutation()
    print()
    sec_figs()
    print()
    sec_gate_inputs()
    print("=" * 78)
    n_fail = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"断言 {len(RESULTS)} 条：PASS {len(RESULTS) - n_fail} / FAIL {n_fail}")
    if n_fail:
        print("失败项：")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  - {name}  {detail}")
    print("=" * 78)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
