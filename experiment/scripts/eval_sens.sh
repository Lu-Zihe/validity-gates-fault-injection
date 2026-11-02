#!/bin/bash
# 任务 2 评估：等训练完成后，对 100/300/500/600/800 五个预算点各评估两臂。
set -u
source /root/miniconda3/etc/profile.d/conda.sh && conda activate legged_gym
export LD_LIBRARY_PATH=/root/isaacgym/python/isaacgym/_bindings/linux-x86_64:${LD_LIBRARY_PATH:-}
export PYTHONPATH=/root/isaacgym/python:/root/legged_gym:/root/rsl_rl:${PYTHONPATH:-}
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
unset R1_BROKEN_INJECTION
cd /root/legged_gym || exit 3

for i in $(seq 1 240); do [ -f /root/_r1/sens/TRAIN_DONE ] && break; sleep 30; done
[ -f /root/_r1/sens/TRAIN_DONE ] || { echo "训练未完成，退出"; exit 1; }

# 解析训练产出：ARM ITERS DIR RC
declare -A D100 D800
while read -r ARM ITERS DIR RC; do
  [ "$ITERS" = "100" ] && D100[$ARM]=$DIR
  [ "$ITERS" = "800" ] && D800[$ARM]=$DIR
done < /root/_r1/sens/runs.txt

evalp () {
  ARM=$1; DIR=$2; CK=$3; TAG=$4
  [ -z "$DIR" ] && { echo "缺 $TAG"; return; }
  D=$(basename "$DIR")
  python -u eval_fault.py --task a1_rescue_fault_lock --exp_name e1_lock \
    --model_dir "$D" --checkpoint "$CK" --num_envs 512 --num_episodes 300 \
    --tag "$TAG" > "/root/_r1/sens/${TAG}.log" 2>&1
  echo "$TAG rc=$?"
}

for ARM in aware broken; do
  evalp $ARM "${D100[$ARM]:-}" 3100 "sens100_${ARM}"
  evalp $ARM "${D800[$ARM]:-}" 3300 "sens300_${ARM}"
  evalp $ARM "${D800[$ARM]:-}" 3600 "sens600_${ARM}"
  evalp $ARM "${D800[$ARM]:-}" 3800 "sens800_${ARM}"
done

# 500 迭代用已有目录
evalp aware  "logs/e1_lock/Nov01_18-41-55_a1_rescue_fault_lock/" 3500 "sens500_aware"
evalp broken "logs/e1_lock/Nov01_19-01-02_a1_rescue_fault_lock/" 3500 "sens500_broken"

echo "SENS_DONE $(date +%F' '%T)" > /root/_r1/sens/SENS_DONE
/root/miniconda3/envs/legged_gym/bin/python - <<'PY'
import glob, json, math
rows = {}
for f in glob.glob("/root/_r1/eval/sens*_*.json"):
    d = json.load(open(f))
    tag = d["tag"]
    rows[tag] = (d["n_episodes"], d["n_falls"], d["fall_rate"], d["rmst_steps"])
for it in (100, 300, 500, 600, 800):
    a = rows.get("sens%d_aware" % it); b = rows.get("sens%d_broken" % it)
    if not a or not b:
        print(it, "缺"); continue
    pa, pb = a[2], b[2]
    sea = math.sqrt(pa*(1-pa)/a[0]); seb = math.sqrt(pb*(1-pb)/b[0])
    sd = math.sqrt(sea**2+seb**2); diff = (pb-pa)*100
    print("%4d iter  aware %.1f%%  broken %.1f%%  diff %+.1f [%+.1f, %+.1f]  RMST %.0f/%.0f" % (
        it, pa*100, pb*100, diff, diff-1.96*sd*100, diff+1.96*sd*100, a[3], b[3]))
PY
