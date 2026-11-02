#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""补测 G1–G6：专治变异测试暴露的四个盲区族。

设计原则：每条补测都必须**在对应变异体存在时失败**（否则它只是装饰）。
  G1 元检查（静态）：守卫必须被调用、且"启用开关"必须被引用 —— 杀 M11/M18/M19
  G2 校核自反性：给 assert_injection_effective 喂 before==after，必须抛错 —— 杀 M14
  G3 边界：p=0 零注入、p=1 全注入（端点）—— 边界正确性
  G4 状态清零：reset 后旧故障必须清空 —— 杀 M05
  G5 观测一致：fault_obs_buf 的腿数 = 故障腿数 —— 杀 M12
  G6 协议指纹：run_meta 的 seed_effective 必须是变量而非常量 None —— 杀 M21

运行（由 variability harness 调用）：
    P1R8_PKG_ROOT=<work> python tests/test_guards_meta.py
"""
import ast
import importlib.util
import os
import sys
from pathlib import Path

WORK = Path(os.environ.get("P1R8_PKG_ROOT", ".")).resolve()
HERE = Path(__file__).resolve().parent

# 载入原自检模块：复用它的 isaacgym 替身、FakeEnv 等（不执行 main）
spec = importlib.util.spec_from_file_location("base_tests", WORK / "tests" / "test_r1_r8_local.py")
base = importlib.util.module_from_spec(spec)
sys.modules["base_tests"] = base
spec.loader.exec_module(base)

import torch  # noqa: E402
from legged_gym.utils import fault_detector as fd          # noqa: E402
from legged_gym.utils import silent_failure_guards as guards  # noqa: E402

RESULTS = []


def check(cid, desc, fn):
    try:
        ev = fn()
        RESULTS.append((cid, True, ev))
        print(f"  [PASS] {cid:6s} {desc}")
    except Exception as e:
        RESULTS.append((cid, False, f"{type(e).__name__}: {e}"))
        print(f"  [FAIL] {cid:6s} {desc}  -> {type(e).__name__}: {e}")


def _src(rel):
    return ast.parse((WORK / rel).read_text(encoding="utf-8"))


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name}")


def _names_in(fn_node):
    """函数体内出现的标识符集合（属性名也收进去，便于查 strict_checks）。"""
    out = set()
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.Name):
            out.add(node.id)
    return out


def _calls_in(fn_node):
    out = set()
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                out.add(node.func.attr)
            elif isinstance(node.func, ast.Name):
                out.add(node.func.id)
    return out


def g1_meta_static():
    """守卫必须被调用 + 启用开关必须被引用。"""
    env_tree = _src("legged_gym/envs/a1_rescue/a1_rescue_phase3_env.py")
    reset = _find_func(env_tree, "reset_idx")
    calls = _calls_in(reset)
    need = {"reset_envs", "apply", "verify"}
    assert need <= calls, f"reset_idx 缺少调用: {need - calls}"

    # verify 必须挂在"受开关约束"的分支里，而不是无条件/恒假分支
    verify_guarded = False
    for node in ast.walk(reset):
        if isinstance(node, ast.If) and "verify" in _calls_in(node):
            if "strict_checks" in _names_in(node.test):
                verify_guarded = True
    assert verify_guarded, "reset 后自检不在 strict_checks 分支里（可被静默绕过）"

    fd_tree = _src("legged_gym/utils/fault_detector.py")
    apply_fn = _find_func(fd_tree, "apply")
    names = _names_in(apply_fn)
    assert "strict_checks" in names, "apply 里不再引用 strict_checks（逐腿核对可能被关）"
    assert "_assert_leg_effective" in _calls_in(apply_fn), "apply 不再调用逐腿核对"
    return {"calls": sorted(need), "strict_checks_referenced": True}


def g2_self_reflexive():
    """before==after 必须被判为"未生效"。"""
    e = base.FakeEnv(num_envs=8)
    ids = torch.arange(8)
    before = e.torque_limits.clone()
    after = before.clone()          # 完全没变
    try:
        guards.assert_injection_effective(e, ids, "free_swing", before, after)
    except guards.SilentFailureError as ex:
        return {"raised": True, "msg": str(ex)[:60]}
    raise AssertionError("before==after 时校核没报错（生效判定恒真）")


def _arm(mode, num_envs=32, **kw):
    probs = {"free_swing": dict(fault_prob_locked=1.0, fault_prob_weakened=0.0, fault_prob_lock=0.0),
             "lock": dict(fault_prob_locked=0.0, fault_prob_weakened=0.0, fault_prob_lock=1.0),
             "none": dict(fault_prob_locked=0.0, fault_prob_weakened=0.0, fault_prob_lock=0.0)}[mode]
    probs.update(kw)
    inj = fd.FaultInjector(num_envs=num_envs, device="cpu", **probs)
    return base.FakeEnv(num_envs=num_envs), inj


def g3_boundary():
    """p=0 必须零注入；p=1 必须全注入。"""
    e0, inj0 = _arm("none")
    ids = torch.arange(e0.num_envs)
    inj0.reset_envs(ids)
    n0 = int((inj0.fault_states > 0).any(dim=1).sum().item())
    assert n0 == 0, f"p=0 仍注入 {n0} 个环境"

    e1, inj1 = _arm("free_swing")
    inj1.reset_envs(ids)
    n1 = int((inj1.fault_states > 0).any(dim=1).sum().item())
    assert n1 == e1.num_envs, f"p=1 只注入 {n1}/{e1.num_envs}"
    return {"p0_injected": n0, "p1_injected": n1}


def g4_state_cleared():
    """reset 必须清空旧状态。"""
    e, inj = _arm("none")
    ids = torch.arange(e.num_envs)
    inj.fault_states[:] = 1          # 人为制造"上一回合残留"
    inj.reset_envs(ids)
    left = int((inj.fault_states > 0).sum().item())
    assert left == 0, f"reset 后仍有 {left} 个残留标记"
    return {"residual": left}


def g5_obs_consistent():
    """上帝视角的腿数 = 故障腿数。"""
    e, inj = _arm("free_swing", num_envs=32)
    ids = torch.arange(32)
    inj.reset_envs(ids)
    inj.apply(e, ids)
    n_fault_legs = int((inj.fault_states > 0).sum().item())
    n_obs = int(e.fault_obs_buf.sum().item())
    assert n_obs == n_fault_legs, f"观测标记 {n_obs} != 故障腿 {n_fault_legs}"
    return {"obs": n_obs, "fault_legs": n_fault_legs}


def g6_run_meta_seed():
    """run_meta 的 seed_effective 必须是变量（不能写成常量 None）。"""
    tree = _src("legged_gym/scripts/train.py")
    fn = _find_func(tree, "_write_run_meta")
    found = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "seed_effective":
                    found = v
    assert found is not None, "run_meta 里没有 seed_effective 字段"
    assert not (isinstance(found, ast.Constant) and found.value is None), \
        "seed_effective 被写成常量 None"
    assert isinstance(found, ast.Name), "seed_effective 不是变量（来源不明）"
    return {"bound_to": found.id}


def main():
    print("=" * 70)
    print("补测 G1–G6（针对变异测试盲区）")
    print("=" * 70)
    check("G1", "守卫被调用 + strict_checks 被引用（元检查）", g1_meta_static)
    check("G2", "校核自反性：before==after 必须报错", g2_self_reflexive)
    check("G3", "边界：p=0 零注入 / p=1 全注入", g3_boundary)
    check("G4", "reset 后旧故障必须清零", g4_state_cleared)
    check("G5", "上帝视角腿数 = 故障腿数", g5_obs_consistent)
    check("G6", "run_meta.seed_effective 必须绑定变量", g6_run_meta_seed)

    n_pass = sum(1 for _, ok, _ in RESULTS if ok)
    n_fail = len(RESULTS) - n_pass
    print("=" * 70)
    print(f"META 合计 {len(RESULTS)} 项：PASS {n_pass} / FAIL {n_fail}")
    print("=" * 70)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
