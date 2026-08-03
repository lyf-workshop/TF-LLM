#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE="core"
PYTHON_VERSION="3.12"
SKILLSBENCH_DIR="${SKILLSBENCH_DIR:-$ROOT_DIR/SkillsBench-repo}"
SKILLSBENCH_REF="${SKILLSBENCH_REF:-b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af}"
SKILLSBENCH_URL="https://github.com/benchflow-ai/SkillsBench.git"

usage() {
  cat <<'EOF'
Usage: bash scripts/setup/deploy.sh [options]
  --profile PROFILE        core | korgym | skillsbench | all
  --python VERSION         Python version managed by uv (default: 3.12)
  --skillsbench-dir PATH   External SkillsBench checkout path
  --skillsbench-ref REF    Reproducible SkillsBench git commit
  -h, --help               Show this help

This script never accepts API keys on the command line. Edit .env after setup.
EOF
}

log() { printf '[tf-llm] %s\n' "$*"; }
warn() { printf '[tf-llm] WARNING: %s\n' "$*" >&2; }
die() { printf '[tf-llm] ERROR: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      [[ $# -ge 2 ]] || die "--profile requires a value"
      PROFILE="$2"; shift 2 ;;
    --python)
      [[ $# -ge 2 ]] || die "--python requires a value"
      PYTHON_VERSION="$2"; shift 2 ;;
    --skillsbench-dir)
      [[ $# -ge 2 ]] || die "--skillsbench-dir requires a value"
      SKILLSBENCH_DIR="$2"; shift 2 ;;
    --skillsbench-ref)
      [[ $# -ge 2 ]] || die "--skillsbench-ref requires a value"
      SKILLSBENCH_REF="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

case "$PROFILE" in
  core) WITH_KORGYM=false; WITH_SKILLSBENCH=false ;;
  korgym) WITH_KORGYM=true; WITH_SKILLSBENCH=false ;;
  skillsbench) WITH_KORGYM=false; WITH_SKILLSBENCH=true ;;
  all) WITH_KORGYM=true; WITH_SKILLSBENCH=true ;;
  *) die "invalid profile '$PROFILE'" ;;
esac
install_skillsbench() {
  command -v docker >/dev/null 2>&1 || die "Docker is required for SkillsBench"
  docker info >/dev/null 2>&1 || die "Docker daemon is unavailable"

  export PATH="$HOME/.local/bin:$PATH"
  local harbor_version=""
  if command -v harbor >/dev/null 2>&1; then
    harbor_version="$(harbor --version 2>/dev/null | head -n 1 || true)"
  fi
  if [[ "$harbor_version" != "0.3.0" ]]; then
    log "Installing adapter-compatible harbor==0.3.0"
    uv tool install --force "harbor==0.3.0"
    hash -r
  fi
  command -v harbor >/dev/null 2>&1 || die "Harbor is not on PATH"
  [[ "$(harbor --version 2>/dev/null | head -n 1)" == "0.3.0" ]] || \
    die "TF-LLM currently requires harbor==0.3.0"

  if [[ ! -d "$SKILLSBENCH_DIR/.git" ]]; then
    [[ ! -e "$SKILLSBENCH_DIR" ]] || \
      die "$SKILLSBENCH_DIR exists but is not a git checkout"
    log "Cloning the external SkillsBench task repository"
    git clone "$SKILLSBENCH_URL" "$SKILLSBENCH_DIR"
  fi

  local current_ref
  current_ref="$(git -C "$SKILLSBENCH_DIR" rev-parse HEAD)"
  if [[ "$current_ref" != "$SKILLSBENCH_REF" ]]; then
    [[ -z "$(git -C "$SKILLSBENCH_DIR" status --porcelain)" ]] || \
      die "SkillsBench checkout is dirty; preserve it before changing commits"
    log "Pinning SkillsBench to $SKILLSBENCH_REF"
    git -C "$SKILLSBENCH_DIR" fetch origin "$SKILLSBENCH_REF"
    git -C "$SKILLSBENCH_DIR" checkout --detach "$SKILLSBENCH_REF"
  fi

  if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
    warn "Apple Silicon is for smoke tests; use Linux x86_64 for paper-scale runs"
  fi
}
cd "$ROOT_DIR"
[[ -f pyproject.toml ]] || die "run this script inside a TF-LLM checkout"
command -v git >/dev/null 2>&1 || die "git is required"

if ! command -v uv >/dev/null 2>&1; then
  command -v curl >/dev/null 2>&1 || die "curl is required to install uv"
  log "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || die "uv is not on PATH; restart the shell"

log "Using $(uv --version)"
uv python install "$PYTHON_VERSION"
uv sync --locked --python "$PYTHON_VERSION"

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env 2>/dev/null || true
  log "Created .env from .env.example"
else
  log "Keeping the existing .env"
fi

if [[ "$WITH_KORGYM" == true ]]; then
  log "Installing the minimal KORGym runtime"
  uv pip install --python "$ROOT_DIR/.venv/bin/python" -r requirements/korgym-runtime.txt
fi

if [[ "$WITH_SKILLSBENCH" == true ]]; then
  install_skillsbench
fi

log "Running a non-secret preflight check"
uv run python scripts/setup/check_environment.py \
  --profile "$PROFILE" \
  --skillsbench-repo "$SKILLSBENCH_DIR" \
  --allow-missing-api-key

cat <<EOF

Deployment finished.
1. Edit $ROOT_DIR/.env.
2. Run: uv run python scripts/setup/check_environment.py --profile $PROFILE --check-api
3. Follow docs/DEPLOYMENT.md and the selected dataset guide.
EOF
