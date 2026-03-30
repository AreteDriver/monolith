#!/usr/bin/env bash
# deploy.sh — Monolith pre-flight checks + deploy to Fly.io
set -euo pipefail

FLYCTL="/home/arete/.fly/bin/flyctl"
APP="monolith-evefrontier"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

step() { echo -e "\n${GREEN}▶ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
fail() { echo -e "${RED}✖ $1${NC}"; exit 1; }

cd "$(dirname "$0")/.."

# 1. Lint
step "Ruff check + format"
ruff check backend/ tests/ eval/ || fail "Lint errors — fix before deploying"
ruff format --check backend/ tests/ eval/ || fail "Format errors — run: ruff format backend/ tests/ eval/"

# 2. Tests
step "Running tests (80% coverage gate)"
python3 -m pytest tests/ -x -q --timeout=30 --cov=backend --cov-fail-under=80 || fail "Tests failed"

# 3. Secrets check
step "Scanning for secrets"
if grep -rn 'sk-ant-\|sk-\|ghp_\|ANTHROPIC_API_KEY\s*=' backend/ --include='*.py' | grep -v 'os\.environ\|getenv\|settings\.\|env_prefix\|""'; then
    fail "Possible secrets in source — check output above"
fi
echo "  Clean"

# 4. Git status
step "Git status"
if [ -n "$(git status --porcelain)" ]; then
    warn "Uncommitted changes — deploying anyway"
    git status --short
fi

# 5. Deploy
step "Deploying to Fly.io ($APP)"
$FLYCTL deploy --wait-timeout 600

# 6. Post-deploy verify
step "Post-deploy health check (waiting 15s for startup)"
sleep 15
STATUS=$(curl -s "https://$APP.fly.dev/api/health" --max-time 10)
if echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('status')=='ok' else 1)" 2>/dev/null; then
    echo -e "  ${GREEN}API healthy${NC}"
else
    warn "Health check returned unexpected response"
    echo "$STATUS" | head -c 200
fi

# Check service status after first health cycle
echo "  Waiting 60s for first health cycle..."
sleep 60
curl -s "https://$APP.fly.dev/api/status" --max-time 10 | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d.get('services', []):
    name = s['service_name']
    status = s['status']
    icon = '✓' if status == 'up' else '⚠' if status == 'degraded' else '✖'
    print(f'  {icon} {name}: {status}')
print(f'  Overall: {d.get(\"overall\", \"?\")}')
" 2>/dev/null || warn "Could not fetch service status"

step "Deploy complete"
