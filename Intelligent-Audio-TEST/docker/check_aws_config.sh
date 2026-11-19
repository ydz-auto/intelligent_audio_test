#!/bin/sh
set -eu
mkdir -p /app/.aws
cat > /app/.aws/config <<'EOF'
[default]
s3 =
  addressing_style = virtual
EOF
AWS_CONFIG_FILE=/app/.aws/config PYTHONPATH=/app python /tmp/check_cos.py
