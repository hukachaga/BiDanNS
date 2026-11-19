#!/usr/bin/env bash
# A boot check of one game in BigDanNS: smoke_game.sh <title ID> <game path on the phone> [seconds, default 90]
# Starts it, waits, then prints from its own log: build, driver, frame generation, save, pad map, crashes, the last pace lines; takes a screenshot.
set -uo pipefail
id=$1; game=$2; secs=${3:-90}
ADB="${ADB:-adb}"; A="$ADB -s ${SERIAL:?}"
export MSYS_NO_PATHCONV=1
F=/sdcard/Android/data/dev.nxnative.android.bigdanns/files
W="${BDN_WORK:?}"
$A shell 'am force-stop dev.nxnative.android.bigdanns'; sleep 2
prev=$($A shell "ls -t $F/logs/$id-*.log 2>/dev/null | head -1" | tr -d '\r')
$A shell "am start -n dev.nxnative.android.bigdanns/dev.nxnative.android.MainActivity --es game '$game' --ez run true" >/dev/null
L=""; for i in $(seq 1 40); do L=$($A shell "ls -t $F/logs/$id-*.log 2>/dev/null | head -1" | tr -d '\r'); [ -n "$L" ] && [ "$L" != "$prev" ] && break; sleep 2; done
sleep "$secs"
echo "== $id  $L"
$A shell "grep -E '^\[nxlaunch\] build|\[vk\] driver:|frame generation|save: |input: DM_PAD_MAP|CRASH|FATAL|DEVICE_LOST|SIGSEGV|lmkd' '$L' | head -9" | cut -c1-200
$A shell "grep -E '\[vk\] pace up' '$L' | tail -3" | sed -E 's/.*\(([0-9.]+) s\): interval ([0-9]) [0-9]+ %; ([0-9.]+) fps; GPU busy p50\/p90 ([0-9.]+)\/([0-9.]+).*([0-9]+ draws).*/  \3 fps, GPU p50 \4 ms, \6/' | cut -c1-120
$A shell "pidof dev.nxnative.android.bigdanns:game >/dev/null && echo '  running' || echo '  NOT RUNNING'"
$A exec-out screencap -p > "$W/logs/smoke-$id.png"; echo "  shot $W/logs/smoke-$id.png"
