#!/usr/bin/env bash
set -euo pipefail
T="$(cat "$HOME/iat-deploy/audio_token.txt")"
curl -s -G -H "Authorization: Bearer $T" \
  -o /tmp/audio_probe.wav \
  -w 'status=%{http_code} bytes=%{size_download}\n' \
  --data-urlencode 'path=oss://audios/test.wav' \
  http://127.0.0.1:15000/api/v1/audios/download
ls -l /tmp/audio_probe.wav
