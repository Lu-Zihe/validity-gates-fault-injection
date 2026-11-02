#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""eval_fault.py —— R1 用的**故障场景**评估（与 eval_clean.py 的干净口径相反）。

为什么要它：eval_clean.py 的设计目标是"证明没有故障"，它有一条硬断言
`assert_no_fault_injection`，正好把 R1 需要的场景挡在门外。本脚本反过来：
**只开故障注入（lock, p=1.0），其余全关**，并**先验证故障真的落地**再评估。

用法：
    python -u eval_fault.py --task a1_rescue_fault_lock --exp_name e1_r1_aware \
        --model_dir Oct27_... --checkpoint 3000 --num_episodes 200 --tag r1_aware

产出：<save_dir>/<tag>.json（摔倒率、RMST、平均回报、注入生效证据）
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import isaacgym  # noqa: F401  必须在 torch 之前


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="a1_rescue_fault_lock")
    ap.add_argument("--exp_name", required=True)
    ap.add_argument("--model_dir", required=True)
    ap.add_argument("--checkpoint", type=int, default=3000)
    ap.add_argument("--cmd_vel", type=float, default=0.8)
    ap.add_argument("--num_envs", type=int, default=2048)
    ap.add_argument("--num_episodes", type=int, default=200)
    ap.add_argument("--fault_mode", default="lock")
    ap.add_argument("--fault_prob", type=float, default=0.10,
                    help="总注入率；必须等于配置声明值 0.10，否则 R8/D6 守卫会拦（这正是它该做的）")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--save_dir", default="/root/_r1/eval")
    args = ap.parse_args()
    args.tag = args.tag or f"{args.exp_name}_ckpt{args.checkpoint}"

    import numpy as np
    import torch
    from legged_gym.envs import task_registry
    from legged_gym.utils import get_args

    _argv = sys.argv
    sys.argv = [sys.argv[0]]
    try:
        a = get_args()
    finally:
        sys.argv = _argv
    a.task = args.task
    a.headless = True
    a.num_envs = args.num_envs
    a.seed = args.seed

    env_cfg, train_cfg = task_registry.get_cfgs(name=a.task)
    env_cfg.env.num_envs = args.num_envs
    env_cfg.seed = args.seed
    # 只开故障，其余全关（与 eval_clean 的"全关"形成对照）
    for holder in ("domain_rand", "dr_config", "curriculum_config"):
        h = getattr(env_cfg, holder, None)
        if h is not None and hasattr(h, "enabled"):
            h.enabled = False
    if hasattr(env_cfg, "terrain") and hasattr(env_cfg.terrain, "curriculum"):
        env_cfg.terrain.curriculum = False
    fc = env_cfg.fault_config
    fc.enabled = True
    fc.fault_mode = args.fault_mode
    fc.fault_prob_locked = args.fault_prob if args.fault_mode == "free_swing" else 0.0
    fc.fault_prob_weakened = args.fault_prob if args.fault_mode == "degrade" else 0.0
    fc.fault_prob_lock = args.fault_prob if args.fault_mode == "lock" else 0.0

    env, _ = task_registry.make_env(name=a.task, args=a, env_cfg=env_cfg)

    train_cfg.runner.resume = True
    train_cfg.runner.experiment_name = args.exp_name
    train_cfg.runner.load_run = args.model_dir
    train_cfg.runner.checkpoint = args.checkpoint
    runner, _ = task_registry.make_alg_runner(env=env, name=a.task, args=a, train_cfg=train_cfg)

    # ---- 注入生效证据（先验，再评）----
    inj = getattr(env, "fault_injector", None)
    n_faulted = int((inj.fault_states > 0).any(dim=1).sum().item()) if inj is not None else -1
    nominal = getattr(env, "nominal_torque_limits", None)
    if nominal is None:
        nominal = getattr(env, "nominal", None)
    tl = env.torque_limits
    changed = int((tl != nominal).any(dim=1).sum().item()) if nominal is not None else -1
    print(f"[注入证据] 故障环境数={n_faulted}/{env.num_envs}  物理量改变的环境数={changed}")
    if n_faulted <= 0:
        print("[FATAL] 一个故障都没注入，评估无意义")
        return 2

    policy = runner.get_inference_policy(device=env.device)
    obs = env.get_observations()

    max_steps = args.num_episodes * 1001
    eps_ret = []
    eps_len = []
    fall_steps = []
    cur_ret = 0.0
    t0 = time.time()
    for i in range(max_steps):
        env.commands[:, 0] = args.cmd_vel
        env.commands[:, 1] = 0.0
        env.commands[:, 2] = 0.0
        with torch.no_grad():
            actions = policy(obs.detach())
            obs, rew, _, dones, infos = env.step(actions.detach())
        timeout = infos["time_outs"]
        done_ids = dones.nonzero(as_tuple=False).flatten().tolist()
        for eid in done_ids:
            L = int(env.episode_length_buf[eid].item())
            eps_len.append(L)
            if not bool(timeout[eid]):
                fall_steps.append(L)
        if i % 2000 == 0:
            print(f"  step {i}/{max_steps} eps={len(eps_len)} falls={len(fall_steps)} {time.time()-t0:.0f}s")

    n = max(len(eps_len), 1)
    fall_rate = len(fall_steps) / n
    # RMST：存活步数（摔倒截断在 1001）
    surv = [min(1001, L) for L in eps_len]
    rmst = float(np.mean(surv)) if surv else 0.0
    res = {
        "tag": args.tag, "timestamp": datetime.now().isoformat(timespec="seconds"),
        "exp_name": args.exp_name, "model_dir": args.model_dir, "checkpoint": args.checkpoint,
        "fault_mode": args.fault_mode, "num_envs": args.num_envs,
        "n_episodes": n, "n_falls": len(fall_steps),
        "fall_rate": round(fall_rate, 4), "rmst_steps": round(rmst, 2),
        "mean_ep_len": round(float(np.mean(eps_len)) if eps_len else 0, 2),
        "n_faulted_envs": n_faulted, "n_physics_changed": changed,
        "protocol": "fault-only: lock@p=1.0, DR/curriculum OFF, 1001-step cap",
    }
    os.makedirs(args.save_dir, exist_ok=True)
    out = os.path.join(args.save_dir, f"{args.tag}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"[结果] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
