#!/usr/bin/env bash
# BigDanNS: builds our fork of Banana Native as its own app, beside the official one.
#   package dev.nxnative.android.bigdanns, label "BigDanNS", every game the official APK has (android/app/gradle.properties nxGames)
#   The on-device packer's native side (the "stage") is taken from the official APK of the same version, since
#   android/ondevice/build.sh is Mac-only; Gradle checks that stage's translator against this tree (xlate_tree.py --check-lib).
#
# Work folder (outside the repository, BDN_WORK, default: the folder that holds this checkout):
#   official/banana-native-v<version>.apk   the official release APK of the version this branch is on
#   stage/                                   made from it by this script when missing
#   venv/                                    Python 3 venv with fonttools (Windows: its python.exe copied as python3.exe)
#   out/                                     the built APKs
# Needs: Android SDK (platform 36, NDK 28.2.13676358, CMake 3.22.1), JDK 17+, Git Bash on Windows.
# Usage: bigdanns/build.sh [extra gradle args]      BDN_VERSION=0.3.45-bdn3 to name the build
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
W="${BDN_WORK:-$(cd "$REPO/.." && pwd)}"
export ANDROID_HOME="${ANDROID_HOME:-${LOCALAPPDATA:-$HOME}/Android/Sdk}"
VERSION="${BDN_VERSION:-0.3.45-bdn2}"
UPSTREAM="${VERSION%%-*}"
[ -d "$W/venv/Scripts" ] && export PATH="$W/venv/Scripts:$PATH" || export PATH="$W/venv/bin:$PATH"
command -v python3 >/dev/null || { echo "no python3 (make $W/venv)"; exit 1; }

# the stage, from the official APK (the same libraries the official app runs)
if [ ! -f "$W/stage/lib/libdmsh_xlate.so" ]; then
  APK="$W/official/banana-native-v$UPSTREAM.apk"
  [ -f "$APK" ] || { echo "no $APK: download the official v$UPSTREAM release APK there"; exit 1; }
  python3 -I - "$APK" "$W/stage" <<'EOF'
import io, os, sys, zipfile
apk, out = zipfile.ZipFile(sys.argv[1]), sys.argv[2]
os.makedirs(os.path.join(out, 'lib'), exist_ok=True)
for n in ['libpython3.14.so', 'libnxpack.so', 'libzbicdec.so', 'libcra.so', 'libdmsh_xlate.so', 'libSPIRV-Tools-shared.so']:
    open(os.path.join(out, 'lib', n), 'wb').write(apk.read('lib/arm64-v8a/' + n))
zipfile.ZipFile(io.BytesIO(apk.read('assets/pack/python.zip'))).extractall(os.path.join(out, 'python'))
print('stage made from', sys.argv[1])
EOF
fi

cd "$REPO/android/app"
P() { command -v cygpath >/dev/null && cygpath -m "$1" || echo "$1"; }
printf 'sdk.dir=%s\n' "$(P "$ANDROID_HOME")" > local.properties
./gradlew --no-daemon -PnxApp=bigdanns -PnxLabel=BigDanNS -PnxVersion="$VERSION" -PnxVersionCode=1 \
  -PnxPackStage="$(P "$W/stage")" "$@" apk
mkdir -p "$W/out"
cp out/nxnative-android-bigdanns.apk "$W/out/BigDanNS-$VERSION.apk"
ls -l "$W/out/BigDanNS-$VERSION.apk"
