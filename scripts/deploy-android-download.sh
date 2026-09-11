#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-0.1.69}"
APK="$ROOT/releases/android/one-trading-private-${VERSION}.apk"
SERVICE_DIR="$ROOT/deploy/android-download"
PUBLIC_APK="$SERVICE_DIR/public/one-trading-private-${VERSION}.apk"

if [[ ! -f "$APK" ]]; then
  echo "Missing signed APK: $APK" >&2
  exit 1
fi

cp -p "$APK" "$PUBLIC_APK"
shasum -a 256 "$APK" "$PUBLIC_APK"

cd "$SERVICE_DIR"
npx zeabur@latest deploy \
  --service-id 6a762f1de4a69d66638cca79 \
  --project-id 6a7613ede4a69d66638cc3f2 \
  --environment-id 6a7613ed5f062718bc7b7ff7 \
  -i=false \
  --json
