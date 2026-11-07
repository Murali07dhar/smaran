#!/bin/sh
# Prints fresh secrets to paste into infra/.env
set -eu
echo "JWT_SECRET=$(openssl rand -hex 32)"
echo "MEDIA_KEY_B64=$(openssl rand -base64 32)"
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
echo "REDIS_PASSWORD=$(openssl rand -hex 16)"
