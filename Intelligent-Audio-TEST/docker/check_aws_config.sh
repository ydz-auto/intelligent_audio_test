#!/bin/sh
set -eu
mkdir -p /app/.aws
cat > /app/.aws/config <<'EOF'
[default]
s3 =
  addressing_style = virtual
# COS 不支持 aws-chunked 尾随校验，关闭默认 CRC32 校验避免 MissingContentLength
request_checksum_calculation = when_required
response_checksum_validation = when_required
EOF
AWS_CONFIG_FILE=/app/.aws/config PYTHONPATH=/app python /tmp/check_cos.py
