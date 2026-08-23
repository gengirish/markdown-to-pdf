#!/usr/bin/env bash
#
# Gated deploy for the CertForge API (Fly.io app `certforge-api`).
#
# Why this exists: the API is not part of any push-to-deploy pipeline. Vercel
# only builds the SPA; the API ships by `fly deploy`, historically straight
# from a laptop with nothing run in front of it — against the half of the
# system that actually carries the risk.
#
# .github/workflows/ci.yml has a deploy-api job that does the same thing on
# merge to main, but GitHub Actions cannot currently run on this account
# (billing), and even once it can, someone will still deploy by hand one day.
# This script is what makes that safe.
#
# Usage:
#   scripts/deploy_api.sh              # run every gate, then deploy
#   scripts/deploy_api.sh --dry-run    # run every gate, stop before deploying
#   scripts/deploy_api.sh --allow-dirty
#
# There is deliberately no flag to skip the tests.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$REPO_ROOT/apps/api"
FLY_APP="certforge-api"
HEALTH_URL="https://certforge-api.fly.dev/api/health"

DRY_RUN=0
ALLOW_DIRTY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)     DRY_RUN=1 ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    -h|--help)     sed -n '2,22p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

step()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()    { printf '    \033[32mok\033[0m  %s\n' "$1"; }
die()   { printf '\n\033[31mBLOCKED\033[0m %s\n\n' "$1" >&2; exit 1; }

cd "$REPO_ROOT"

# ── 1. Provenance ───────────────────────────────────────────────────────────
# A deploy you cannot trace back to a commit is a deploy you cannot roll back
# to a known state, so establish what is shipping before running anything.
step "Provenance"

if [ "$ALLOW_DIRTY" -eq 0 ] && [ -n "$(git status --porcelain)" ]; then
  git status --short
  die "working tree is dirty. Commit first, or pass --allow-dirty if you
        genuinely mean to ship something that is not in git."
fi
ok "working tree clean"

SHA="$(git rev-parse HEAD)"
SHORT="$(git rev-parse --short HEAD)"

# Deploying a commit that exists only on this machine means the running image
# cannot be rebuilt by anyone else, and cannot be diffed against later.
if ! git branch -r --contains "$SHA" 2>/dev/null | grep -q .; then
  die "HEAD ($SHORT) is not on any remote branch. Push it first, so the
        deployed image is reproducible from the repository."
fi
ok "HEAD $SHORT is on a remote branch"
echo "        $(git log -1 --format='%s' "$SHA")"

# ── 2. The gates ────────────────────────────────────────────────────────────
step "Gates"

command -v ruff   >/dev/null || die "ruff is not installed (pip install ruff)"
command -v python >/dev/null || die "python is not on PATH"

ruff check apps/api/api/ sdk/pdfcert/ >/dev/null && ok "ruff"
python scripts/check_tracked_sources.py >/dev/null && ok "no source hidden by .gitignore"

# Run pytest from apps/api so pytest.ini's testpaths/pythonpath apply. No -q
# here: pytest.ini already sets it, and a second -q suppresses the summary
# line this reads the pass count from.
PYTEST_LOG="$(mktemp)"
( cd "$API_DIR" && python -m pytest ) >"$PYTEST_LOG" 2>&1 \
  || { tail -30 "$PYTEST_LOG"; die "pytest failed. Nothing deployed."; }
PASSED="$(grep -Eo '[0-9]+ passed' "$PYTEST_LOG" | tail -1)"
[ -n "$PASSED" ] || die "could not read a pass count from pytest output.
        Refusing to deploy on an unreadable test result: $PYTEST_LOG"
ok "pytest — $PASSED"
rm -f "$PYTEST_LOG"

# ── 3. Deploy ───────────────────────────────────────────────────────────────
step "Deploy"

if ! command -v flyctl >/dev/null; then
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '    \\033[33mwarn\\033[0m flyctl is not installed; a real deploy would stop here.\\n'
  else
    die "flyctl is not installed — https://fly.io/docs/flyctl/install/"
  fi
fi

CURRENT="$(flyctl releases --app "$FLY_APP" --json 2>/dev/null | python -c '
import json,sys
try:
    r = json.load(sys.stdin)
    print(r[0].get("Version", "?") if r else "none")
except Exception:
    print("?")
' || echo "?")"
echo "    current release: v$CURRENT"

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n\033[33mDRY RUN\033[0m every gate passed; stopping before `flyctl deploy`.\n\n'
  exit 0
fi

printf '    deploying %s to %s ...\n\n' "$SHORT" "$FLY_APP"
( cd "$API_DIR" && flyctl deploy --remote-only ) || die "flyctl deploy failed. The previous release is still serving."

# ── 4. Confirm it is actually serving ───────────────────────────────────────
# `flyctl deploy` returning 0 means the machine started, not that the app
# answers. fly.toml runs migrations in a release_command; a boot failure after
# that still shows as a successful deploy command.
step "Verify"

for i in $(seq 1 20); do
  if curl -fsS --max-time 10 "$HEALTH_URL" 2>/dev/null | grep -q '"status":"healthy"'; then
    ok "$HEALTH_URL reports healthy"
    curl -fsS --max-time 10 "$HEALTH_URL"; echo
    printf '\n\033[32mDeployed\033[0m %s\n' "$SHORT"
    printf 'Roll back with: flyctl releases --app %s && flyctl deploy --app %s --image <previous>\n\n' "$FLY_APP" "$FLY_APP"
    exit 0
  fi
  sleep 5
done

die "deploy reported success but $HEALTH_URL never went healthy.
        Check: flyctl logs --app $FLY_APP"
