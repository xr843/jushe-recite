#!/usr/bin/env bash
# 并行跑多品强制对齐：每品一个独立 align.py 进程（缓存按品命名，互不干扰），
# 同时最多 MAX 个并发，跑满即等一个结束再起下一个。
# 用法: ./align_parallel.sh 4 世间 业 随眠 贤圣 智 定
set -u
cd "$(dirname "$0")"
MAX="${1:-4}"; shift
PY=.venv/bin/python

running=0
for pin in "$@"; do
  # 已有对齐结果则跳过（断点续跑）
  if [ -f "aligned_${pin}.json" ]; then
    echo "[$pin] 已有 aligned_${pin}.json，跳过"
    continue
  fi
  while [ "$(jobs -rp | wc -l)" -ge "$MAX" ]; do wait -n; done
  echo "[$pin] 启动对齐 → align_${pin}.out"
  "$PY" align.py "$pin" > "align_${pin}.out" 2>&1 &
done
wait
echo "=== 全部并行任务结束 ==="
for pin in "$@"; do
  if [ -f "aligned_${pin}.json" ]; then
    echo "[$pin] ✓ $(grep -h '命中' align_${pin}.out 2>/dev/null | tail -1)"
  else
    echo "[$pin] ✗ 未生成 aligned_${pin}.json，见 align_${pin}.out"
  fi
done
