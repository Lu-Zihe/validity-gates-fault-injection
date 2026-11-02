#!/bin/bash
# 种子实验：对 SEED 分别跑 aware / broken 两臂，各续训 500 迭代，然后评估。
# 用法：bash rr_seed.sh <SEED>
set -u
SEED=${1:?need seed}
source /root/miniconda3/etc/profile.d/conda.sh && conda activate legged_gym
export LD_LIBRARY_PATH=/root/isaacgym/python/isaacgym/_bindings/linux-x86_64:${LD_LIBRARY_PATH:-}
export PYTHONPATH=/root/isaacgym/python:/root/legged_gym:/root/rsl_rl:${PYTHONPATH:-}
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
cd /root/legged_gym || exit 3
mkdir -p /root/_r1/seed

BASE_RUN=Nov01_16-01-57_a1_rescue_fault_lock
BASE_CKPT=3000
EXP=e1_lock
OUT=/root/_r1/seed/runs_seed${SEED}.txt
: > "$OUT"

echo "=== seed $SEED start $(date +%F' '%T) ==="

run () {
  ARM=$1; BROKEN=$2
  if [ "$BROKEN" = "1" ]; then export R1_BROKEN_INJECTION=1; else unset R1_BROKEN_INJECTION; fi
  BEFORE=$(ls -d logs/$EXP/*/ 2>/dev/null | sort)
  echo "--- seed=$SEED arm=$ARM broken=$BROKEN start $(date +%T)"
  python -u legged_gym/scripts/train_resume.py \
    --task a1_rescue_fault_lock --headless --num_envs 4096 \
    --max_iterations 500 --seed "$SEED" --resume \
    --load_run "$BASE_RUN" --checkpoint "$BASE_CKPT" \
    > "/root/_r1/seed/seed${SEED}_${ARM}.log" 2>&1
  RC=$?
  AFTER=$(ls -d logs/$EXP/*/ 2>/dev/null | sort)
  NEW=$(comm -13 <(echo "$BEFORE") <(echo "$AFTER") | head -1)
  echo "$ARM $NEW $RC" >> "$OUT"
  echo "--- seed=$SEED arm=$ARM rc=$RC dir=$NEW end $(date +%T)"
}

run aware 0
run broken 1

# 评估两个新目录
echo "=== seed $SEED eval $(date +%T) ==="
while read -r ARM DIR RC; do
  D=$(basename "$DIR")
  python -u eval_fault.py --task a1_rescue_fault_lock --exp_name "$EXP" \
    --model_dir "$D" --checkpoint 3500 --num_envs 512 --num_episodes 300 \
    --tag "seed${SEED}_${ARM}" > "/root/_r1/seed/seed${SEED}_${ARM}_eval.log" 2>&1
  echo "$ARM eval rc=$? $(date +%T)"
done < "$OUT"

echo "SEED${SEED}_DONE $(date +%F' '%T)" > "/root/_r1/seed/SEED${SEED}_DONE"
cat "$OUT"
