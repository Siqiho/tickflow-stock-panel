#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/frontend"
ANDROID="$FRONTEND/android"
JDK_HOME="$ROOT/.android-toolchain/jdk/Contents/Home"
ANDROID_HOME="$ROOT/.android-sdk"
GRADLE_USER_HOME="$ROOT/.android-toolchain/gradle-home"
SIGNING_ENV="$ROOT/.private/android/signing.env"

for required in \
  "$JDK_HOME/bin/java" \
  "$ANDROID_HOME/build-tools/36.0.0/zipalign" \
  "$ANDROID_HOME/build-tools/36.0.0/apksigner" \
  "$SIGNING_ENV"; do
  if [[ ! -e "$required" ]]; then
    echo "Missing required Android release file: $required" >&2
    exit 1
  fi
done

export JAVA_HOME="$JDK_HOME"
export ANDROID_HOME
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export GRADLE_USER_HOME

# shellcheck disable=SC1090
source "$SIGNING_ENV"

cd "$FRONTEND"
corepack pnpm@9.10.0 run build
corepack pnpm@9.10.0 exec cap sync android

cd "$ANDROID"
./gradlew clean assembleRelease --no-daemon --console=plain

VERSION="$(cd "$FRONTEND" && node -p "require('./package.json').version")"
UNSIGNED="$ANDROID/app/build/outputs/apk/release/app-release-unsigned.apk"
OUT_DIR="$ROOT/releases/android"
ALIGNED="$OUT_DIR/.one-trading-private-${VERSION}-aligned.apk"
OUTPUT="$OUT_DIR/one-trading-private-${VERSION}.apk"

mkdir -p "$OUT_DIR"
"$ANDROID_HOME/build-tools/36.0.0/zipalign" -p -f 4 "$UNSIGNED" "$ALIGNED"
"$ANDROID_HOME/build-tools/36.0.0/apksigner" sign \
  --ks "$ONE_TRADING_KEYSTORE_PATH" \
  --ks-key-alias "$ONE_TRADING_KEY_ALIAS" \
  --ks-pass "pass:$ONE_TRADING_KEYSTORE_PASSWORD" \
  --key-pass "pass:$ONE_TRADING_KEY_PASSWORD" \
  --out "$OUTPUT" \
  "$ALIGNED"

"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify --verbose --print-certs "$OUTPUT"
shasum -a 256 "$OUTPUT"
echo "$OUTPUT"
