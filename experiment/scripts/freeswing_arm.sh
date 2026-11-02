#!/bin/bash
# 第二故障形态（free_swing）双臂对照：与主实验同基线、同预算、同评估协议。
set -u
source /root/miniconda3/etc/profile.d/conda.sh && conda activate legged_gym
export LD_LIBRARY_PATH=/root/isaacgym/python/isaacgym/_bindings/linux-x86_64:${LD_LIBRARY_PATH:-}
export PYTHONPATH=/root/isaacgym/python:/root/legged_gym:/root/rsl_rl:${PYTHONPATH:-}
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
cd /root/legged_gym || exit 3

BASE_RUN=logs/e1_lock/Nov01_16-01-57_a1_rescue_fault_lock
NEW=logs/e1_free_swing
OUT=/root/_r1/fs
mkdir -p "$NEW" "$OUT" /root/_r1/eval_fs

# 1) 把基线检查点搬进新实验目录（续训只认 logs/<exp>/<run>）
[ -d "$NEW/base_lock" ] || cp -r "$BASE_RUN" "$NEW/base_lock"

run_arm () {
  ARM=$1; BROKEN=$2
  if [ "$BROKEN" = "1" ]; then export R1_BROKEN_INJECTION=1; else unset R1_BROKEN_INJECTION; fi
  echo "start $ARM broken=$BROKEN $(date +%T)" >> "$OUT/timeline.txt"
  BEFORE=$(ls -d "$NEW"/*/ 2>/dev/null | sort)
  python -u legged_gym/scripts/train_resume.py \
    --task a1_rescue_fault_freeswing --headless --num_envs 4096 \
    --max_iterations 500 --seed 42 --resume \
    --load_run base_lock --checkpoint 3000 \
    > "$OUT/train_${ARM}.log" 2>&1
  RC=$?
  AFTER=$(ls -d "$NEW"/*/ 2>/dev/null | sort)
  DIR=$(comm -13 <(echo "$BEFORE") <(echo "$AFTER") | grep -v base_lock | head -1)
  echo "$ARM ${DIR:-NONE} $RC" >> "$OUT/runs.txt"
  echo "done $ARM rc=$RC dir=${DIR:-NONE} $(date +%T)" >> "$OUT/timeline.txt"
}

evalp () {
  DIR=$1; CK=$2; TAG=$3
  unset R1_BROKEN_INJECTION          # 关键：评估不得继承训练期的注入开关
  python -u eval_fault.py --task a1_rescue_fault_freeswing --exp_name e1_free_swing \
    --model_dir "$(basename "$DIR")" --checkpoint "$CK" --fault_mode free_swing \
    --fault_prob 0.10 --num_envs 512 --num_episodes 300 \
    --save_dir /root/_r1/eval_fs --tag "$TAG" > "$OUT/${TAG}.log" 2>&1
  echo "$TAG rc=$?" >> "$OUT/eval.txt"
}

# 2) 基线在 free_swing 下的起点（回答"换形态后基线是多少"）
evalp "$NEW/base_lock" 3000 fs_base42

# 3) 两臂续训
run_arm aware 0
run_arm broken 1

# 4) 评估
while read -r ARM DIR RC; do
  [ "$DIR" = "NONE" ] && continue
  evalp "$DIR" 3500 "fs_${ARM}"
done < "$OUT/runs.txt"

# 5) 汇总
/root/miniconda3/envs/legged_gym/bin/python - <<'PY'
import glob, json, math, os
rows = {}
for f in glob.glob("/root/_r1/eval_fs/fs_*.json"):
    d = json.load(open(f))
    rows[d["tag"]] = d
def line(tag):
    d = rows.get(tag)
    if not d: return "缺 %s" % tag
    return "%s  n=%d  falls=%d  rate=%.1f%%  rmst=%.0f" % (
        tag, d["n_episodes"], d["n_falls"], d["fall_rate"]*100, d["rmst_steps"])
for t in ("fs_base42", "fs_aware", "fs_broken"):
    print(line(t))
a, b = rows.get("fs_aware"), rows.get("fs_broken")
if a and b:
    pa, pb = a["fall_rate"], b["fall_rate"]
    sea = math.sqrt(pa*(1-pa)/a["n_episodes"]); seb = math.sqrt(pb*(1-pb)/b["n_episodes"])
    sd = math.sqrt(sea**2+seb**2); diff = (pb-pa)*100
    print("差值 %+.1f pp  95%%CI [%+.1f, %+.1f]" % (diff, diff-1.96*sd*100, diff+1.96*sd*100))
PY
echo "FS_DONE $(date +%F' '%T)" > "$OUT/FS_DONE"
