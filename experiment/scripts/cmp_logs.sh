#!/bin/bash
# 对比：旧 lock 从零训练 vs 新的 aware 训练，各自前 5 次与后 3 次打印的 Mean reward
set -u
for f in /root/legged_gym/logs/e1_lock/Oct25_03-15-43_a1_rescue_fault_lock/../../../../*; do :; done
show () {
  F=$1; TAG=$2
  echo "== $TAG : $F"
  [ -f "$F" ] || { echo "   (no file)"; return; }
  grep -a "Mean reward" "$F" | head -5
  echo "   ..."
  grep -a "Mean reward" "$F" | tail -3
}
show /root/_r1/e1_r1_aware.log AWARE_NEW
show /root/_r1/e1_r1_broken.log BROKEN_NEW
# 旧 run 的日志在 _e1b2 下（从零训练的那条）
for L in /root/_e1b2/*.log; do
  if grep -qa "e1_lock" "$L" 2>/dev/null; then show "$L" "OLD_$(basename $L)"; fi
done
