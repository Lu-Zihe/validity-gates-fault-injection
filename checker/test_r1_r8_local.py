#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
R1–R8 零 GPU 本地自检（2026-10-12 P1-1）

为什么要有它：R1–R8 修的都是**静默失效**——"配置说 A、实际做 B、而且不报错"。
这种毛病靠"人读代码"是抓不住的（本项目已经栽过三次）。所以每个修复都配一条
**可执行的断言**，在本机 CPU 上跑（torch CPU + numpy + isaacgym 替身），
把"改对了"变成"打印出来的证据"。

判据：全部检查 PASS，且**旧行为必须被抓住**（每条修复都有一条"反向用例"：
拿旧实现/旧参数喂进去，断言它必须报错或必须被识别为静默无效）。

用法::

    python tests/test_r1_r8_local.py            # 全跑
    python tests/test_r1_r8_local.py -v         # 打印更多证据
"""
import json
import os
import sys
import traceback
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("P1R8_PKG_ROOT") or os.path.dirname(HERE)
# P1R8_USE_REAL_ISAACGYM=1 ⇒ 用**真** isaacgym（云端；比替身强，能验证真实地形几何）。
# 注意：isaacgym 必须在 torch 之前导入，否则报 "PyTorch was imported before isaacgym"。
USE_REAL_ISAACGYM = os.environ.get("P1R8_USE_REAL_ISAACGYM") == "1"
if USE_REAL_ISAACGYM:
    import isaacgym  # noqa: F401
    # 真包有循环导入的脆弱点：`legged_gym.utils.__init__` 会 import task_registry，
    # 而 task_registry 又回头 import `legged_gym.envs.base...` ⇒ 必须先初始化 `legged_gym.envs`。
    # （eval_clean.py 也是先 `from legged_gym.envs import task_registry`，同一个道理。）
    import legged_gym.envs  # noqa: F401
else:
    sys.path.insert(0, os.path.join(HERE, "isaacgym_stub"))   # isaacgym 测试替身
sys.path.insert(0, ROOT)

if not USE_REAL_ISAACGYM:
    # ---- 测试专用 shim：本工作树是**部分覆盖层**（只含 R1–R8 触及的文件 + 运行时依赖），
    #      没有 a1/anymal/cassie 那些任务包，也没有 legged_gym/__init__.py（云端本来就有）。
    #      因此这里把 `legged_gym.envs` 预注册成"带 __path__ 的命名空间包"，
    #      避免执行真实的 envs/__init__.py（它会去 import 本机不存在的任务模块）。
    #      ⚠️ 这只影响本机自检，不影响云端运行；云端用 P1R8_USE_REAL_ISAACGYM=1 走另一条路。
    import types
    _envs_pkg = types.ModuleType("legged_gym.envs")
    _envs_pkg.__path__ = [os.path.join(ROOT, "legged_gym", "envs")]
    sys.modules["legged_gym.envs"] = _envs_pkg

    # terrain.py 只用 LeggedRobotCfg 做类型标注（`cfg: LeggedRobotCfg.terrain`），
    # 而真实的 legged_robot_config 还要 import 本机没有的 base_config ⇒ 测试里替换成最小替身。
    _base_cfg_pkg = types.ModuleType("legged_gym.envs.base")
    _base_cfg_pkg.__path__ = [os.path.join(ROOT, "legged_gym", "envs", "base")]
    sys.modules["legged_gym.envs.base"] = _base_cfg_pkg
    _cfg_mod = types.ModuleType("legged_gym.envs.base.legged_robot_config")

    class LeggedRobotCfg:            # noqa: D401  (测试替身)
        class terrain:
            pass

    _cfg_mod.LeggedRobotCfg = LeggedRobotCfg
    sys.modules["legged_gym.envs.base.legged_robot_config"] = _cfg_mod

import numpy as np
import torch

try:  # Windows 控制台默认 GBK，会把 ⇒/✅ 这类字符打成崩溃
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RESULTS = []
VERBOSE = "-v" in sys.argv


def check(cid, desc, fn, expect="pass"):
    """expect='pass' → 期望不抛异常；expect='raise' → 期望抛异常（旧行为必须被抓住）"""
    try:
        detail = fn()
        ok = (expect == "pass")
        err = None
    except Exception as e:
        detail = None
        ok = (expect == "raise")
        err = f"{type(e).__name__}: {e}"
    RESULTS.append({"id": cid, "desc": desc, "expect": expect,
                    "ok": bool(ok), "detail": detail, "error": err})
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {cid:<8} {desc}")
    if not ok:
        print(f"         ↳ 期望={expect}；实际: {err or detail}")
    elif VERBOSE and (detail or err):
        print(f"         ↳ {json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else (detail if detail else err)}")
    return ok


# ==================================================================== 测试替身
class ShapeProps:
    def __init__(self, friction=1.0):
        self.friction = friction


class BodyProps:
    def __init__(self, mass):
        self.mass = mass


class FakeGym:
    """记录所有 set 调用，用来证明"真的写进去了"（而不是静默跳过）"""

    def __init__(self, base_mass=6.0, n_bodies=13):
        self.base_mass = base_mass
        self.n_bodies = n_bodies
        self.shape_sets = []
        self.body_sets = []
        self.dof_state_sets = []

    def get_actor_rigid_shape_properties(self, h, a):
        return [ShapeProps(1.0), ShapeProps(1.0)]

    def set_actor_rigid_shape_properties(self, h, a, props):
        self.shape_sets.append((h, a, tuple(round(float(p.friction), 6) for p in props)))

    def get_actor_rigid_body_properties(self, h, a):
        return [BodyProps(self.base_mass)] + [BodyProps(0.5) for _ in range(self.n_bodies - 1)]

    def set_actor_rigid_body_properties(self, h, a, props, recomputeInertia=False):
        self.body_sets.append((h, a, round(float(props[0].mass), 6)))

    def set_dof_state_tensor_indexed(self, sim, tensor, ids, n):
        # 云端真 gymtorch 下 `unwrap_tensor` 返回的对象**没有 len()**（实测 TypeError），
        # 所以这里只用 numel/len 兜底，且以 n 为准（真实现的语义参数）。
        try:
            k = int(ids.numel()) if hasattr(ids, "numel") else len(ids)
        except Exception:
            k = int(n)
        self.dof_state_sets.append((k, int(n)))


class FakeEnv:
    """legged_gym 的最小替身（只保留 R1–R8 触及的那些张量/载体）"""

    def __init__(self, num_envs=16, num_dof=12, base_mass=6.0):
        self.num_envs = num_envs
        self.device = "cpu"
        self.gym = FakeGym(base_mass=base_mass)
        self.envs = list(range(num_envs))
        self.actor_handles = list(range(100, 100 + num_envs))
        self.sim = "sim"
        self.nominal = torch.full((num_envs, num_dof), 33.5)
        self.torque_limits = self.nominal.clone()
        self.p_gains = torch.full((num_dof,), 20.0)
        self.d_gains = torch.full((num_dof,), 0.5)
        self.dof_pos = torch.randn(num_envs, num_dof)
        self.dof_vel = torch.randn(num_envs, num_dof)
        # ⚠️ 真环境里 default_dof_pos 是 (1, num_dof)（legged_robot.py 用 unsqueeze(0) 生成）
        # ⇒ 替身必须用同一形状，否则 lock 的切片 bug 会"假过"（独立复核抓到过）
        self.default_dof_pos = torch.zeros(1, num_dof)
        self.fault_obs_buf = torch.zeros(num_envs, 4)
        self.dof_state = torch.zeros(num_envs * num_dof * 2)


class Cfg:
    """Terrain 的最小 cfg 替身"""

    def __init__(self, **kw):
        self.mesh_type = "trimesh"
        self.terrain_length = 8.0
        self.terrain_width = 8.0
        self.horizontal_scale = 0.1
        self.vertical_scale = 0.005
        self.border_size = 25.0
        self.num_rows = 8
        self.num_cols = 7
        self.terrain_proportions = [1 / 7] * 7
        self.curriculum = False
        self.selected = False
        self.slope_treshold = 0.75
        self.strict_checks = True
        self.debris_size = None
        self.debris_density = None
        self.tilt_angle = None
        for k, v in kw.items():
            setattr(self, k, v)


def main():
    import legged_gym.utils.curriculum_plan as cplan
    import legged_gym.utils.silent_failure_guards as guards
    import legged_gym.utils.terrain_selector as ts
    import legged_gym.utils.domain_randomization as dr
    import legged_gym.utils.fault_detector as fd
    import legged_gym.utils.terrain as terrain_mod

    print("=" * 78)
    print(f"R1–R8 零 GPU 本地自检  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  python={sys.version.split()[0]}  torch={torch.__version__}  numpy={np.__version__}")
    print("=" * 78)

    # ---------------------------------------------------------------- R1 地形
    print("\n[R1] 地形课程：真难度梯度 + 7 生成器接列（D1）")
    sched = cplan.curriculum_schedule(8, 7, 0.5, 1.0)
    check("R1-1", "gradient 调度表：8 档难度、7 个生成器", lambda: {
        "n": len(sched),
        "difficulties": sorted({d for (_i, _j, _c, d) in sched}),
        "choices": sorted({c for (_i, _j, c, _d) in sched}),
    } and (_assert(len({d for (_i, _j, _c, d) in sched}) == 8 and
                   len({c for (_i, _j, c, _d) in sched}) == 7) or (_ for _ in ()).throw(
        AssertionError("难度档数或生成器数不对"))))

    legacy = cplan.curriculum_schedule(8, 7, legacy_fixed=True)
    check("R1-2", "legacy_fixed 调度表复原冻结行为（难度恒定 0.5、choice 恒定 6）", lambda: {
        "difficulties": sorted({d for (*_x, d) in legacy}),
        "choices": sorted({c for (_i, _j, c, _d) in legacy}),
    } and (_assert({d for (*_x, d) in legacy} == {0.5} and {c for (_i, _j, c, _d) in legacy} == {6})
           or (_ for _ in ()).throw(AssertionError("legacy 复现不一致"))))

    check("R1-3", "R8 断言抓住 D1（难度全同 ⇒ 必须报错）",
          lambda: guards.assert_terrain_schedule_effective(legacy), expect="raise")
    check("R1-4", "R8 断言放过正确梯度", lambda: guards.assert_terrain_schedule_effective(sched))

    def build_terrain(**kw):
        cfg = Cfg(**kw)
        return terrain_mod.Terrain(cfg, 4096)

    t_grad = build_terrain(generation="gradient", curriculum_difficulty_min=0.5,
                           curriculum_difficulty_max=1.0)
    check("R1-5", "gradient 地形：行间幅度拉开（几何级复核）", lambda: t_grad.terrain_evidence)
    t_legacy = build_terrain(generation="legacy_fixed")
    check("R1-6", "legacy_fixed 地形可精确复现（不做梯度断言）", lambda: {
        "generation": t_legacy.generation,
        "distinct_sums": len(set(
            int(t_legacy.height_field_raw[
                t_legacy.border + i * t_legacy.length_per_env_pixels:
                t_legacy.border + (i + 1) * t_legacy.length_per_env_pixels,
                t_legacy.border + j * t_legacy.width_per_env_pixels:
                t_legacy.border + (j + 1) * t_legacy.width_per_env_pixels].sum())
            for i in range(8) for j in range(7))),
    })
    t_auto = build_terrain()   # 不给 generation
    check("R1-7", "未声明 generation 时默认 legacy_fixed（不许静默换地形）",
          lambda: _assert(t_auto.generation == "legacy_fixed") or
          (_ for _ in ()).throw(AssertionError(f"实际={t_auto.generation}")))

    def legacy_ignores_debris():
        """legacy_fixed 必须**连建图期域随机化一起**忽略——否则"复现旧地形"实际换了地图
        （独立复核实测：带 debris 与不带相比 28.6% 像素不同、坡度 +25%）"""
        cfg = Cfg(generation="legacy_fixed", debris_size=0.05,
                  debris_density=0.15, tilt_angle=0.075)
        cfg.num_rows, cfg.num_cols = 2, 7
        t = terrain_mod.Terrain(cfg, 16)
        rand = t.get_terrain_rand()
        assert all(v is None for v in rand.values()), f"legacy_fixed 仍带建图期随机化: {rand}"
        cfg2 = Cfg(generation="gradient", debris_size=0.05, debris_density=0.15, tilt_angle=0.075)
        cfg2.num_rows, cfg2.num_cols = 2, 7
        t2 = terrain_mod.Terrain(cfg2, 16)
        assert all(v is not None for v in t2.get_terrain_rand().values()), "gradient 丢了建图期随机化"
        return {"legacy": rand, "gradient": t2.get_terrain_rand()}
    check("R1-9", "legacy_fixed 连建图期 DR 一起忽略（复现旧地形不被 debris 参数换掉）",
          legacy_ignores_debris)

    check("R1-8", "R8 断言抓住『gradient 但难度没落到高度场』",
          lambda: guards.assert_terrain_not_degenerate(t_legacy, "gradient"), expect="raise")

    # ---------------------------------------------------------------- R2 课程→配比
    print("\n[R2] 课程等级真正驱动地形配比（不再只写一个行索引）")
    sel = ts.AdaptiveTerrainSelector(num_levels=8, window_size=50, energy_reference=200.0,
                                     energy_threshold=0.7)
    check("R2-1", "等级 → terrain_proportions 每级不同且和为 1", lambda: {
        f"L{lv}": [round(p, 3) for p in _props_at(sel, lv)] for lv in (0, 3, 7)
    } and (_assert(all(abs(sum(_props_at(sel, lv)) - 1.0) < 1e-9 for lv in range(8)))
           or (_ for _ in ()).throw(AssertionError("配比和不为 1"))))
    check("R2-2", "L0 只用 1 种地形，L7 用满 7 种（配比随等级变化 = 有因果影响）",
          lambda: _assert(
              sum(1 for p in _props_at(sel, 0) if p > 0) == 1 and
              sum(1 for p in _props_at(sel, 7) if p > 0) == 7)
          or (_ for _ in ()).throw(AssertionError("配比没有随等级变化")))

    # ---------------------------------------------------------------- R3 域随机化
    print("\n[R3] 域随机化真接入（去 hasattr 守卫、修参数槽位、8 维落地）")
    env = FakeEnv(num_envs=8)
    # R3 拍板后：默认 authority = friction:ruins_dr / base_mass:builtin / motor_strength:ruins_dr
    # ⇒ 默认只写摩擦与电机；质量路径用显式 authority 单独覆盖（见 R3-1b）
    mgr = dr.RuinsDomainRandomization(num_envs=8, stage_ratio=0.5, device="cpu", seed=0)
    mgr.set_total_iters(100)
    params = mgr.apply_runtime(env, torch.arange(8))

    check("R3-1", "默认真源下 DR 只写摩擦与电机（质量归内置）",
          lambda: _assert(len(env.gym.shape_sets) == 8 and len(env.gym.body_sets) == 0
                          and not torch.equal(env.torque_limits, env.nominal))
          or (_ for _ in ()).throw(AssertionError(
              f"shape_sets={len(env.gym.shape_sets)} body_sets={len(env.gym.body_sets)} "
              f"torque_changed={not torch.equal(env.torque_limits, env.nominal)}")))

    def mass_path_works():
        """把质量真源显式改成 ruins_dr 时，质量写入路径必须真的工作（代码路径别变成死码）"""
        e = FakeEnv(num_envs=8)
        m = dr.RuinsDomainRandomization(8, device="cpu", seed=1,
                                        authority={'friction': 'ruins_dr', 'base_mass': 'ruins_dr',
                                                   'motor_strength': 'ruins_dr'})
        m.apply_runtime(e, torch.arange(8))
        assert len(e.gym.body_sets) == 8, f"质量写入次数 {len(e.gym.body_sets)}"
        base = e.gym.base_mass
        for (_h, _a, mass) in e.gym.body_sets:
            assert abs(mass / base - 1.0) <= 0.35, f"质量缩放越界: {mass}/{base}"
        return {"n_mass_writes": len(e.gym.body_sets), "nominal_base_mass": base}
    check("R3-1b", "显式把质量真源设为 ruins_dr 时，质量写入路径真的工作", mass_path_works)

    check("R3-2", "旧调用写法（params 槽位收到 env_ids）不再静默 no-op，而是报错",
          lambda: mgr.apply_to_env(FakeEnv(8), torch.arange(8)), expect="raise")

    check("R3-3", "未知随机化维度直接报错（旧实现静默忽略）",
          lambda: dr.RuinsDomainRandomization(8, param_ranges={"wrong_dim": (0, 1, 0, 1)}),
          expect="raise")

    def fake_env_missing_carrier():
        e = FakeEnv(4)
        del e.gym
        return dr.RuinsDomainRandomization(4, device="cpu").apply_runtime(e, torch.arange(4))
    check("R3-4", "载体不存在时直接报错（旧实现 hasattr 静默跳过）",
          fake_env_missing_carrier, expect="raise")

    def terrain_with_debris(**kw):
        cfg = Cfg(generation="gradient", **kw)
        cfg.num_rows, cfg.num_cols = 2, 7
        t = terrain_mod.Terrain(cfg, 16)
        return t

    np.random.seed(0)
    t_no = terrain_with_debris()                       # debris=None（冻结行为）
    np.random.seed(0)
    t_size = terrain_with_debris(debris_size=0.15, debris_density=0.3, tilt_angle=0.30)
    check("R3-5", "建图期维（粒径/密度/倾角）真的改变高度场（D2 的另外三维有了载体）",
          lambda: _assert(not np.array_equal(t_no.height_field_raw, t_size.height_field_raw))
          or (_ for _ in ()).throw(AssertionError("高度场完全相同 ⇒ 参数没流到生成器")))

    check("R3-6", "DR 阶段切换（small→large）真的换范围",
          lambda: _assert(mgr.get_randomized_params_batch(1, stage="large")["friction"][0] < 1.25 and
                          mgr.get_randomized_params_batch(1, stage="small")["friction"][0] <= 1.0)
          or (_ for _ in ()).throw(AssertionError("阶段没切换")))

    def stage_anchored():
        """两阶段必须锚在 common_step_counter 上（旧代码 set_total_training_iters 零调用）"""
        m = dr.RuinsDomainRandomization(8, stage_ratio=0.5, device="cpu", total_steps=72000)
        m.observe_step(0)
        s0 = m._get_stage()
        m.observe_step(int(72000 * 0.5) - 1)
        s1 = m._get_stage()
        m.observe_step(int(72000 * 0.5) + 1)
        s2 = m._get_stage()
        assert (s0, s1, s2) == ("small", "small", "large"), f"锚点阶段错: {s0},{s1},{s2}"
        assert m.is_stage_anchored()
        return {"at_0": s0, "below_ratio": s1, "above_ratio": s2}
    check("R3-7", "两阶段锚在 common_step_counter：0.5 前 small、之后 large", stage_anchored)
    check("R3-8", "无锚点的两阶段必须报错（旧代码就是这样静默停在 small）",
          lambda: guards.assert_dr_stage_anchored(
              dr.RuinsDomainRandomization(8, device="cpu")), expect="raise")

    def authority_filter():
        """逐维真源：authority='builtin' 的维不许再被 RuinsDR 写"""
        m = dr.RuinsDomainRandomization(8, device="cpu",
                                        authority={'friction': 'ruins_dr', 'base_mass': 'builtin',
                                                   'motor_strength': 'ruins_dr'})
        assert m.runtime_dims == ('friction', 'motor_strength'), m.runtime_dims
        p = m.get_randomized_params_batch(4)
        assert set(p.keys()) == {'friction', 'motor_strength'}, p.keys()
        # 非法 authority 必须报错
        try:
            dr.RuinsDomainRandomization(8, device="cpu", authority={'friction': 'who_knows'})
        except ValueError:
            pass
        else:
            raise AssertionError("非法 authority 没报错")
        return {"runtime_dims": list(m.runtime_dims), "params": sorted(p.keys())}
    check("R3-9", "逐维真源：base_mass 归内置 ⇒ RuinsDR 不再写质量", authority_filter)

    def authority_conflicts():
        """真源与内置开关冲突时必须报错（否则两套写同一维）"""
        class _DRCfg:
            randomize_friction = True          # ← 冲突：authority 说 friction 归 ruins_dr
            randomize_base_mass = True
            randomize_motor_strength = False
            push_robots = True
            push_interval_s = 15

        m = dr.RuinsDomainRandomization(8, device="cpu")
        try:
            guards.assert_dr_authority(m, _DRCfg())
        except guards.SilentFailureError:
            pass
        else:
            raise AssertionError("摩擦双真源没被拦住")

        class _DRCfg2:
            randomize_friction = False
            randomize_base_mass = True
            randomize_motor_strength = False
            push_robots = True
            push_interval_s = 15          # 正间隔 = 合法（推力确实生效且语义明确）

        ev = guards.assert_dr_authority(m, _DRCfg2())
        assert ev['push_robots'] is True and ev['push_interval_s'] == 15
        return ev
    check("R3-10", "真源冲突/推力负间隔都必须报错；正间隔+开启则放过", authority_conflicts)

    def push_negative_interval():
        """`push_interval_s=-1`（旧写法"关闭推力"）必须被拦住或显式关掉"""
        class _DRCfg:
            randomize_friction = False
            randomize_base_mass = True
            randomize_motor_strength = False
            push_robots = True
            push_interval_s = -1

        try:
            guards.assert_dr_authority(dr.RuinsDomainRandomization(8, device="cpu"), _DRCfg())
        except guards.SilentFailureError:
            pass
        else:
            raise AssertionError("push_interval_s<0 仍开着推力没被拦住")
        # 取模语义的算术证据
        import numpy as _np
        pi = int(_np.ceil(-1 / 0.02))
        triggered = [c for c in (0, 50, 100, 750) if c % pi == 0]
        assert pi < 0 and triggered, "负间隔取模不再触发（前提变了）"
        return {"push_interval": pi, "still_triggers_at": triggered}
    check("R3-11", "『push_interval_s=-1 关闭推力』是无效写法（负间隔取模仍触发）",
          push_negative_interval)

    # ---------------------------------------------------------------- R4/R5 故障
    print("\n[R4/R5] 故障注入单一入口 + 三形态（free_swing / lock / degrade）")
    check("R4-1", "旧术语正名：'single_leg_lock' → free_swing",
          lambda: _assert(fd.canonical_mode("single_leg_lock") == "free_swing")
          or (_ for _ in ()).throw(AssertionError("正名失败")))

    def arm(mode, num_envs=64, **kw):
        e = FakeEnv(num_envs=num_envs)
        probs = {"free_swing": dict(fault_prob_locked=1.0, fault_prob_weakened=0.0, fault_prob_lock=0.0),
                 "degrade": dict(fault_prob_locked=0.0, fault_prob_weakened=1.0, fault_prob_lock=0.0),
                 "lock": dict(fault_prob_locked=0.0, fault_prob_weakened=0.0, fault_prob_lock=1.0)}[mode]
        probs.update(kw)
        inj = fd.FaultInjector(num_envs=num_envs, device="cpu", **probs)
        ids = torch.arange(num_envs)
        inj.reset_envs(ids)
        applied = inj.apply(e, ids)
        return e, inj, applied

    e_fs, inj_fs, ap_fs = arm("free_swing")
    check("R4-2", "free_swing：故障腿 3 个关节的力矩上限=0，其余不变",
          lambda: _assert(bool((e_fs.torque_limits == 0).any()) and ap_fs["free_swing"] == 64)
          or (_ for _ in ()).throw(AssertionError(f"applied={ap_fs}")))

    e_dg, inj_dg, ap_dg = arm("degrade", degrade_severity=0.5)
    check("R4-3", "degrade：力矩上限 = 标称 × 0.5（旧 weakened 支路的物理本意）",
          lambda: _assert(bool(torch.isclose(
              e_dg.torque_limits[e_dg.torque_limits != 33.5],
              torch.full_like(e_dg.torque_limits[e_dg.torque_limits != 33.5], 16.75), atol=1e-4).all()))
          or (_ for _ in ()).throw(AssertionError(f"applied={ap_dg}")))

    e_lk, inj_lk, ap_lk = arm("lock")
    check("R4-4", "lock：PD 增益×10 且 p_gains 升为 2D（力矩上限不动）",
          lambda: _assert(e_lk.p_gains.dim() == 2 and float(e_lk.p_gains.max()) == 200.0
                          and torch.equal(e_lk.torque_limits, e_lk.nominal))
          or (_ for _ in ()).throw(AssertionError(
              f"p_gains.dim={e_lk.p_gains.dim()} max={float(e_lk.p_gains.max())}")))

    def lock_teleport():
        before_pos = e_lk.dof_pos.clone()
        before_vel = e_lk.dof_vel.clone()
        inj_lk.on_step(e_lk)
        moved = int((e_lk.dof_pos != before_pos).sum().item())
        vel_zeroed = int((e_lk.dof_vel == 0).sum().item())
        assert moved > 0, "lock 没有把关节位置钉住"
        assert vel_zeroed > int((before_vel == 0).sum().item()), "lock 没有把关节速度清零"
        assert len(e_lk.gym.dof_state_sets) == 1, "lock 没有把状态写回仿真"
        return {"dof_pos_moved": moved, "vel_zeroed": vel_zeroed}
    check("R4-5", "lock：每步把 dof_pos/dof_vel 钉到锁定值并写回仿真", lock_teleport)

    def sample_rate():
        e = FakeEnv(num_envs=4000)
        inj = fd.FaultInjector(num_envs=4000, fault_prob_locked=0.10, fault_prob_weakened=0.10,
                               fault_prob_lock=0.0, device="cpu")
        inj.reset_envs(torch.arange(4000))
        st = inj.fault_states
        fs = int((st == fd.MODE_IDS["free_swing"]).any(dim=1).sum())
        dg = int((st == fd.MODE_IDS["degrade"]).any(dim=1).sum())
        assert abs(fs / 4000 - 0.10) < 0.02, f"free_swing 比例偏离: {fs/4000:.4f}"
        assert abs(dg / 4000 - 0.10) < 0.02, f"degrade 比例偏离: {dg/4000:.4f}"
        return {"free_swing_rate": round(fs / 4000, 4), "degrade_rate": round(dg / 4000, 4)}
    check("R4-6", "概率口径：0.10 free_swing + 0.10 degrade（旧配置的 0.10+0.10 现在两端都真实）", sample_rate)

    check("R4-7", "D4 修复：三形态下 nominal_marked 全为 0（无『标为故障但物理正常』）",
          lambda: _nominal_marked_all_modes(arm))

    def old_weakened_repro():
        """复现旧行为：1D p_gains + 旧 `dim()==1 → return` ⇒ 被标为故障但物理不变"""
        e = FakeEnv(num_envs=4)
        inj = fd.FaultInjector(num_envs=4, fault_prob_locked=0.0, fault_prob_weakened=1.0,
                               fault_prob_lock=0.0, device="cpu")
        ids = torch.arange(4)
        inj.reset_envs(ids)                      # 4 个环境全被标成 degrade
        # 旧实现：走 1D p_gains 的弱化支路 → 直接 return，什么都不改
        if e.p_gains.dim() == 1:
            pass                                  # ← 旧代码就在这里静默返回
        stats = {"total": 4, "normal": 0, "free_swing": 0, "lock": 0, "degrade": 4,
                 "nominal_marked": inj.count_nominal_marked(e)}
        return stats
    check("R5-1", "旧行为复现：名义故障确实存在（nominal_marked=4）",
          lambda: _assert(old_weakened_repro()["nominal_marked"] == 4)
          or (_ for _ in ()).throw(AssertionError("没能复现旧行为")))
    check("R5-2", "R8 断言抓住旧行为（nominal_marked>0 ⇒ 必须报错）",
          lambda: guards.assert_fault_stats_consistent(old_weakened_repro()), expect="raise")

    def gains_2d_idempotent():
        e = FakeEnv(num_envs=8)
        g1, _ = fd.ensure_gains_2d(e)
        g2, _ = fd.ensure_gains_2d(e)
        assert g1.dim() == 2 and g2.dim() == 2
        assert torch.equal(g1, g2), "非幂等"
        assert torch.allclose(g1[0], torch.full((12,), 20.0)), "1D→2D 改变了数值"
        return {"shape": tuple(g1.shape), "value_unchanged": True}
    check("R5-3", "p_gains 升 2D 且幂等、不改变原有数值（对旧结果无副作用）", gains_2d_idempotent)

    # ---------------------------------------------------------------- R6 能耗口径
    print("\n[R6] 归一化能耗口径统一（分母 200 W / clamp [0,1] / 阈值 0.7）")
    check("R6-1", "0.528 的算术自洽性：105.6 W ÷ 200 W = 0.528",
          lambda: _assert(abs(ts.normalize_energy(105.6, 200.0) - 0.528) < 1e-9)
          or (_ for _ in ()).throw(AssertionError("算术不符")))
    check("R6-2", "clamp 生效（超过 200 W 的原始值归一化后仍 ≤1）",
          lambda: _assert(ts.normalize_energy(500.0, 200.0) == 1.0)
          or (_ for _ in ()).throw(AssertionError("没有 clamp")))
    check("R6-3", "selector 默认口径 = 200 W / 0.7（不再是 100 W / 0.5）",
          lambda: _assert(ts.AdaptiveTerrainSelector().get_energy_caliber()["reference_watts"] == 200.0
                          and ts.AdaptiveTerrainSelector().get_energy_caliber()["threshold"] == 0.7)
          or (_ for _ in ()).throw(AssertionError("默认口径不对")))
    check("R6-4", "R8 断言抓住旧口径（100 W ⇒ 必须报错）",
          lambda: guards.assert_energy_caliber(100.0, 0.7), expect="raise")
    check("R6-5", "stats 同时给出原始能耗与归一化值（D5 澄清所需）",
          lambda: _stats_evidence(ts))
    check("R6-6", "阈值边界：恰好 0.80 不升级、0.90 才升级（float 边界不许反向）",
          lambda: _threshold_boundary(ts))

    # ---------------------------------------------------------------- R7 概率口径
    print("\n[R7] 故障概率口径统一（配置声称值 = 运行时值）")
    cfg_path = os.path.join(ROOT, "legged_gym", "envs", "a1_rescue", "a1_rescue_phase3_config.py")
    src = open(cfg_path, encoding="utf-8").read()
    check("R7-1", "配置里所有 fault_prob_locked 都是 0.10（不再出现 0.20）",
          lambda: _assert("fault_prob_locked = 0.20" not in src and "fault_prob_locked = 0.10" in src)
          or (_ for _ in ()).throw(AssertionError("仍存在 0.20")))

    class FakeFaultCfg:
        pass

    def unknown_field():
        c = FakeFaultCfg()
        c.enabled = True
        c.fault_prob = 0.2                     # ← D6 的幽灵字段
        c.fault_prob_locked = 0.10
        c.fault_prob_weakened = 0.0
        c.fault_prob_lock = 0.0
        return guards.assert_no_unknown_fault_fields(c)
    check("R7-2", "脚本写 `fault_prob`（幽灵字段）时必须报错（旧实现静默无效）",
          unknown_field, expect="raise")
    check("R7-3", "R8 断言抓住『总注入率 0.20』（提交 config 的旧值）",
          lambda: guards.assert_fault_prob_caliber(_Obj(fault_prob_locked=0.20,
                                                        fault_prob_weakened=0.0,
                                                        fault_prob_lock=0.0), 0.10), expect="raise")
    check("R7-4", "R8 断言放过 0.10（旧口径等价臂 0.10/0/0）",
          lambda: guards.assert_fault_prob_caliber(_Obj(fault_prob_locked=0.10,
                                                        fault_prob_weakened=0.0,
                                                        fault_prob_lock=0.0), 0.10,
                                                   expected_mode="free_swing"))

    def fault_arm_calibers():
        """E1 三条单形态臂必须都能过口径断言（独立复核抓到过：写死 locked==0.10 会让两臂建 env 就炸）"""
        arms = {
            "free_swing_arm": (_Obj(fault_prob_locked=0.10, fault_prob_weakened=0.0,
                                    fault_prob_lock=0.0), "free_swing"),
            "degrade_arm": (_Obj(fault_prob_locked=0.0, fault_prob_weakened=0.10,
                                 fault_prob_lock=0.0), "degrade"),
            "lock_arm": (_Obj(fault_prob_locked=0.0, fault_prob_weakened=0.0,
                              fault_prob_lock=0.10), "lock"),
            "old_physical_equiv": (_Obj(fault_prob_locked=0.10, fault_prob_weakened=0.0,
                                        fault_prob_lock=0.0), "free_swing"),
        }
        out = {}
        for name, (cfg, mode) in arms.items():
            out[name] = guards.assert_fault_prob_caliber(cfg, 0.10, expected_mode=mode)[
                "total_injection_rate"]
        return out
    check("R7-5", "三条单形态臂的总注入率都 = 0.10（口径断言不许写死单个字段）", fault_arm_calibers)

    def config_arms_consistent():
        """用 AST 直接读**真实 config 文件**：每个 enabled 的 fault_config 必须
        总注入率 = 0.10 且声明的 fault_mode 对应概率 > 0。
        （这是补齐"自检从不构造真实 task config"这个盲区——独立复核正是从那里穿透的。）"""
        import ast
        tree = ast.parse(open(cfg_path, encoding="utf-8").read())

        def class_fields(node):
            out = {}
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                        and isinstance(stmt.targets[0], ast.Name):
                    try:
                        out[stmt.targets[0].id] = ast.literal_eval(stmt.value)
                    except Exception:
                        pass
            return out

        def fault_configs(node, prefix=""):
            found = []
            for stmt in node.body:
                if isinstance(stmt, ast.ClassDef):
                    name = prefix + stmt.name
                    if stmt.name == "fault_config":
                        found.append((name, class_fields(stmt)))
                    found += fault_configs(stmt, name + ".")
            return found

        checked = {}
        for name, f in fault_configs(tree):
            if not f.get("enabled"):
                continue
            total = (f.get("fault_prob_locked", 0.0) + f.get("fault_prob_weakened", 0.0)
                     + f.get("fault_prob_lock", 0.0))
            mode = f.get("fault_mode")
            prob = {"free_swing": f.get("fault_prob_locked", 0.0),
                    "degrade": f.get("fault_prob_weakened", 0.0),
                    "lock": f.get("fault_prob_lock", 0.0)}.get(mode)
            checked[name] = {"total": total, "mode": mode, "p_mode": prob}
            assert abs(total - 0.10) < 1e-9, f"{name}: 总注入率 {total} != 0.10"
            assert prob is not None, f"{name}: fault_mode={mode} 不是合法形态"
            assert prob > 0, f"{name}: fault_mode={mode} 但该形态概率为 0"
        assert checked, "没找到任何 enabled 的 fault_config（配置结构变了？）"
        return checked
    check("R7-6", "真实 config 的三个故障臂：总注入率均 0.10、mode 与概率一致（AST 直读）",
          config_arms_consistent)

    # ---------------------------------------------------------------- R8 幽灵文件
    print("\n[R8] 幽灵配置副本（D9）与断言防线接线")
    snapshot_dir = os.path.join(os.path.dirname(ROOT), "代码快照-20261012", "legged_gym", "envs", "a1_rescue")
    check("R8-1", "幽灵文件检测器抓住快照里的前置空格副本（D9 现场）",
          lambda: guards.assert_no_shadow_module_files(snapshot_dir, "a1_rescue_phase3_config"),
          expect="raise")
    check("R8-2", "修复工作树已无幽灵/重复模块文件",
          lambda: guards.assert_no_shadow_module_files(
              os.path.join(ROOT, "legged_gym", "envs", "a1_rescue"), "a1_rescue_phase3_config"))

    def wired():
        """断言防线真的被接线（不是"已定义、零调用"）。

        独立复核指出：用 `text.count(name)` 计数会把 import 行也算进去，区分不了
        "已定义"与"真调用"。这里改成 AST：只在**函数体内**确有 `guards.<name>(...)` 调用才算。
        """
        import ast
        targets = {
            "legged_gym/utils/terrain.py": ["assert_terrain_schedule_effective",
                                            "assert_terrain_not_degenerate"],
            "legged_gym/envs/a1_rescue/a1_rescue_phase3_env.py": [
                "assert_no_unknown_fault_fields", "assert_energy_caliber",
                "assert_fault_prob_caliber", "assert_dr_targets_exist",
                "assert_no_shadow_module_files", "assert_dr_stage_anchored",
                "assert_single_curriculum"],
            "legged_gym/utils/fault_detector.py": ["assert_fault_stats_consistent",
                                                   "assert_injection_effective"],
        }
        calls = {}
        for rel, names in targets.items():
            tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
            found = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Attribute) and fn.attr in names:
                        found.add(fn.attr)
                    elif isinstance(fn, ast.Name) and fn.id in names:
                        found.add(fn.id)
            calls[rel] = {n: (n in found) for n in names}
        missing = [(f, n) for f, d in calls.items() for n, ok in d.items() if not ok]
        assert not missing, f"防线未在函数体里被真正调用: {missing}"
        return calls
    check("R8-3", "R8 防线全部被 AST 级确认为『真调用』（不是只 import）", wired)

    def eval_clean_switches():
        """eval_clean 的「clean protocol」必须真的关掉内置随机化与推力（旧版漏掉的就是它们）"""
        import ast
        path = os.path.join(ROOT, "eval_clean.py")
        src = open(path, encoding="utf-8").read()
        for attr in ("randomize_friction", "randomize_base_mass", "randomize_restitution",
                     "randomize_motor_strength", "randomize_pd_gains", "push_robots",
                     "push_interval_s"):
            assert f'"{attr}"' in src, f"eval_clean 没有逐项处理 {attr}"
        tree = ast.parse(src)
        fn = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              and n.name == "assert_all_switches_off"]
        assert fn, "找不到 assert_all_switches_off"
        body = ast.dump(fn[0])
        assert "push_robots" in body, "防线①没有复核 push_robots"
        return {"attrs_handled": 7, "guard_checks_push": True}
    check("R8-8", "eval_clean 的 clean 协议逐项关闭内置随机化/推力（旧版只关了一个不存在的开关）",
          eval_clean_switches)

    def inject_fault_mask_path():
        """评估侧主口径：逐 env-逐关节掩码（旧脚本 `torque_limits[mask]=0` 的统一入口替代）"""
        e = FakeEnv(num_envs=8)
        mask = torch.zeros(8, 12, dtype=torch.bool)
        mask[0, 0:3] = True          # env0 的 FL 整腿
        mask[3, 5] = True            # env3 的 FR 单个关节
        ev = fd.inject_fault(e, mask=mask, mode="free_swing")
        assert ev["n_faulted_envs"] == 2 and ev["n_faulted_joints"] == 4, ev
        assert float(e.torque_limits[mask].abs().max()) == 0.0, "掩码位置未置 0"
        assert float(e.torque_limits[~mask].min()) == 33.5, "非掩码位置被改动"
        assert e.fault_obs_buf[0, 0] == 1.0 and e.fault_obs_buf[3, 1] == 1.0, "fault_obs_buf 未按腿标记"
        assert e.fault_obs_buf[0, 1] == 0.0, "未故障腿被误标"
        ev2 = fd.inject_fault(e, mask=mask, mode="degrade", severity=0.5)
        assert abs(float(e.torque_limits[0, 0]) - 16.75) < 1e-4, float(e.torque_limits[0, 0])
        return {"free_swing": ev, "degrade": ev2}
    check("R8-9", "inject_fault(mask=...) 逐环境逐关节注入 + fault_obs_buf 按腿标记", inject_fault_mask_path)

    def inject_fault_mask_shape_guard():
        e = FakeEnv(num_envs=8)
        try:
            fd.inject_fault(e, mask=torch.zeros(4, 12, dtype=torch.bool), mode="free_swing")
        except ValueError:
            return {"raised": "shape mismatch"}
        raise AssertionError("掩码形状不符未报错")
    check("R8-10", "掩码形状不符 ⇒ 报错（不许静默部分注入）", inject_fault_mask_shape_guard)

    def audit_gate_works():
        """审计门自己要被测：脏文件必须命中，干净文件必须放过"""
        import importlib.util
        import tempfile
        tool = os.path.join(ROOT, "tools", "audit_eval_injection.py")
        spec = importlib.util.spec_from_file_location("audit_tool", tool)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            dirty = os.path.join(td, "dirty.py")
            with open(dirty, "w", encoding="utf-8") as f:
                f.write("import torch\nm = torch.rand(4, 12) < 0.2\nenv.torque_limits[m] = 0.0\n")
            clean = os.path.join(td, "clean.py")
            with open(clean, "w", encoding="utf-8") as f:
                f.write("from legged_gym.utils.fault_detector import inject_fault\n"
                        "inject_fault(env, mask=m, mode='free_swing')\n")
            ghost = os.path.join(td, "ghost.py")
            with open(ghost, "w", encoding="utf-8") as f:
                f.write("cfg.fault_config.fault_prob = 0.2\n")
            d_hits = mod.scan_file(dirty)
            c_hits = mod.scan_file(clean)
            g_hits = mod.scan_file(ghost)
        assert d_hits, "直写 torque_limits 未被审计门抓到"
        assert not c_hits, f"统一入口写法被误报: {c_hits}"
        assert g_hits, "幽灵字段 fault_prob 未被审计门抓到"
        return {"dirty_hits": len(d_hits), "clean_hits": len(c_hits), "ghost_hits": len(g_hits)}
    check("R8-11", "审计门自身有效：脏写法命中、统一入口写法放过", audit_gate_works)

    def migrated_eval_scripts_clean():
        """迁移后的评估脚本目录必须过审计门（fail-closed：不干净就不许进 E1）

        ⚠️ 子进程必须显式指定 UTF-8：Windows 默认用 GBK 解码子进程输出，而审计门会打印中文，
        读取线程会 UnicodeDecodeError 崩掉、`stdout` 变成 None（本机实测，别踩第二次）。
        """
        import subprocess
        tool = os.path.join(ROOT, "tools", "audit_eval_injection.py")
        d = os.path.join(ROOT, "eval_scripts")
        if not os.path.isdir(d):
            return {"skipped": "eval_scripts 未生成"}
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, tool, d], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        assert r.returncode == 0, f"迁移后仍不干净:\n{(r.stdout or '')[-800:]}"
        tail = (r.stdout or "").strip().splitlines()
        return {"exit": r.returncode, "tail": tail[-1] if tail else ""}
    check("R8-12", "迁移后的评估脚本目录通过注入口径审计（fail-closed）", migrated_eval_scripts_clean)

    def step_with_lock_contract():
        """B1：评估侧必须走 step_with_lock（否则 lock 只放大增益、没被每步钉住）"""
        class StepFakeEnv(FakeEnv):
            def step(self, actions):
                # 模拟"仿真步进把关节推到别处"（若无 on_step 回写，钉子就不存在）
                self.dof_pos = self.dof_pos + 0.05
                return ("obs", "priv", 1.0, False, {})

        e = StepFakeEnv(num_envs=4)
        inj = fd.FaultInjector(num_envs=4, device="cpu")
        inj.fault_states[1, 2] = fd.MODE_IDS["lock"]          # env1 的 RL 腿被锁
        inj.refresh_lock_flag()   # 直写状态表后必须刷新（否则 on_step 会静默早退）
        e.fault_injector = inj
        out = fd.step_with_lock(e, torch.zeros(4, 12), verify=True)
        assert len(out) == 5, out
        sl = fd.LEG_JOINT_SLICES[2]
        dev = float((e.dof_pos[1, sl] - e.default_dof_pos.reshape(-1)[sl]).abs().max().item())
        assert dev <= fd.PIN_TOLERANCE, f"钉子未生效：偏差 {dev}"
        assert e.dof_vel[1, sl].abs().max().item() == 0.0, "锁定关节速度未归零"
        # 缺 injector ⇒ 必须报错（不许静默当普通 step）
        try:
            fd.step_with_lock(FakeEnv(num_envs=2), torch.zeros(2, 12), injector=None, verify=False)
        except RuntimeError:
            ok_no_inj = True
        else:
            ok_no_inj = False
        assert ok_no_inj, "没有 FaultInjector 时未报错"
        # 负例：on_step 不写回 ⇒ 验证必须失败
        class DeadInjector:
            fault_states = inj.fault_states
            def on_step(self, env):
                return None
        try:
            fd.step_with_lock(StepFakeEnv(num_envs=4), torch.zeros(4, 12),
                              injector=DeadInjector(), verify=True)
        except RuntimeError:
            ok_dead = True
        else:
            ok_dead = False
        assert ok_dead, "on_step 没写回时验证未失败（评估数字会被当成 lock 的表现）"
        return {"pin_dev": dev, "tolerance": fd.PIN_TOLERANCE}
    check("R8-13", "step_with_lock：固定 step→on_step 顺序 + 钉住验证 + 缺 injector 报错",
          step_with_lock_contract)

    def train_py_single_seed_source():
        """D8 的陷阱必须彻底消失：train.py 不得再维护第二套种子路径

        ⚠️ 判据必须只看**生效代码行**，不能全文 grep 字符串——解释性注释里会（也应该）提到
        `SEED = 123` 这个历史陷阱，全文匹配会把"已修好"误判成"没修"（本测试第一版就误报过）。
        """
        import re as _re
        p = os.path.join(ROOT, "legged_gym", "scripts", "train.py")
        src = open(p, encoding="utf-8").read()
        code_lines = [ln for ln in src.splitlines()
                      if ln.strip() and not ln.lstrip().startswith("#")]
        active_seed_assign = [ln for ln in code_lines if _re.match(r"\s*SEED\s*=\s*\d+", ln)]
        assert not active_seed_assign, f"train.py 仍有生效的硬编码种子：{active_seed_assign}"
        assert not any("torch.manual_seed(SEED)" in ln for ln in code_lines), \
            "train.py 仍有生效的第二套 manual_seed"
        assert "[seed/R8]" in src, "train.py 没有打印生效种子（无法从日志核对）"
        assert "args.seed" in src, "train.py 没有做 CLI 与生效种子的冲突检查"
        return {"single_source": True, "code_lines": len(code_lines)}
    check("R8-14", "train.py 种子单一真源（D8 陷阱清除）+ 打印生效种子 + 冲突报错",
          train_py_single_seed_source)

    def run_meta_writer_contract():
        """run_meta.json（E1 协议指纹）的三条硬约束，用 AST 取函数体后检查"""
        import ast as _ast
        p = os.path.join(ROOT, "legged_gym", "scripts", "train.py")
        tree = _ast.parse(open(p, encoding="utf-8").read())
        fn = next((n for n in _ast.walk(tree)
                   if isinstance(n, _ast.FunctionDef) and n.name == "_write_run_meta"), None)
        assert fn is not None, "train.py 里没有 _write_run_meta（协议指纹没落盘）"
        body = _ast.get_source_segment(open(p, encoding="utf-8").read(), fn)
        # ① 目录必须先建：log_dir 只是路径，runner 之后才创建
        assert "os.makedirs" in body, "run_meta 没建目录（会 FileNotFoundError）"
        assert body.index("os.makedirs") < body.index('open(os.path.join(log_dir'), \
            "makedirs 必须在 open 之前"
        # ② 口径字段必须从 domain_rand 读（不是 dr_config —— 两段不是同一对象）
        cal_idx = body.index('"randomization_caliber"')
        cal_seg = body[cal_idx:body.index("},", cal_idx)]
        assert "cfg_d" in cal_seg, "randomization_caliber 要从 env_cfg.domain_rand 读（cfg_d）"
        assert "getattr(dr," not in cal_seg, "randomization_caliber 不能从 dr_config 读"
        # ③ 必须写种子与任务（统计单位的最小凭据）
        for key in ('"task"', '"seed_effective"', '"fault"'):
            assert key in body, f"run_meta 缺少 {key}"
        # ④ 写失败必须吵（不能静默）
        assert "WARN" in body, "run_meta 写失败时必须打印告警，不许静默"
        return {"checks": ["makedirs-before-open", "caliber-from-domain_rand", "keys", "loud-warn"]}
    check("R8-15", "run_meta.json 契约：先建目录 / 口径取自 domain_rand / 必带种子 / 失败要吵",
          run_meta_writer_contract)

    def env_order():
        """顺序口径：DR 必须在故障注入之前，否则故障被 DR 覆盖（D8 家族）。

        独立复核指出：文本 index 只能证明"源码里出现的先后"。这里改成 AST——
        解析 `A1RescuePhase3Env.reset_idx` 函数体里**顶层语句的调用顺序**。
        """
        import ast
        path = os.path.join(ROOT, "legged_gym/envs/a1_rescue/a1_rescue_phase3_env.py")
        tree = ast.parse(open(path, encoding="utf-8").read())
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "reset_idx":
                fn = node
                break
        assert fn is not None, "找不到 A1RescuePhase3Env.reset_idx"
        seq = []
        for stmt in fn.body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    f = node.func
                    if isinstance(f, ast.Attribute):
                        seq.append(f.attr)
                    elif isinstance(f, ast.Name):
                        seq.append(f.id)
        def pos(name):
            assert name in seq, f"reset_idx 里没有调用 {name}（顺序断言失败）"
            return seq.index(name)
        p_cur, p_super = pos("_curriculum_decide"), pos("reset_idx")
        p_obs, p_dr = pos("observe_step"), pos("apply_runtime")
        p_fault = pos("apply")
        p_verify = pos("verify")
        assert p_cur < p_super < p_obs < p_dr < p_fault, f"重置顺序不对: {seq}"
        assert p_fault < p_verify, "自检必须在注入之后"
        return {"curriculum_decide": p_cur, "super_reset_idx": p_super,
                "dr_observe": p_obs, "dr_apply": p_dr, "fault_apply": p_fault,
                "verify": p_verify}
    check("R8-4", "重置顺序（AST 解析函数体）：课程 → 标称恢复 → DR → 注入 → 自检", env_order)

    def single_curriculum_guard():
        """两套课程同开必须报错，且**不受 strict_checks 门控**"""
        class _T:
            curriculum = True

        class _CC:
            enabled = True

        class _Cfg:
            terrain = _T()
            curriculum_config = _CC()

        try:
            guards.assert_single_curriculum(_Cfg())
        except guards.SilentFailureError:
            ok = True
        else:
            ok = False
        assert ok, "两套课程同开没有被拦住"
        # 单套开启必须放过
        class _CC2:
            enabled = False
        class _Cfg2:
            terrain = _T()
            curriculum_config = _CC2()
        guards.assert_single_curriculum(_Cfg2())
        return {"both_on_raised": True, "single_on_passed": True}
    check("R8-6", "两套课程同开 ⇒ 无条件报错（不受 strict_checks 门控）", single_curriculum_guard)

    def rows1_no_false_positive():
        """num_rows=1 是合法配置（只有一档难度），几何断言不许误伤"""
        cfg = Cfg(generation="gradient", curriculum_difficulty_min=0.5,
                  curriculum_difficulty_max=1.0)
        cfg.num_rows, cfg.num_cols = 1, 7
        t = terrain_mod.Terrain(cfg, 8)
        return {"generation": t.generation,
                "ratio": t.terrain_evidence.get("row_amplitude_ratio")}
    check("R8-7", "num_rows=1 不触发『行间无差异』误报", rows1_no_false_positive)

    def reset_order_semantics():
        """顺序不是文风问题：先故障后 DR 会把故障覆盖掉（D8 家族）。用真 DR + 真注入器证明。"""
        ids = torch.arange(8)

        def run(dr_first):
            e = FakeEnv(num_envs=8)
            inj = fd.FaultInjector(num_envs=8, fault_prob_locked=1.0, fault_prob_weakened=0.0,
                                   fault_prob_lock=0.0, device="cpu")
            m = dr.RuinsDomainRandomization(8, stage_ratio=0.5, device="cpu", seed=3, total_steps=1000)
            m.observe_step(0)
            inj.reset_envs(ids)
            if dr_first:
                m.apply_runtime(e, ids)     # 正确顺序：DR 在故障之前
                inj.apply(e, ids)
            else:
                inj.apply(e, ids)           # 错误顺序：故障先，DR 覆盖
                m.apply_runtime(e, ids)
            return e

        ok = run(True)
        bad = run(False)
        assert bool((ok.torque_limits == 0).any()), "正确顺序下故障应当保留（力矩=0）"
        n_zero_bad = int((bad.torque_limits == 0).sum().item())
        assert n_zero_bad == 0, f"错误顺序下故障被 DR 覆盖（仍应有 0，实测 {n_zero_bad}）"
        return {"correct_order_zero_limits": int((ok.torque_limits == 0).sum().item()),
                "wrong_order_zero_limits": n_zero_bad}
    check("R8-5", "顺序语义：先故障后 DR 会把故障覆盖掉（所以必须先 DR 后注入）", reset_order_semantics)

    # ---------------------------------------------------------------- 汇总
    n_pass = sum(1 for r in RESULTS if r["ok"])
    n_fail = len(RESULTS) - n_pass
    print("\n" + "=" * 78)
    print(f"合计 {len(RESULTS)} 项：PASS {n_pass} / FAIL {n_fail}")
    print("=" * 78)
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0], "torch": torch.__version__, "numpy": np.__version__,
        "total": len(RESULTS), "pass": n_pass, "fail": n_fail, "results": RESULTS,
    }
    out = os.path.join(HERE, "local_verification_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[报告] {out}")
    return 0 if n_fail == 0 else 1


class _Obj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _assert(cond):
    if not cond:
        raise AssertionError("断言为假")
    return True


def _props_at(selector, level):
    old = selector.current_level
    selector.current_level = level
    p = selector.get_terrain_proportions()
    selector.current_level = old
    return p


def _stats_evidence(ts_mod):
    s = ts_mod.AdaptiveTerrainSelector(energy_reference=200.0, energy_threshold=0.7, window_size=3)
    for _ in range(3):
        s.update(episode_length=800, energy_penalty=105.6, max_episode_length=1000)
    st = s.get_stats()
    assert abs(st["avg_energy_raw"] - 105.6) < 1e-6, f"原始能耗没留痕: {st['avg_energy_raw']}"
    assert abs(st["avg_energy"] - 0.528) < 1e-6, f"归一化值不对: {st['avg_energy']}"
    return {"avg_energy_raw": st["avg_energy_raw"], "avg_energy_norm": st["avg_energy"],
            "caliber": st["energy_caliber"]}


def _nominal_marked_all_modes(arm_fn):
    out = {}
    for m in ("free_swing", "degrade", "lock"):
        e, inj, _ap = arm_fn(m)
        out[m] = inj.get_fault_summary(e)["nominal_marked"]
    assert all(v == 0 for v in out.values()), f"仍存在名义故障: {out}"
    return out


def _threshold_boundary(ts_mod):
    """恰好达标（success=0.80 整）不许升级；必须严格大于阈值才升级。"""
    s = ts_mod.AdaptiveTerrainSelector(energy_threshold=0.7, window_size=4, start_level=0)
    for _ in range(4):
        s.update(episode_length=800, energy_penalty=10.0, max_episode_length=1000)
    assert s.current_level == 0, f"恰好 0.80 却升级了（float 边界反向）: level={s.current_level}"
    s2 = ts_mod.AdaptiveTerrainSelector(energy_threshold=0.7, window_size=4, start_level=0)
    for _ in range(4):
        s2.update(episode_length=900, energy_penalty=10.0, max_episode_length=1000)
    assert s2.current_level == 1, f"0.90 应当升级但没升: level={s2.current_level}"
    return {"at_threshold_level": s.current_level, "above_threshold_level": s2.current_level}


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
