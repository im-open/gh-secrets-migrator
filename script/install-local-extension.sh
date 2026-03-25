#!/usr/bin/env bash
# Install a patched local version of gh-secrets-migrator as a GitHub CLI extension.
#
# Supports:
# - Using the current checkout (default)
# - Cloning a specific repo URL + branch and installing from that clone
#
# Examples:
#   ./script/install-local-extension.sh
#   ./script/install-local-extension.sh --clone --repo-url https://github.com/im-open/gh-secrets-migrator.git --branch fix-pygithub-issue-3021

set -euo pipefail

REPO_URL="https://github.com/im-open/gh-secrets-migrator.git"
BRANCH="fix-pygithub-issue-3021"
WORKDIR="${TMPDIR:-/tmp}"
USE_CURRENT=true

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --clone                 Clone repo/branch before install (default: use current directory)
  --use-current           Use current checkout (default)
  --repo-url <url>        Repo URL when --clone is used
  --branch <name>         Branch name when --clone is used
  --workdir <path>        Clone destination parent dir (default: /tmp)
  -h, --help              Show help

Defaults:
  repo-url: ${REPO_URL}
  branch:   ${BRANCH}
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clone)
      USE_CURRENT=false
      shift
      ;;
    --use-current)
      USE_CURRENT=true
      shift
      ;;
    --repo-url)
      REPO_URL="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --workdir)
      WORKDIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

need_cmd gh
need_cmd git
need_cmd python3
need_cmd make

if [[ "$USE_CURRENT" == "true" ]]; then
  REPO_DIR="$PWD"
  echo "Using current checkout: $REPO_DIR"
else
  mkdir -p "$WORKDIR"
  REPO_DIR="$WORKDIR/gh-secrets-migrator-${BRANCH}"
  rm -rf "$REPO_DIR"
  echo "Cloning $REPO_URL (branch: $BRANCH) into $REPO_DIR"
  git clone --depth 1 --single-branch --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"

if [[ -x "venv/bin/python" ]]; then
  PYTHON_BIN="venv/bin/python"
  echo "Using existing venv interpreter: $PYTHON_BIN"
else
  PYTHON_BIN="python3"
  echo "No venv found, using system interpreter: $PYTHON_BIN"
fi

"$PYTHON_BIN" -m pip install -r requirements.txt
make build

echo "Removing old extension install if present..."
gh extension remove secrets-migrator >/dev/null 2>&1 || true

echo "Installing patched extension from local checkout..."
gh extension install .

echo
echo "Installed extension version:"
gh extension list | grep secrets-migrator || true

echo
echo "Smoke test:"
gh secrets-migrator --help

echo
echo "Done. Patched extension installed from: $REPO_DIR"
