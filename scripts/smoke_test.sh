#!/usr/bin/env bash
#
# Read-only smoke test for a deployed CertForge environment.
#
# Every check here is a GET. Nothing is issued, nothing is emailed, nothing is
# written — so this is safe to run against production, which is the point:
# the suites that DO write (test_api.py, sdk/test_sdk.py) are not.
#
# Usage:
#   scripts/smoke_test.sh                          # production
#   scripts/smoke_test.sh https://staging.example  # anywhere else
#   scripts/smoke_test.sh http://localhost:8000    # local uvicorn
#
# Exits non-zero if any check fails, so it can gate a deploy.

set -uo pipefail

BASE="${1:-https://certs.intelliforge.tech}"
BASE="${BASE%/}"
# The CertForge host is probed separately from BASE, because the URLs inside a
# CertForge QR code are built from CERTFORGE_WEB_URL rather than from the legacy
# site. Override with SMOKE_CERTFORGE_WEB.
#
# The origin the browser UI is served from — used to prove CORS still admits
# the real front end, not just that it blocks strangers.
SITE_ORIGIN="${SMOKE_SITE_ORIGIN:-https://certs.intelliforge.tech}"

PASS=0; FAIL=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n\n       expected: %s\n       actual:   %s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

get()      { curl -s -m 30 "$@"; }
status()   { curl -s -m 30 -o /dev/null -w '%{http_code}' "$@"; }
ctype()    { curl -s -m 30 -o /dev/null -w '%{content_type}' "$@"; }
acao()     { curl -s -m 30 -D - -o /dev/null "$@" | tr -d '\r' | grep -i '^access-control-allow-origin:' | cut -d' ' -f2-; }

check_status() { local n="$1" u="$2" want="$3"; local got; got="$(status "$BASE$u")"
  [ "$got" = "$want" ] && ok "$n" || bad "$n" "HTTP $want" "HTTP $got"; }

check_contains() { local n="$1" u="$2" want="$3"; local got; got="$(get "$BASE$u")"
  case "$got" in *"$want"*) ok "$n" ;; *) bad "$n" "body containing: $want" "$(printf '%s' "$got" | head -c 140)" ;; esac; }

printf '\n\033[1mSmoke test\033[0m %s\n' "$BASE"

head_ "System"
check_status   "GET /api/health is 200"            "/api/health" 200
check_contains "  ... and reports healthy"         "/api/health" '"status":"healthy"'
check_contains "GET /api/info exposes branding"    "/api/info"   '"branding"'
check_contains "GET /api/courses returns a list"   "/api/courses" '"courses"'
check_status   "GET /docs is 200"                  "/docs" 200

head_ "Agent-discovery surface"
for p in /llms.txt /robots.txt /sitemap.xml /.well-known/ai-plugin.json; do
  check_status "GET $p is 200" "$p" 200
done

head_ "Route table"
OPENAPI="$(get "$BASE/openapi.json")"
case "$OPENAPI" in
  *'/api/v1/api/v1'*) bad "no double-prefixed /api/v1/api/v1 routes" "none" "found some" ;;
  *) ok "no double-prefixed /api/v1/api/v1 routes" ;;
esac

head_ "Frozen legacy contract"
# The bare {"error": ...} envelope. sdk/pdfcert parses this shape verbatim.
check_contains "legacy errors stay un-enveloped" "/invoice/not.a.real.token/download" '{"error":{'
case "$(get "$BASE/invoice/not.a.real.token/download")" in
  *'"success"'*) bad "legacy error carries NO success field" "no success key" "success key present" ;;
  *) ok "legacy error carries no success field" ;;
esac
check_contains "tampered token fails verification" "/certificate/bogus.token/verify" '"valid":false'

head_ "CertForge v1 envelope"
check_contains "v1 errors are enveloped" "/api/v1/orgs/__no_such_org__" '"success":false'
check_contains "  ... with a data key"    "/api/v1/orgs/__no_such_org__" '"data":null'

head_ "Public credential surface"
# Regression guard: this returned 500 (undefined `Organization`) until Wave 1.
check_status "unknown badge.json is 404, not 500" "/credentials/CF-2026-NOTREAL/badge.json" 404
check_status "unknown /verify is 404"             "/verify/CF-2026-NOTREAL" 404
CT="$(ctype "$BASE/verify/CF-2026-NOTREAL")"
case "$CT" in text/html*) ok "/verify serves HTML, not the SPA shell" ;;
  *) bad "/verify serves HTML" "text/html" "$CT" ;; esac

head_ "CertForge public host"
# Everything above was probed against BASE, which defaults to the LEGACY host —
# where these rewrites have existed since 3b52e72. The URLs CertForge actually
# stamps into a QR code are built from CERTFORGE_WEB_URL, and on THAT host they
# 404'd for the whole of Wave 1 while every check in this file passed. Probing
# the path without probing the host it is written on is what hid the bug.
CF_WEB="${SMOKE_CERTFORGE_WEB:-https://certforge.intelliforge.tech}"
CF_WEB="${CF_WEB%/}"

# Asserting the STATUS here would be useless: Next.js answers an unrouted path
# with its own 404, so "404" is returned both when the API refused the
# credential and when the request never reached the API at all. The first
# version of this section passed against a host serving nothing but the app
# shell. So each check below pins a response only the API can produce.
check_abs_contains() { local n="$1" u="$2" want="$3"; local got; got="$(get "$u")"
  case "$got" in *"$want"*) ok "$n" ;;
    *) bad "$n" "body containing: $want" "$(printf '%s' "$got" | head -c 140)" ;; esac; }

check_abs_ctype() { local n="$1" u="$2" want="$3"; shift 3; local got
  got="$(ctype "$@" "$u")"
  case "$got" in "$want"*) ok "$n" ;; *) bad "$n" "$want" "$got" ;; esac; }

check_abs_contains "/verify reaches the API, not the app shell" \
  "$CF_WEB/verify/CF-2026-NOTREAL" "Invalid or Revoked Credential"
check_abs_ctype "badge.json reaches the API, not the app shell" \
  "$CF_WEB/credentials/CF-2026-NOTREAL/badge.json" "application/json"
check_abs_ctype "the issuer profile reaches the API, not the app shell" \
  "$CF_WEB/orgs/__no_such_org__" "application/json" -H "Accept: application/json"

head_ "CORS"
A="$(acao -H "Origin: https://smoke-test.invalid" "$BASE/api/health")"
[ -z "$A" ] && ok "unknown origin gets no ACAO" || bad "unknown origin is refused" "no ACAO header" "$A"
A="$(acao -X OPTIONS -H "Origin: $SITE_ORIGIN" -H 'Access-Control-Request-Method: POST' "$BASE/api/certificate")"
[ "$A" = "$SITE_ORIGIN" ] && ok "site origin is admitted" || bad "site origin is admitted" "$SITE_ORIGIN" "${A:-<none>}"

printf '\n\033[1m%d passed, %d failed\033[0m\n\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
