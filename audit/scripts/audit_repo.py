#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""仓库审计工具：对 **本地已解压的源码目录** 跑三条检查，输出 JSON。

判据来源：`[workspace]/20-外部有效性扩样方案与首例复核-20261012/.md` §三/§四
  C1 seed 有效性：训练入口是否**真的**把 --seed 传到 set_seed（而不是只解析）
  C2 评估开关：play/eval 脚本是否显式关闭随机化/设置确定性
  C3 注入可核性：出现"扰动/故障"写物理量的地方，是否有**核对它真的生效**的代码

设计原则（写进论文的方法节）：
  - 工具只给 **信号 + 暂定判定**，终判必须人工复核（`manual_review` 列）；
  - 每条判定都记录**证据行**（文件:行号 + 代码片段），可逐条回看；
  - 分析单元 = 仓库 @ 固定 ref；本工具不联网，ref 由上层记录。

用法：
    python audit_repo.py <repo_dir> [--name NAME] [--json]
"""
import argparse
import ast
import json
import re
from pathlib import Path

SEED_FUNCS = {"set_seed", "seed_everything", "manual_seed", "seed_all", "PRNGKey", "PRNGKeyArray"}

# 三种常见的"声明 seed 入口"写法：
#   argparse: add_argument("--seed", ...) / {"name": "--seed"}
#   absl:     flags.DEFINE_integer("seed", ...)
#   config:   cfg.seed = ... / config.seed: int
RE_SEED_DECL = re.compile(
    r"""(add_argument\(\s*["']--?seed|["']--seed["']|DEFINE_\w+\(\s*["']seed["']|seed\s*[:=]\s*\d+)""",
    re.I,
)


def py_files(root: Path):
    skip = {".git", "build", "dist", "__pycache__", ".eggs", "node_modules"}
    out = []
    for p in root.rglob("*.py"):
        if any(part in skip for part in p.parts):
            continue
        out.append(p)
    return out


def read(p: Path):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def find_train_entries(root: Path):
    cands = []
    for p in py_files(root):
        name = p.name.lower()
        if name in ("train.py",) or (p.parent.name == "scripts" and "train" in name):
            cands.append(p)
    return cands


def _arg_text(node):
    """把调用实参还原成源码文本（兼容 Python 3.8：没有 ast.unparse）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _arg_text(node.value) + "." + node.attr
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Call):
        return _arg_text(node.func) + "(...)"
    return "<expr>"


def c1_seed(root: Path):
    """C1：--seed 有没有被写进 **env_cfg**（真正播种用的那个 cfg）。

    真实缺陷（legged_gym 上游）：`update_cfg_from_args` 只做 `cfg_train.seed = args.seed`，
    而 `set_seed(env_cfg.seed)` 用的是 env_cfg 的默认值 ⇒ CLI 种子对环境影响为零。
    修好的写法（extreme-parkour）：多一行 `env_cfg.seed = args.seed`。
    """
    ev = {"seed_flag_files": [], "routing": [], "set_seed_calls": [],
          "verdict": None, "evidence": []}

    for p in py_files(root):
        rel = str(p.relative_to(root))
        txt = read(p)
        if RE_SEED_DECL.search(txt):
            ev["seed_flag_files"].append(rel)
        try:
            tree = ast.parse(txt)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # 形如 X.seed = args.seed（只认 **CLI** 来源；X.seed = train_cfg.seed 不算）
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) \
                    and node.value.attr == "seed" \
                    and isinstance(node.value.value, ast.Name) and node.value.value.id == "args":
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and t.attr == "seed":
                        base = t.value.id if isinstance(t.value, ast.Name) else "?"
                        ev["routing"].append({"file": rel, "line": node.lineno, "base": base})
                        ev["evidence"].append(f"{rel}:{node.lineno}: {base}.seed = args.seed")
            # 形如 set_seed(env_cfg.seed) / torch.manual_seed(...)
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
                if name in SEED_FUNCS:
                    arg = _arg_text(node.args[0]) if node.args else ""
                    ev["set_seed_calls"].append({"file": rel, "line": node.lineno, "arg": arg})

    env_bases = {"env_cfg", "env_config", "env"}
    train_bases = {"cfg_train", "train_cfg", "cfg", "config"}
    routed_env = any(r["base"] in env_bases for r in ev["routing"])
    routed_train_only = (not routed_env) and any(r["base"] in train_bases for r in ev["routing"])
    has_set_seed = bool(ev["set_seed_calls"])

    if not ev["seed_flag_files"]:
        ev["verdict"] = "no_seed_flag"
    elif routed_env and has_set_seed:
        ev["verdict"] = "seed_applied"
    elif routed_train_only and has_set_seed:
        ev["verdict"] = "MISROUTED_seed_to_train_cfg"   # 真实缺陷：CLI 种子没进环境
    elif has_set_seed:
        ev["verdict"] = "declared_and_seeded_routing_unclear"
    elif ev["seed_flag_files"]:
        ev["verdict"] = "declared_but_no_seed_call"
    else:
        ev["verdict"] = "no_set_seed_call"
    return ev


def c2_eval_switches(root: Path):
    """C2：eval/play 脚本里是否有确定性/单环境/关随机化开关。"""
    plays = [p for p in py_files(root) if p.name.lower() in ("play.py", "eval.py", "evaluate.py")]
    ev = {"play_files": [], "verdict": None, "detail": []}
    if not plays:
        ev["verdict"] = "no_eval_entry"
        return ev
    for p in plays:
        txt = read(p)
        hits = {
            "headless": "--headless" in txt,
            "num_envs_1": bool(re.search(r"num_envs\s*=\s*1\b", txt)),
            "deterministic": bool(re.search(r"deterministic|torch\.use_deterministic", txt)),
            "noise_off": bool(re.search(r"add_noise\s*=\s*False", txt)),
        }
        ev["play_files"].append(str(p.relative_to(root)))
        ev["detail"].append({"file": str(p.relative_to(root)), **hits,
                             "score": sum(hits.values())})
    best = max(d["score"] for d in ev["detail"])
    ev["verdict"] = "complete" if best >= 3 else ("partial" if best >= 1 else "absent")
    return ev


def c3_injection_audit(root: Path):
    """C3：扰动/故障注入处是否有"生效核对"。"""
    ev = {"injection_files": [], "audit_files": [], "verdict": None, "evidence": []}
    inj_pat = re.compile(r"(fault|inject|disturb|perturb|randomiz)", re.I)
    audit_pat = re.compile(r"(assert_|verify|_check_effective|assert\s+.*(fault|inject))", re.I)
    for p in py_files(root):
        txt = read(p)
        if not inj_pat.search(txt):
            continue
        ev["injection_files"].append(str(p.relative_to(root)))
        if audit_pat.search(txt):
            ev["audit_files"].append(str(p.relative_to(root)))
            for i, line in enumerate(txt.splitlines(), 1):
                if audit_pat.search(line) and len(ev["evidence"]) < 5:
                    ev["evidence"].append(f"{p.relative_to(root)}:{i}: {line.strip()[:90]}")
    if not ev["injection_files"]:
        ev["verdict"] = "no_injection_code"
    elif ev["audit_files"]:
        ev["verdict"] = "has_audit_signal"
    else:
        ev["verdict"] = "no_audit_signal"
    return ev


def audit(root: Path, name=None):
    files = py_files(root)
    return {
        "name": name or root.name,
        "path": str(root),
        "n_py": len(files),
        "C1_seed": c1_seed(root),
        "C2_eval": c2_eval_switches(root),
        "C3_injection": c3_injection_audit(root),
        "manual_review": "待人工复核：C1 需确认 seed 是否传入 set_seed 的实参；C3 需确认 assert 是否真的守在注入点上",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--name", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = audit(Path(a.repo), a.name)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(f"== {r['name']}  ({r['n_py']} py) ==")
        print(f"  C1 seed   : {r['C1_seed']['verdict']}")
        for e in r['C1_seed']['evidence'][:3]:
            print(f"              {e}")
        print(f"  C2 eval   : {r['C2_eval']['verdict']}  {r['C2_eval']['detail']}")
        print(f"  C3 inject : {r['C3_injection']['verdict']}  files={len(r['C3_injection']['injection_files'])}")


if __name__ == "__main__":
    main()
