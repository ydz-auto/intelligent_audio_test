#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/iat-deploy/compose"

sudo -n docker compose -p intelligent-audio-test --env-file .env \
  -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T -e PGPASSWORD=intelligent_audio_test666 postgres \
  psql -h 127.0.0.1 -U intelligent_audio_test -d intelligent_audio_test \
  -c "select id,user_id,name,status,scopes from access_tokens where name='audio-playback-proxy';"

T="$(cat "$HOME/iat-deploy/audio_token.txt")"
curl -s -G -H "Authorization: Bearer $T" \
  -o /tmp/audio_probe.wav \
  -w 'status=%{http_code} bytes=%{size_download}\n' \
  --data-urlencode 'path=oss://audios/test.wav' \
  http://127.0.0.1:15000/api/v1/audios/download
ls -l /tmp/audio_probe.wav
