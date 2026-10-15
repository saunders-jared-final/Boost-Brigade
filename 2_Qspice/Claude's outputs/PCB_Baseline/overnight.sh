#!/bin/bash
# Gate-4 overnight report matrix: simulate, measure (s10_metrics.py), drop the .qraw (C: is nearly full)
cd "$(dirname "$0")"
for st in S10xb S10xp; do
  echo "[$(date +%H:%M)] $st"
  cmd.exe /c sim_only.bat $st
  python3 s10_metrics.py $st > results/$st.summary.txt 2>&1 && rm -f stages/$st.qraw
  tail -1 results/$st.sim.txt
done
echo "[$(date +%H:%M)] done"
