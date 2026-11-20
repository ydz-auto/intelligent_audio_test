#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

TOKEN="$(python3 -c "import secrets; print('at_'+secrets.token_hex(16))")"
HASH="$(printf %s "$TOKEN" | sha256sum | awk '{print $1}')"
HINT="${TOKEN: -4}"

SQL="delete from access_tokens where name='audio-playback-proxy'; insert into access_tokens (user_id,name,token_hash,token_hint,scopes,status) values (1,'audio-playback-proxy','$HASH','$HINT','[\"audio:read\"]'::json,'enabled');"

sudo -n docker compose -p intelligent-audio-test --env-file .env \
  -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T -e PGPASSWORD=intelligent_audio_test666 postgres \
  psql -h 127.0.0.1 -U intelligent_audio_test -d intelligent_audio_test \
  -q -c "$SQL" >/tmp/audio-token-sql.log 2>&1

printf %s "$TOKEN" > ~/iat-deploy/audio_token.txt
chmod 600 ~/iat-deploy/audio_token.txt
echo TOKEN_CREATED
