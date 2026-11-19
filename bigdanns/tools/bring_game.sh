#!/usr/bin/env bash
# Bring one game from the official Banana Native app into BigDanNS, through BigDanNS itself (so its files are its own):
#   bring_game.sh <title ID> <game path on the phone (.nup or dump folder)>
# 1. the official pack copied to /sdcard/BigDanNS-import/<id>, 2. the official save put where BigDanNS copies an old save from once
# (<folder holding the game>/saves-test/<id>, SaveMigrate), 3. the game added with that pack (--es game --es pack), 4. the pack imported into
# BigDanNS's own storage (pack_title / pack_import, test app), 5. the staging copy removed. The official app's files are only read.
set -euo pipefail
id=$1; game=$2
ADB="${ADB:-adb}"; A="$ADB -s ${SERIAL:?}"
export MSYS_NO_PATHCONV=1
O=/sdcard/Android/data/dev.bananative.android/files; N=/sdcard/Android/data/dev.nxnative.android.bigdanns/files
APP=dev.nxnative.android.bigdanns/dev.nxnative.android.MainActivity
parent=$(dirname "$game")
$A shell "mkdir -p /sdcard/BigDanNS-import && rm -rf /sdcard/BigDanNS-import/$id && cp -r $O/packs/$id /sdcard/BigDanNS-import/ && du -sh /sdcard/BigDanNS-import/$id"
if $A shell "[ -d $O/saves/$id ]"; then
  $A shell "mkdir -p '$parent/saves-test' && [ ! -e '$parent/saves-test/$id' ] && cp -r $O/saves/$id '$parent/saves-test/' ; ls '$parent/saves-test/$id' | head -3" || true
fi
$A shell "am start -n $APP --es game '$game' --es pack /sdcard/BigDanNS-import/$id" >/dev/null; sleep 6
$A shell "am start -n $APP --es pack_title $id --es pack_import /sdcard/BigDanNS-import/$id" >/dev/null
for i in $(seq 1 60); do
  s=$($A shell "du -s $N/packs/$id 2>/dev/null" | cut -f1 | tr -dc 0-9); t=$($A shell "du -s /sdcard/BigDanNS-import/$id" | cut -f1 | tr -dc 0-9)
  if [ "${s:-0}" -ge "$(( ${t:-1} * 98 / 100 ))" ]; then break; fi; sleep 5
done
sleep 4; $A shell 'input tap 1373 748'   # the "Pack imported" dialog's OK
$A shell "run-as dev.nxnative.android.bigdanns cat shared_prefs/games.xml" | tr -d '\r' | grep -o "\"title_id\":\"$id\"[^}]*" | sed 's/&quot;/"/g' | cut -c1-300 || true
$A shell "rm -rf /sdcard/BigDanNS-import/$id"
echo "$id: pack $($A shell "du -sh $N/packs/$id" | cut -f1) in BigDanNS"
