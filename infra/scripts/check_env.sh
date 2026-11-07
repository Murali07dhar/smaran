#!/bin/sh
# Fail fast if required secrets are missing, still placeholders, or malformed.  Usage: check_env.sh infra/.env
set -eu
file="${1:-infra/.env}"
[ -f "$file" ] || { echo "ERROR: $file not found (run: make env)"; exit 1; }

get() { grep -E "^$1=" "$file" | tail -n 1 | cut -d= -f2- || true; }
fail=0

for var in JWT_SECRET MEDIA_KEY_B64 POSTGRES_PASSWORD REDIS_PASSWORD; do
  val="$(get "$var")"
  case "$val" in
    ""|change-me*) echo "ERROR: $var is empty or still a placeholder in $file"; fail=1 ;;
  esac
done

jwt="$(get JWT_SECRET)"
if [ "${#jwt}" -lt 32 ] && [ -n "$jwt" ]; then echo "ERROR: JWT_SECRET must be at least 32 characters"; fail=1; fi

key="$(get MEDIA_KEY_B64)"
case "$key" in change-me*|"") ;; *)
  bytes="$(printf '%s' "$key" | base64 -d 2>/dev/null | wc -c | tr -d ' ')"
  if [ "$bytes" != "32" ]; then echo "ERROR: MEDIA_KEY_B64 must decode to exactly 32 bytes (got $bytes)"; fail=1; fi ;;
esac

for var in POSTGRES_PASSWORD REDIS_PASSWORD; do
  case "$(get "$var")" in *[!A-Za-z0-9]*) echo "ERROR: $var must contain letters and digits only (it is embedded in a URL)"; fail=1 ;; esac
done

[ "$fail" -eq 0 ] && echo "env OK"
exit "$fail"
