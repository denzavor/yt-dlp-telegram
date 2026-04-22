#!/usr/bin/env bash
set -euo pipefail

SOURCE_FILE="${1:-$HOME/Downloads/cookies.txt}"
TORONTO_HOST="${TORONTO_HOST:-toronto}"
REMOTE_FILE="${REMOTE_FILE:-/opt/yt-dlp-telegram/data/instagram_cookies.txt}"

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "Source file not found: $SOURCE_FILE" >&2
  exit 1
fi

local_hash="$(shasum -a 256 "$SOURCE_FILE" | awk '{print $1}')"
remote_hash="$(
  ssh -o BatchMode=yes "$TORONTO_HOST" \
    "sudo -n sh -lc 'if [ -f \"$REMOTE_FILE\" ]; then shasum -a 256 \"$REMOTE_FILE\" | awk \"{print \\\$1}\"; fi'"
)"

if [[ -n "$remote_hash" && "$local_hash" == "$remote_hash" ]]; then
  echo "Toronto cookies are already up to date."
  echo "sha256: $local_hash"
  exit 0
fi

ssh -o BatchMode=yes "$TORONTO_HOST" \
  "sudo -n tee \"$REMOTE_FILE\" >/dev/null && sudo -n chmod 600 \"$REMOTE_FILE\"" \
  < "$SOURCE_FILE"

verified_remote_hash="$(
  ssh -o BatchMode=yes "$TORONTO_HOST" \
    "sudo -n sh -lc 'shasum -a 256 \"$REMOTE_FILE\" | awk \"{print \\\$1}\"'"
)"

if [[ "$local_hash" != "$verified_remote_hash" ]]; then
  echo "Remote verification failed." >&2
  echo "local : $local_hash" >&2
  echo "remote: $verified_remote_hash" >&2
  exit 1
fi

echo "Toronto cookies updated."
echo "sha256: $verified_remote_hash"
