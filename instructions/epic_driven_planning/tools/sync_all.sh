#!/bin/bash
# sync_all.sh - 全プロジェクトの同期状況を一括確認
#
# 使用方法:
#   ./sync_all.sh           # 全プロジェクト確認
#   ./sync_all.sh --json    # JSON出力

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token 2>/dev/null)}"

export GITHUB_TOKEN

python3 "$SCRIPT_DIR/sync_status.py" \
  --github nobu007/TypeEnforcerAI \
  --github nobu007/instructions \
  --github nobu007/ai-hub \
  --github nobu007/n8n_auto_wordpress \
  --github jinno0/github-actions-hub \
  --github jinno0/github-actions-actions \
  --github jinno0/copilot-instruction-eval \
  --gitlab a09097066154/github-actions-hub \
  --ado jin5770808/github-actions-hub \
  --ado jin5770808/micro-instruction-engineering \
  --ado jin5770808/tokyo-career-up \
  "$@"
