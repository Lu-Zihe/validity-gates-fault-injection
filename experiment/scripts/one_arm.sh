#!/bin/bash
# 单臂续训：one_arm.sh <SEED> <ARM> <BROKEN 0/1>
set -u
SEED=$1; ARM=$2; BROKEN=$3
source /root/miniconda3/etc/profile.d/conda.sh && conda activate legged_gym
export LD_LIBRARY_PATH=/root/isaacgym/python/isaacgym/_bindings/linux-x86_64:${LD_LIBRARY_PATH:-}
export PYTHONPATH=/root/isaacgym/python:/root/legged_gym:/root/rsl_rl:${PYTHONPATH:-}
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
cd /root/legged_gym || exit 3
mkdir -p /root/_r1/seed

BASE_RUN=Nov01_16-01-57_a1_rescue_fault_lock
EXP=e1_lock
if [ "$BROKEN" = "1" ]; then export R1_BROKEN_INJECTION=1; else unset R1_BROKEN_INJECTION; fi

BEFORE=$(ls -d logs/$EXP/*/ 2>/dev/null | sort)
echo "start seed=$SEED arm=$ARM broken=$BROKEN $(date +%T)"
python -u legged_gym/scripts/train_resume.py \
  --task a1_rescue_fault_lock --headless --num_envs 4096 \
  --max_iterations 500 --seed "$SEED" --resume \
  --load_run "$BASE_RUN" --checkpoint 3000 \
  > "/root/_r1/seed/seed${SEED}_${ARM}.log" 2>&1
RC=$?
AFTER=$(ls -d logs/$EXP/*/ 2>/dev/null | sort)
NEW=$(comm -13 <(echo "$BEFORE") <(echo "$AFTER") | head -1)
echo "$ARM $NEW $RC" >> "/root/_r1/seed/runs_seed${SEED}_par.txt"
echo "done seed=$SEED arm=$ARM rc=$RC dir=$NEW $(date +%T)"
