#!/bin/bash
# 任务 2：迭代数敏感性。每臂跑 100 与 800 两个预算，产出可评估的检查点。
set -u
source /root/miniconda3/etc/profile.d/conda.sh && conda activate legged_gym
export LD_LIBRARY_PATH=/root/isaacgym/python/isaacgym/_bindings/linux-x86_64:${LD_LIBRARY_PATH:-}
export PYTHONPATH=/root/isaacgym/python:/root/legged_gym:/root/rsl_rl:${PYTHONPATH:-}
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
cd /root/legged_gym || exit 3
mkdir -p /root/_r1/sens
OUT=/root/_r1/sens/runs.txt
: > "$OUT"
BASE=Nov01_16-01-57_a1_rescue_fault_lock

one () {
  ARM=$1; BR=$2; ITERS=$3
  if [ "$BR" = "1" ]; then export R1_BROKEN_INJECTION=1; else unset R1_BROKEN_INJECTION; fi
  B=$(ls -d logs/e1_lock/*/ 2>/dev/null | sort)
  echo "[$(date +%T)] train $ARM iters=$ITERS broken=$BR"
  python -u legged_gym/scripts/train_resume.py --task a1_rescue_fault_lock --headless \
    --num_envs 4096 --max_iterations "$ITERS" --seed 42 --resume \
    --load_run "$BASE" --checkpoint 3000 > "/root/_r1/sens/${ARM}_${ITERS}.log" 2>&1
  rc=$?
  A=$(ls -d logs/e1_lock/*/ 2>/dev/null | sort)
  NEW=$(comm -13 <(echo "$B") <(echo "$A") | head -1)
  FIN=$(ls "$NEW"model_final_*.pt 2>/dev/null | head -1)
  TARGET=$((${ITERS} + 3000))
  if [ -n "$FIN" ]; then cp "$FIN" "${NEW}model_${TARGET}.pt"; fi
  echo "$ARM $ITERS $NEW $rc" >> "$OUT"
  echo "[$(date +%T)] done $ARM $ITERS rc=$rc dir=$NEW"
}

one aware 0 100
one broken 1 100
one aware 0 800
one broken 1 800

unset R1_BROKEN_INJECTION
echo "SENS_TRAIN_DONE $(date +%F' '%T)" > /root/_r1/sens/TRAIN_DONE
cat "$OUT"
