#!/usr/bin/env bash
# One automated Castle Town run on BigDanNS: bench_route.sh <label> [override.spv]
# Starts Ocarina of Time with the base environment + the recorded route (DM_KEYS=@rota-castelo.keys) [+ DM_VK_SPV_OVERRIDE of b1f06157308e3b22 by the
# given module], waits until the route's last step has played, settles, then measures: pace (villa_test.sh) and the per-vertex cost of the character vertex
# shader (DM_VK_GPUPROF_SPLIT), and takes a screenshot. Needs SERIAL, GAME_NUP and BDN_WORK (the folder with env-0400486024DEC000.txt.base).
set -euo pipefail
label=$1; ovr=${2:-}
HERE="$(cd "$(dirname "$0")" && pwd)"
W="${BDN_WORK:?}"
ADB="${ADB:-adb}"; A="$ADB -s ${SERIAL:?}"
export MSYS_NO_PATHCONV=1
F=/sdcard/Android/data/dev.nxnative.android.bigdanns/files; FS=/storage/emulated/0/Android/data/dev.nxnative.android.bigdanns/files
G="${GAME_NUP:?set GAME_NUP to the game's .nup or folder on the phone}"
END_FRAME=${END_FRAME:-9400}
env=$(mktemp); cat "$W/env-0400486024DEC000.txt.base" > "$env"; echo "DM_KEYS=@$FS/${ROUTE:-rota-castelo-praca.keys}" >> "$env"
[ -n "${BENCH_EXTRA:-}" ] && printf '%s\n' $BENCH_EXTRA >> "$env"   # extra KEY=value lines (space-separated)
if [ -n "$ovr" ]; then
  $A push "$ovr" "$F/spv/bench.spv" >/dev/null
  echo "DM_VK_SPV_OVERRIDE=$FS/spv/b1f06157_orig.spv:$FS/spv/bench.spv" >> "$env"
fi
$A push "$(cygpath -m "$env")" "$F/env-0400486024DEC000.txt" >/dev/null; rm -f "$env"
$A shell 'am force-stop dev.nxnative.android.bigdanns'; sleep 2
prev=$($A shell "ls -t $F/logs/*.log 2>/dev/null | head -1" | tr -d '\r')
$A shell "am start -n dev.nxnative.android.bigdanns/dev.nxnative.android.MainActivity --es game '$G' --ez run true" >/dev/null
for i in $(seq 1 60); do   # this run's own log
  L=$($A shell "ls -t $F/logs/*.log | head -1" | tr -d '\r'); [ "$L" != "$prev" ] && break; sleep 2
done
f=0
for i in $(seq 1 150); do
  f=$($A shell "grep -oE 'pace up to frame [0-9]+' '$L' | tail -1" | tr -dc 0-9)
  [ "${f:-0}" -ge "$END_FRAME" ] && break; sleep 10
done
echo "$label: route done at frame ${f:-?}"
L=$($A shell "ls -t $F/logs/*.log | head -1" | tr -d '\r'); echo "log $L"
$A shell "grep -E 'spv override|CRASH|FATAL|DEVICE_LOST' '$L' | head -3"
sleep 8
"$HERE/villa_test.sh" "${label}_pace" 20 | head -1
"$HERE/villa_test.sh" "${label}_split" 14 "env DM_VK_GPUPROF_SPLIT=1" "env DM_VK_GPUPROF=60" > /dev/null
$A shell "echo 'env DM_VK_GPUPROF=0' >> $F/ctl.txt; echo 'env DM_VK_GPUPROF_SPLIT=0' >> $F/ctl.txt"
T=$(cygpath -m /tmp)
"$W/venv/Scripts/python.exe" -I - "$T/villa_${label}_split.log" <<'EOF'
import re, sys
from collections import defaultdict
vs = defaultdict(lambda: [0, 0, 0.0])
for l in open(sys.argv[1], encoding='utf-8', errors='replace'):
    m = re.search(r'gpu prof split:  v ([0-9a-f]+)/([0-9a-f]+) x(\d+) \((\d+) vertices\): ([0-9.]+) ms', l)
    if m: v = vs[m.group(1)]; v[0] += int(m.group(3)); v[1] += int(m.group(4)); v[2] += float(m.group(5))
b, o = vs['b1f06157308e3b22'], vs['ab00a7150d4383ac']
print('b1f06157 us/vertex %.3f (draws %d) | reference ab00a715 us/vertex %.4f | ratio %.1f' % (1000 * b[2] / max(b[1], 1), b[0], 1000 * o[2] / max(o[1], 1), (b[2] / max(b[1], 1)) / max(o[2] / max(o[1], 1), 1e-9)))
EOF
$A exec-out screencap -p > "$W/logs/shot-$label.png"; echo "shot $W/logs/shot-$label.png"
