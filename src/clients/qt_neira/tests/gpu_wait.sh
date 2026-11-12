#!/bin/bash
# Очередь GPU (штаб, 10.11.2026): model-2d -> zrenie-upravlenie -> qt-dizain.
# Выходит, когда замка нет И zrenie-upravlenie его уже брал и снял; либо через 10 мин без замка и без
# zrenie (тогда спросить штаб); либо по пределу 150 мин. Итог — в gpu_wait.log.
LOCK=/d/AI/neira-repo/docs/board/GPU.lock
LOG=/d/AI/neira-tools/qt_neira/tests/gpu_wait.log
seen=0; free_min=0
echo "start $(date)" >> $LOG
for i in $(seq 1 150); do
  if [ -f "$LOCK" ]; then
    free_min=0
    if head -c 20 "$LOCK" | grep -q "zrenie-upravlenie"; then seen=1; fi
  else
    free_min=$((free_min+1))
    if [ $seen -eq 1 ]; then echo "READY: zrenie took and released the lock $(date)" >> $LOG; exit 0; fi
    if [ $free_min -ge 10 ]; then echo "NO-ZRENIE: lock free 10 min, zrenie never took it $(date)" >> $LOG; exit 0; fi
  fi
  sleep 60
done
echo "LIMIT: 150 min reached seen_zrenie=$seen $(date)" >> $LOG
