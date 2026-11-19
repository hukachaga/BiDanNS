#!/usr/bin/env bash
# Live A/B in a running BigDanNS game: villa_test.sh <label> <seconds> [ctl line ...]
# Sends each ctl line (e.g. "env DM_OOT_SHADOW_RANGE=200") to the app's ctl.txt, waits 6 s to settle, then summarizes the
# pace lines of the next <seconds>: fps and GPU p50 medians, draws, CPU recording.
set -euo pipefail
A="${ADB:-adb} -s ${SERIAL:?set SERIAL}"
export MSYS_NO_PATHCONV=1
F=/sdcard/Android/data/dev.nxnative.android.bigdanns/files
label=$1; secs=$2; shift 2
L=$($A shell "ls -t $F/logs/*.log | head -1" | tr -d '\r')
for line in "$@"; do $A shell "echo '$line' >> $F/ctl.txt"; done
sleep 6
n0=$($A shell "wc -l < '$L'" | tr -d '\r ')
sleep "$secs"
$A shell "tail -n +$((n0 + 1)) '$L'" | tr -d '\r' > "/tmp/villa_$label.log" || true
grep -E '\[vk\] pace up' "/tmp/villa_$label.log" | sed -E 's/.*; ([0-9.]+) fps; GPU busy p50\/p90 ([0-9.]+)\/([0-9.]+) ms.*its CPU ([0-9.]+)\), ([0-9]+) draws.*thermal ([0-9-]+).*/\1 \2 \3 \4 \5 \6/' |
  awk -v l="$label" '{f[NR]=$1; g[NR]=$2; p[NR]=$3; c[NR]=$4; d[NR]=$5; t=$6} END { if (!NR) { print l": no pace lines"; exit }
    n=asort(f); asort(g); asort(p); asort(c); asort(d); m=int((n+1)/2);
    printf "%-14s windows %d  fps %s  GPU p50 %s p90 %s ms  CPU %s ms  draws %s  thermal %s\n", l, n, f[m], g[m], p[m], c[m], d[m], t }'
grep -E 'ctl: env|gpu prof' "/tmp/villa_$label.log" | cut -c1-400 | tail -12 || true
