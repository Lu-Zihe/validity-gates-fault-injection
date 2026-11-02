"""
silent_failure_guards.py — R8(2026-10-12)：把「静默失效」变成「报错」

背景（论文第二支柱）：本项目的缺陷族统一形态是
    「配置里写的值 ≠ 代码实际执行的值」
而且它的**传播机制**是不报错的降级：`hasattr` 守卫、被写死的开关、
取整后为 0 的采样、参数传错槽位后被守卫挡住、同名幽灵文件被 grep 命中。

D1–D9 九种形态里，**八种的共同点是「错得很安静」**。所以真正的修复不是
把每一处改对（那只能修当下这一处），而是让「再次变安静」变成不可能——
即把每个关键不变量写成 fail-closed 断言，在启动/步进时立刻炸掉。

本模块的每个断言都：
  1) 只在**违反不变量**时报错（不误伤合法配置）
  2) 报错信息里带上**实测值与期望值**（可当运行时证据直接抄进实验记录）
  3) 返回**证据字典**，供自检脚本打印（零 GPU 也能验）

命名约定：assert_*（违反即 raise SilentFailureError）
"""

import os

__all__ = [
    "SilentFailureError",
    "assert_no_shadow_module_files",
    "assert_terrain_not_degenerate",
    "assert_terrain_schedule_effective",
    "assert_dr_targets_exist",
    "assert_dr_stage_anchored",
    "assert_dr_authority",
    "assert_injection_effective",
    "assert_fault_stats_consistent",
    "assert_energy_caliber",
    "assert_fault_prob_caliber",
    "assert_no_unknown_fault_fields",
    "assert_single_curriculum",
]

# A1 机器人：4 腿 × 3 关节
NUM_LEGS = 4
JOINTS_PER_LEG = 3
NUM_JOINTS = NUM_LEGS * JOINTS_PER_LEG


def assert_single_curriculum(cfg):
    """断言只有一个课程调度器在写 `terrain_levels`。

    两套课程（legged_gym 原生 `terrain.curriculum`：按行走距离升降级；本项目双指标
    `AdaptiveTerrainSelector`）如果同时开启，会**先后写同一个 terrain_levels**：
    选择器先按等级写 level/origins，随后 `_update_terrain_curriculum` 再按距离改写
    ⇒ `terrain_levels` 与 `env_origins` 指向不同行。这种冲突不报错、只表现为数字变差，
    属于本项目的缺陷族原型，所以**无条件报错**（不受 strict_checks 门控：
    配置层的自相矛盾不是"数值校核"，没有"调试时先放过"的正当理由）。
    """
    tc = getattr(cfg, "terrain", None)
    cc = getattr(cfg, "curriculum_config", None)
    native = bool(getattr(tc, "curriculum", False)) if tc is not None else False
    selector = bool(getattr(cc, "enabled", False)) if cc is not None else False
    if native and selector:
        raise SilentFailureError(
            "[R8/R2] 两套课程同时开启：cfg.terrain.curriculum=True（legged_gym 按行走距离升降级）"
            " 与 curriculum_config.enabled=True（双指标选择器）会互相覆盖 terrain_levels。"
            "请显式只留一套。")
    return {"native_curriculum": native, "selector_curriculum": selector}


class SilentFailureError(RuntimeError):
    """违反「配置声称值 = 实际执行值」不变量时抛出。

    故意不继承 AssertionError：python -O 会把 assert 全部剥掉，
    而这条防线不允许被剥掉（它在提交包里必须永远生效）。
    """
    pass


def _fmt(x):
    return x if isinstance(x, str) else repr(x)


# ---------------------------------------------------------------- D9 幽灵文件
def assert_no_shadow_module_files(directory, module_basename="a1_rescue_phase3_config"):
    """同一目录下不允许存在「去掉首尾空格后同名」的其他 .py 文件。

    D9 实况：`legged_gym/envs/a1_rescue/ a1_rescue_phase3_config.py`（名字带**前导空格**，
    Aug 29 的旧版本，8003 B）与真正的 `a1_rescue_phase3_config.py`（6912 B）并存。
    `grep 关键字` 会命中前者，于是「版本核实」得出相反结论（同一个问题判了三次，前两次都错）。

    Returns:
        dict: {'checked': [...], 'shadow': [...]}
    """
    if not os.path.isdir(directory):
        raise SilentFailureError(f"[R8/shadow] 目录不存在: {directory}")

    canonical = module_basename + ".py"
    shadow = []
    seen = {}
    for name in os.listdir(directory):
        if not name.endswith(".py"):
            continue
        stripped = name.strip()
        if stripped != name:
            shadow.append((name, stripped, "首尾空白"))
        seen.setdefault(stripped, []).append(name)
    for stripped, names in seen.items():
        if len(names) > 1:
            shadow.append((names, stripped, "同名多份"))

    if shadow:
        detail = "; ".join(f"{_fmt(s[0])} ≡ {_fmt(s[1])} ({s[2]})" for s in shadow)
        raise SilentFailureError(
            "[R8/shadow] 检测到幽灵/重复模块文件，任何基于文件名或 grep 的版本核实都会失真："
            f"{detail}。请删除或改名后再运行。")
    return {"checked": directory, "canonical": canonical, "shadow": []}


# ---------------------------------------------------------------- D1 课程空转
def assert_terrain_schedule_effective(schedule, require_rows_vary=True):
    """断言课程调度表真的产生了「行间难度差」与「列间生成器差」。

    D1 实况：8 行 difficulty 全 0.5、choice 全 6 ⇒ 课程等级只改写一个索引，
    而索引指向的地图几何完全相同 ⇒ 对训练分布的因果影响为 0（且完全静默）。

    Returns:
        dict: 证据（难度档数、生成器数、每档取值）
    """
    if not schedule:
        raise SilentFailureError("[R8/D1] 课程调度表为空 ⇒ 地形生成什么都不会发生")

    diffs = sorted({round(float(d), 6) for (_i, _j, _c, d) in schedule})
    choices = sorted({int(c) for (_i, _j, c, _d) in schedule})
    rows = {}
    for (i, _j, _c, d) in schedule:
        rows.setdefault(int(i), set()).add(round(float(d), 6))

    evidence = {
        "n_tiles": len(schedule),
        "distinct_difficulties": diffs,
        "distinct_choices": choices,
        "row_difficulty_counts": {k: len(v) for k, v in sorted(rows.items())},
    }

    n_rows = len(rows)
    n_cols = len({int(j) for (_i, j, _c, _d) in schedule})
    # 单行配置（num_rows=1）没有"行间"可比：难度只有一档是合法的，不算 D1。
    if require_rows_vary and n_rows >= 2:
        if len(diffs) < 2:
            raise SilentFailureError(
                "[R8/D1] 所有瓦片难度相同 ⇒ 「课程/难度梯度」对训练分布无因果影响"
                f"（实测难度取值={diffs}）。这正是 D1 的形态：写得对、跑得动、效果为 0。")
        multi = {k: v for k, v in rows.items() if len(v) > 1}
        if multi:
            raise SilentFailureError(
                f"[R8/D1] 同一行内出现多个难度值 ⇒ 行不再是难度档：{multi}")
    if n_cols > 1 and len(choices) < 2:
        raise SilentFailureError(
            f"[R8/D1] {n_cols} 个地形列共用同一个生成器 ⇒ 多种地形实际只有 1 种"
            f"（实测 choice={choices}）")
    return evidence


def assert_terrain_not_degenerate(terrain, generation, min_row_amplitude_ratio=1.05):
    """在 Terrain 实例上做**几何级**复核：难度梯度必须真的改变高度场幅度。

    D1 实况：`difficulty` 恒 0.5、`choice` 恒 6 ⇒ 8 行瓦片的**参数完全相同**。
    注意：不能要求瓦片逐字节相同（随机细节起伏使它们本来就不逐字节相同）——
    旧实现在这一点上"看起来有差异"，所以按行幅度判：gradient 模式下最难行/最易行的
    平均高度必须拉开 ≥min_row_amplitude_ratio 倍，否则判定梯度没有落到高度场。

    门槛的取法（独立复核提的误伤风险）：默认放到 **1.05**——纯粹"没有梯度"时该比值
    在噪声下才 ~1.0，而真梯度（difficulty 0.5→1.0，多个生成器幅度随难度线性放大）
    应当明显更大。**num_rows < 2 时跳过判定**（单行配置本来就没有"行间"可比）。
    实测比值总是随 evidence 返回，便于在真 isaacgym 上核对。
    """
    field = getattr(terrain, "height_field_raw", None)
    if field is None:
        raise SilentFailureError("[R8/D1] Terrain 上没有 height_field_raw")

    lx = int(getattr(terrain, "length_per_env_pixels", 0))
    ly = int(getattr(terrain, "width_per_env_pixels", 0))
    border = int(getattr(terrain, "border", 0))
    rows = int(getattr(terrain.cfg, "num_rows", 0))
    cols = int(getattr(terrain.cfg, "num_cols", 0))
    if min(lx, ly, rows, cols) <= 0:
        raise SilentFailureError(
            f"[R8/D1] 地形尺寸信息不完整: lx={lx} ly={ly} rows={rows} cols={cols}")

    # 用「整块瓦片的高度场和」做判重（int16，和相同 ⇒ 同几何）
    tile_sums = {}
    for i in range(rows):
        for j in range(cols):
            block = field[border + i * lx: border + (i + 1) * lx,
                          border + j * ly: border + (j + 1) * ly]
            tile_sums[(i, j)] = int(block.sum())

    distinct = len(set(tile_sums.values()))
    # ⚠️ 判据说明（重要）：**不能**用「瓦片几何是否逐字节相同」判 D1。
    # 因为旧实现里 choice 恒为 composite_slope，它的细节起伏是随机生成的 ⇒
    # 即使 difficulty 全为 0.5，56 块瓦片也不会逐字节相同，这个判据会漏掉 D1。
    # D1 的真正特征是「难度参数不随行变化 ⇒ 行间幅度无差异」。因此按**行幅度**判：
    row_amp = []
    for i in range(rows):
        amps = []
        for j in range(cols):
            block = field[border + i * lx: border + (i + 1) * lx,
                          border + j * ly: border + (j + 1) * ly]
            amps.append(float(abs(block.astype("float64")).mean()))
        row_amp.append(sum(amps) / max(1, len(amps)))

    evidence = {
        "generation": generation,
        "n_tiles": rows * cols,
        "distinct_heightfield_sums": distinct,
        "row_mean_abs_height": [round(a, 3) for a in row_amp],
        "row_amplitude_ratio": (round(max(row_amp) / min(row_amp), 3)
                                if min(row_amp) > 0 else None),
    }

    if generation in ("gradient", "randomized") and max(row_amp) <= 0.0:
        raise SilentFailureError(
            "[R8/D1] 高度场全为 0（平地）⇒ 地形生成器实际什么都没做，"
            f"课程/随机化对分布无效。generation={generation}")

    if generation == "gradient" and rows >= 2:
        # 难度从 min 阶梯升到 max，行间幅度必须拉开（≥ min_row_amplitude_ratio 倍）
        if min(row_amp) <= 0.0:
            ratio = float('inf')
        else:
            ratio = max(row_amp) / min(row_amp)
        if ratio < min_row_amplitude_ratio:
            raise SilentFailureError(
                f"[R8/D1] generation='gradient' 但行间地形幅度几乎没差别"
                f"（最难行/最易行 = {ratio:.3f}，要求 ≥{min_row_amplitude_ratio}）"
                f"⇒ 难度梯度没有真正作用于高度场。行均值={evidence['row_mean_abs_height']}")
    return evidence


# ---------------------------------------------------------------- D2 域随机化死代码
def assert_dr_targets_exist(env, required=("gym", "envs", "actor_handles", "torque_limits")):
    """断言域随机化真正要写的载体存在。

    D2 实况：`domain_randomization.py` 三处写入全被 `hasattr` 守卫
    （`env.robot`、`env.motor_strength` 根本不存在）⇒ 静默跳过、不报错，
    「8 维两阶段废墟 DR」实际从未作用于仿真。

    真实载体（legged_gym）：
      friction → `gym.get/set_actor_rigid_shape_properties(envs[i], actor_handles[i])`
      base_mass → `gym.get/set_actor_rigid_body_properties(...)`
      motor_strength → `env.torque_limits`（2D，标称值×系数）

    本断言把「载体缺失」从静默跳过改成启动即报错。
    """
    missing = [a for a in required if not hasattr(env, a)]
    if missing:
        raise SilentFailureError(
            f"[R8/D2] 域随机化的写入载体不存在: {missing}。"
            "legged_gym 里摩擦/质量走 gym 的 rigid shape/body properties，"
            "电机强度走 env.torque_limits —— 不存在 env.robot 或 env.motor_strength，"
            "用 hasattr 守卫跳过它们只是把缺陷藏起来。")
    return {"checked_attrs": list(required)}


def assert_dr_stage_anchored(mgr):
    """断言两阶段域随机化**有锚点**。

    R3 续修实况：`set_total_training_iters()` 在旧代码里**全项目零调用**
    ⇒ `total_iters=None` ⇒ `_get_stage()` 永远返回 'small'
    ⇒ 「后 50% 大范围随机化」从未发生（而且 current_iter 是在每次调用里自增，
       计数单位是 reset 次数，不是训练迭代）。
    没有锚点的两阶段策略 = 名存实亡，必须报错而不是静默。
    """
    if not getattr(mgr, "is_stage_anchored", lambda: False)():
        raise SilentFailureError(
            "[R8/D2] 两阶段域随机化没有锚点（total_steps 未设置）⇒ 阶段将永远停在 'small'，"
            "「后 50% 大范围随机化」不会发生。请在 dr_config 里设 "
            "total_steps = max_iterations × num_steps_per_env。")
    return {"total_steps": mgr.total_steps, "stage_ratio": mgr.stage_ratio}


def assert_dr_authority(mgr, domain_rand_cfg):
    """断言「每个运行时随机化维只有一个真源」。

    实况（2026-10-12 云端一手核实）：`domain_rand` **没有 `enabled` 字段**，内置
    `randomize_friction=True` / `randomize_base_mass=True` / `push_robots=True` 都是默认值；
    而 `eval_clean.py` 的"四开关全关"只关 `dr_config/curriculum/fault` + 一个不存在的
    `domain_rand.enabled` ⇒ **建 env 期的摩擦/质量随机化与周期推力从未被关掉**，
    却让评估自称"clean protocol"。同一维被两套机制写 = 论文口径说不清。

    这里按 authority 逐维核对：谁是真源，另一套必须真的关掉。
    """
    auth = getattr(mgr, "authority", {})
    evidence = {"authority": dict(auth)}

    # 摩擦
    if auth.get('friction') == 'ruins_dr' and getattr(domain_rand_cfg, 'randomize_friction', False):
        raise SilentFailureError(
            "[R8/D2] authority['friction']='ruins_dr' 但 domain_rand.randomize_friction=True "
            "⇒ 建 env 时写一次 + 每次 reset 再写一次，两个真源。请把 randomize_friction 设为 False。")
    if auth.get('friction') == 'builtin' and not getattr(domain_rand_cfg, 'randomize_friction', False):
        raise SilentFailureError(
            "[R8/D2] authority['friction']='builtin' 但 randomize_friction=False ⇒ 摩擦根本没有随机化。")

    # 基座质量（论文的 ±1 kg 载荷口径在内置里）
    if auth.get('base_mass') == 'builtin' and not getattr(domain_rand_cfg, 'randomize_base_mass', False):
        raise SilentFailureError(
            "[R8/D2] authority['base_mass']='builtin' 但 randomize_base_mass=False "
            "⇒ 载荷随机化不存在（论文的 ±1 kg 口径会落空）。")
    if auth.get('base_mass') == 'ruins_dr' and getattr(domain_rand_cfg, 'randomize_base_mass', False):
        raise SilentFailureError(
            "[R8/D2] authority['base_mass']='ruins_dr' 但 randomize_base_mass=True ⇒ 质量有两个真源。")

    # 电机强度（内置没有对应开关，存在即冲突）
    if auth.get('motor_strength') == 'ruins_dr' and \
            getattr(domain_rand_cfg, 'randomize_motor_strength', False):
        raise SilentFailureError(
            "[R8/D2] authority['motor_strength']='ruins_dr' 但 domain_rand.randomize_motor_strength=True "
            "⇒ 电机强度有两个真源。")

    # 推力：与本模块无关，但它是 eval「clean」失真的同伙 → 要求显式声明
    push_s = getattr(domain_rand_cfg, 'push_interval_s', None)
    push_on = getattr(domain_rand_cfg, 'push_robots', None)
    if push_on and (push_s is None or float(push_s) <= 0):
        raise SilentFailureError(
            f"[R8/D2] push_robots=True 但 push_interval_s={push_s}（<=0）⇒ "
            "旧实现里 `push_interval = ceil(push_interval_s/dt)` 会是负数，"
            "而 `common_step_counter % 负数 == 0` 仍然每隔 |push_interval| 步触发即"
            "『写了关闭推力、实际还在推』。请二选一：push_robots=False 或给正数间隔。")
    evidence['push_robots'] = push_on
    evidence['push_interval_s'] = push_s
    return evidence


# ---------------------------------------------------------------- D3/D4 注入生效与统计口径
def assert_injection_effective(env, env_ids, mode, before, after, severity=None, joints=None,
                               label=None):
    """断言「被标记为故障的环境」其物理量**真的变了**。

    D3/D4 实况：
      - `single_leg_lock` 实为 torque_limits=0 ⇒ 自由摆动（术语与物理不符）
      - `weakened` 支路因 p_gains 是 1D 直接 return ⇒ 10% 环境被标为故障却物理完全正常

    Args:
        before/after: 注入前/后的张量，形状一致 (n, k)。若要只比较部分列，先用 joints 切片
                      或直接把切好的张量传进来（joints=None 表示"全列都要变"）。
        env_ids: 行索引；**传 None 表示 before/after 已经是目标行**（评估/训练侧切片后调用）
    Returns:
        dict: 生效环境数、未生效环境数（必须为 0）
    """
    if before is None or after is None:
        raise SilentFailureError(f"[R8/D3] assert_injection_effective 缺少 before/after（mode={mode}）")
    idx = slice(None) if env_ids is None else env_ids
    if env_ids is not None and len(env_ids) == 0:
        return {"mode": mode, "n_requested": 0, "n_effective": 0}
    b = before[idx]
    a = after[idx]
    if joints is not None:
        b = b[:, joints]
        a = a[:, joints]
    changed = (b != a).any(dim=-1)
    n_req = int(b.shape[0])
    n_eff = int(changed.sum().item())
    evidence = {"mode": mode, "severity": severity, "label": label,
                "n_requested": n_req, "n_effective": n_eff}
    if n_eff != n_req:
        bad = int((~changed).sum().item())
        raise SilentFailureError(
            f"[R8/D3] 注入未生效: mode='{mode}'{(' ' + label) if label else ''} "
            f"请求 {n_req} 个环境，实际物理量变化 {n_eff} 个（未生效 {bad} 个）"
            " ⇒ 这会把「物理正常」的环境计入故障组，系统性污染分母。")
    return evidence


def assert_fault_stats_consistent(stats):
    """断言故障统计自洽：各组之和 = 总数；且「标为故障」= 「物理已改变」。

    stats 需含: total, normal, free_swing, lock, degrade, nominal_marked
      nominal_marked = 被标记为故障但物理量未变的环境数（D4 的污染量）
    """
    need = ("total", "normal", "free_swing", "lock", "degrade")
    miss = [k for k in need if k not in stats]
    if miss:
        raise SilentFailureError(f"[R8/D4] 故障统计字段缺失: {miss}")
    summation = stats["normal"] + stats["free_swing"] + stats["lock"] + stats["degrade"]
    if summation != stats["total"]:
        raise SilentFailureError(
            f"[R8/D4] 故障统计不自洽: normal+free_swing+lock+degrade={summation} != total={stats['total']}")
    nominal = int(stats.get("nominal_marked", 0))
    if nominal > 0:
        raise SilentFailureError(
            f"[R8/D4] 有 {nominal} 个环境被标记为故障但物理量未发生变化 ⇒ 故障组分母被污染"
            "（这正是 weakened 支路因 1D p_gains 直接 return 造成的形态）")
    return dict(stats)


# ---------------------------------------------------------------- D5 能耗口径
def assert_energy_caliber(energy_reference, energy_threshold,
                          expected_reference=200.0, expected_threshold=0.7,
                          clamp=(0.0, 1.0)):
    """断言归一化能耗口径与「论文声称的口径」一致。

    D5 实况：报告写「除以 200 W、阈值 ≤0.7、截断到 [0,1]」，代码是
    `energy_reference=100.0`、默认阈值 0.5、且**全文无 clamp** ⇒ 0.528 无法按论文定义复现。
    在口径统一之前，0.528 这个数**禁止引用**（16 号事实基线表 §A8/§H3）。

    Returns:
        dict: 实测口径（可直接写进实验记录）
    """
    evidence = {
        "energy_reference": float(energy_reference),
        "energy_threshold": float(energy_threshold),
        "clamp": tuple(clamp),
    }
    if abs(float(energy_reference) - float(expected_reference)) > 1e-9:
        raise SilentFailureError(
            f"[R8/D5] 归一化能耗分母 = {energy_reference}，与论文声称的 {expected_reference} W 不一致"
            " ⇒ 归一化值差 2 倍，0.528 不可复现（确认前该数字禁用）")
    if abs(float(energy_threshold) - float(expected_threshold)) > 1e-9:
        raise SilentFailureError(
            f"[R8/D5] 能耗升级阈值 = {energy_threshold}，与论文声称的 {expected_threshold} 不一致")
    if clamp is None:
        raise SilentFailureError("[R8/D5] 归一化能耗没有 clamp 到 [0,1]，与论文声称的「截断到 [0,1]」不符")
    return evidence


# ---------------------------------------------------------------- D6 概率口径
def assert_fault_prob_caliber(fault_cfg, declared_total=0.10, expected_mode=None):
    """断言**总注入强度** = 论文/配置声称值（0.10），且声明的形态真的有概率。

    D6 实况：提交 config 写 `fault_prob_locked = 0.20`，三个 GOOD 快照实跑 0.10，
    `patch_obs52.py` 运行时又写回 0.1 ⇒ 复现者按提交 config 跑会得到 2 倍注入强度。

    ⚠️ 判据必须落在**总注入率**上，不能写死某一个字段：
    R4 之后一条配置可以只开一个形态（E1 的三条对照臂就是 `0.10/0/0`、`0/0.10/0`、`0/0/0.10`），
    若把 `fault_prob_locked == 0.10` 写死，degrade/lock 两条臂会**建 env 就报错**
    （2026-10-12 独立复核抓到的真实缺陷）。
    另外交叉核对 `fault_mode` 与概率：声明 mode='lock' 却只给 free_swing 概率 = 另一种静默错配。
    """
    p_fs = float(getattr(fault_cfg, "fault_prob_locked", 0.0))
    p_dg = float(getattr(fault_cfg, "fault_prob_weakened", 0.0))
    p_lk = float(getattr(fault_cfg, "fault_prob_lock", 0.0))
    total = p_fs + p_dg + p_lk
    mode = expected_mode if expected_mode is not None else getattr(fault_cfg, "fault_mode", None)
    mode_prob = {"free_swing": p_fs, "degrade": p_dg, "lock": p_lk,
                 None: total}.get(mode, None)

    evidence = {"total_injection_rate": total, "declared_total": declared_total,
                "per_mode": {"free_swing": p_fs, "degrade": p_dg, "lock": p_lk},
                "fault_mode": mode}
    if mode is not None and mode not in ("free_swing", "degrade", "lock"):
        raise SilentFailureError(
            f"[R8/D6] fault_mode='{mode}' 不是合法形态（合法值 free_swing/lock/degrade）。"
            "注意旧名 'single_leg_lock' 在物理上是 free_swing，请改名。")
    if abs(total - float(declared_total)) > 1e-9:
        raise SilentFailureError(
            f"[R8/D6] 总注入强度 = {total:.4f}（free_swing={p_fs} + degrade={p_dg} + lock={p_lk}），"
            f"与声称值 {declared_total} 不一致"
            " ⇒ 复现者按配置跑会得到不同注入强度。")
    if mode_prob is not None and mode_prob <= 0.0:
        raise SilentFailureError(
            f"[R8/D6] fault_mode='{mode}' 但该形态的概率为 0（{evidence['per_mode']}）"
            " ⇒ 声称的故障形态与实际注入的形态不是同一个（静默错配）。")
    return evidence


def assert_no_unknown_fault_fields(fault_cfg, allowed_extra=()):
    """断言脚本没有往 fault_config 上乱塞字段。

    D6 实况：大量脚本写 `env_cfg.fault_config.fault_prob = 0.2`，
    而代码读的是 `fault_prob_locked` ⇒ 注入强度不受控且**不报错**（Python 允许动态加属性）。
    """
    known = {
        "enabled", "fault_mode", "fault_prob_locked", "fault_prob_weakened",
        "fault_prob_lock", "fault_prob_start", "fault_curriculum_steps",
        "velocity_threshold", "consecutive_frames", "degrade_severity",
        "lock_stiffness_scale", "strict_checks", "declared_total",
    }
    known |= set(allowed_extra)
    fields = {k for k in vars(fault_cfg) if not k.startswith("_")}
    unknown = sorted(fields - known)
    if unknown:
        raise SilentFailureError(
            f"[R8/D6] fault_config 上出现未知字段 {unknown} ⇒ 它们不会被任何代码读取"
            "（例如 fault_prob 是废弃名，代码读 fault_prob_locked）。请改名或删除，不要让它静默存在。")
    return {"fields": sorted(fields)}
