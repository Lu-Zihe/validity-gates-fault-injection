#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""汇总云端 21 仓库审计结果，按"判据是否适用"分类，输出 CSV + 控制台表。

适用性规则（重要）：
  - legged_gym / IsaacGym 血统：`--seed`→cfg→set_seed(env_cfg.seed) 的链路成立，C1 可判。
  - JAX / MuJoCo-MJX / Warp / config 驱动：种子走 config→PRNGKey，本工具的 C1 模型不适用，
    标 `n/a`（不是缺陷，也不是通过）。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"

# 血统/后端（人工标注，来自 repos.csv + 仓库自述）
BACKEND = {
    "iit-DLSLab/fault-locomotion-isaaclab": ("IsaacLab", "PyTorch", "legged_gym-like"),
    "google-deepmind/mujoco_playground": ("MuJoCo MJX", "JAX", "config-driven"),
    "isaac-sim/IsaacLab": ("IsaacSim/PhysX", "PyTorch", "framework"),
    "mujocolab/mjlab": ("MuJoCo Warp", "PyTorch", "config-driven"),
    "google/brax": ("Brax", "JAX", "config-driven"),
    "antonilo/rl_locomotion": ("Raisim", "PyTorch", "legged_gym-like"),
    "amazon-far/holosoma": ("IsaacSim", "PyTorch", "framework"),
    "Genesis-Embodied-AI/genesis-world": ("Genesis", "Python", "framework"),
    "DLR-RM/stable-baselines3": ("-", "PyTorch", "library"),
    "vwxyzjn/cleanrl": ("-", "PyTorch", "single-file"),
    "Toni-SM/skrl": ("multi", "multi", "library"),
    "LeCAR-Lab/ASAP": ("IsaacGym+IsaacLab", "PyTorch", "legged_gym-like"),
    "unitreerobotics/unitree_rl_mjlab": ("MuJoCo", "PyTorch", "config-driven"),
    "isaac-sim/OmniIsaacGymEnvs": ("OmniIsaacGym", "PyTorch", "framework"),
    "AgibotTech/agibot_x1_train": ("IsaacGym", "PyTorch", "legged_gym-like"),
    "LeCAR-Lab/HumanoidVerse": ("IsaacGym+IsaacLab", "PyTorch", "framework"),
    "google-deepmind/dm_control": ("MuJoCo", "Python", "library"),
    "learnsyslab/gym-pybullet-drones": ("PyBullet", "PyTorch", "gym-env"),
    "pytorch/rl": ("-", "PyTorch", "library"),
    "NVlabs/ProtoMotions": ("IsaacLab/IsaacGym", "PyTorch", "framework"),
    "limxdynamics/pointfoot-legged-gym": ("IsaacGym", "PyTorch", "legged_gym-like"),
}


def main():
    rows = []
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        name = d["name"]
        if "/" not in name and "_" in name:          # 云端目录名 owner_repo -> owner/repo
            owner, rest = name.split("_", 1)
            name = f"{owner}/{rest}"
        backend, lang, idiom = BACKEND.get(name, ("?", "?", "?"))
        c1 = d["C1_seed"]["verdict"]
        # 适用性
        if idiom in ("legged_gym-like",):
            applicable, c1v = True, c1
        elif idiom in ("framework", "library", "single-file", "gym-env"):
            applicable, c1v = False, "n/a(" + c1 + ")"
        else:  # config-driven (JAX/Warp/MJX)
            applicable, c1v = False, "n/a(" + c1 + ")"
        rows.append({
            "repo": name, "backend": backend, "lang": lang, "idiom": idiom,
            "n_py": d["n_py"], "C1_applicable": applicable, "C1": c1v,
            "C2": d["C2_eval"]["verdict"], "C3": d["C3_injection"]["verdict"],
            "C3_inject_files": len(d["C3_injection"]["injection_files"]),
        })

    import csv
    out = ROOT / "audit_21repos.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"{'repo':42s} {'backend':18s} {'C1':38s} {'C2':16s} {'C3':18s}")
    for r in rows:
        print(f"{r['repo'][:42]:42s} {r['backend'][:18]:18s} {r['C1'][:38]:38s} "
              f"{r['C2'][:16]:16s} {r['C3'][:18]:18s}")

    app = [r for r in rows if r["C1_applicable"]]
    mis = [r for r in app if r["C1"].startswith("MISROUTED")]
    print(f"\nC1 适用 {len(app)} 个，其中 MISROUTED {len(mis)} 个：{[r['repo'] for r in mis]}")
    print(f"总仓库 {len(rows)}；按血统 legged_gym-like {sum(1 for r in rows if r['idiom']=='legged_gym-like')}")


if __name__ == "__main__":
    main()
