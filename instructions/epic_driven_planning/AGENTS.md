# AGENTS.md - Epic-Driven Planning ツールキット

> AIエージェント（Claude Code, Copilot等）がこのツールを正しく使用するための指示書

## 🎯 このツールの目的

**Epic → Feature → Story → Task を段階的に分解し、GitHub/GitLab/ADO に同期する**

---

## 🌐 プロジェクト・組織 一元管理（重要）

### 登録済みプロジェクト一覧

```bash
# 一覧表示
python project_sync.py --list-projects
```

| プロジェクトID | GitHub | GitLab | Azure DevOps |
|--------------|--------|--------|--------------|
| `enterprise-rag-system` | nobu007/enterprise-rag-system | jinno-ai/enterprise-rag-system | jin5770808/tokyo-career-up |
| `ai-hub` | nobu007/ai-hub | jinno-ai/ai-hub | jin5770808/tokyo-career-up |
| `realtime-edge-detection` | jinno-ai/realtime-edge-detection | jinno-ai/realtime-edge-detection | jin5770808/tokyo-career-up |
| `llm-agent-framework` | jinno-ai/llm-agent-framework | jinno-ai/llm-agent-framework | jin5770808/tokyo-career-up |

### 組織マッピング

| GitHub | GitLab | Azure DevOps |
|--------|--------|--------------|
| nobu007 | jinno-ai | jin5770808 |
| jinno-ai | jinno-ai | jin5770808 |

### 環境変数（必須）

```bash
# GitHub（gh CLI で自動）
gh auth status

# GitLab
export GITLAB_TOKEN="glpat-xxxx"

# Azure DevOps
export AZURE_DEVOPS_PAT="xxxx"
# または
export AZURE_DEVOPS_EXT_PAT="xxxx"
```

---

## 🚀 クイックスタート（3環境同期）

### 方法1: multi_provider_sync.py（最も簡単）

```bash
cd hub/instructions/epic_driven_planning

# 3環境すべてに同期
python multi_provider_sync.py \
    --github nobu007 ai-hub \
    --gitlab jinno-ai/enterprise-rag-system \
    --ado jin5770808 tokyo-career-up
```

### 方法2: project_sync.py（プロジェクトID指定）

```bash
# プロジェクトID指定で全環境に同期
python project_sync.py \
    --project enterprise-rag-system \
    --decomposition output/decomposition.json \
    --all-providers
```

---

## 📋 対応インストラクション（01-planning-requirements）

| ステージ | インストラクション | ツール/モード |
|----------|-------------------|---------------|
| Epic | `02_epic/ado_epic_create.md` | `--mode epic` |
| Feature | `03_feature/ado_feature_create.md` | `--mode feature` |
| Story | `04_story/ado_story_create.md` | `--mode story` |
| Task | `05_task/ado_task_create.md` | `--mode task` |

## ⚠️ 必読：実行前に必ず確認

1. **設定ファイル** (`*_config.yaml`) が存在するか
2. **認証** が完了しているか（`gh auth status`, `az login --status`）
3. **データ本体** (`output/_registry/`) の状態

---

## 📋 標準ワークフロー（01-planning-requirements 準拠）

### Phase 1: 準備

```bash
# 1. ディレクトリ移動
cd hub/instructions/epic_driven_planning

# 2. 認証確認
gh auth status              # GitHub
az account show             # ADO
glab auth status            # GitLab（必要な場合）

# 3. 設定ファイル確認/作成
cp config_template.yaml my_project_config.yaml
# 必須項目を編集: org, repo, provider, epic.goal
```

### Phase 2: 全自動パイプライン（推奨）

```bash
# 01-planning-requirements を完全に実行
python epic_manager.py \
    --config my_project_config.yaml \
    --mode full-pipeline

# 実行されるステージ:
#   1. epic     → 02_epic/ado_epic_create.md
#   2. feature  → 03_feature/ado_feature_create.md
#   3. story    → 04_story/ado_story_create.md
#   4. task     → 05_task/ado_task_create.md
#   5. validate → 品質チェック
#   6. schedule → スケジュール最適化
#   7. sync     → プロバイダー同期
```

### Phase 3: 個別ステップ実行（01-planning-requirements 準拠）

```bash
# 02_epic: Epic生成（ビジネスゴール定義）
python epic_manager.py --config my_project_config.yaml --mode epic

# 03_feature: Feature分解（1-2スプリントの機能単位）
python epic_manager.py --config my_project_config.yaml --mode feature

# 04_story: Story分解（1スプリント内で完了、INVEST原則）
python epic_manager.py --config my_project_config.yaml --mode story

# 05_task: Task分解（2-8時間の技術タスク）
python epic_manager.py --config my_project_config.yaml --mode task

# 品質チェック
python epic_manager.py --config my_project_config.yaml --mode validate

# スケジュール最適化
python epic_manager.py --config my_project_config.yaml --mode schedule
```

### Phase 4: プロバイダー同期（3環境対応）

```bash
# ============================================
# 方法1: multi_provider_sync.py（推奨・簡単）
# ============================================

# 3環境すべてに同期（一発コマンド）
python multi_provider_sync.py \
    --github nobu007 ai-hub \
    --gitlab jinno-ai/enterprise-rag-system \
    --ado jin5770808 tokyo-career-up

# 個別プロバイダー
python multi_provider_sync.py --github nobu007 ai-hub
python multi_provider_sync.py --gitlab jinno-ai/enterprise-rag-system
python multi_provider_sync.py --ado jin5770808 tokyo-career-up

# ============================================
# 方法2: project_sync.py（プロジェクトID指定）
# ============================================

# プロジェクト一覧表示
python project_sync.py --list-projects

# 全環境同期
python project_sync.py \
    --project enterprise-rag-system \
    --decomposition output/decomposition.json \
    --all-providers

# 個別プロバイダー
python project_sync.py \
    --project ai-hub \
    --decomposition output/decomposition.json \
    --provider github

# ============================================
# 方法3: 従来の方法（設定ファイル指定）
# ============================================

# GitHub Issues + Projects V2
python project_sync.py \
    --config my_project_config.yaml \
    --decomposition output/{org}/{repo}/E00001/decomposition.json \
    --provider github

# Azure DevOps Work Items
python project_sync.py \
    --config my_project_config.yaml \
    --decomposition output/{org}/{repo}/E00001/decomposition.json \
    --provider ado

# ドライラン（実際には作成しない）
python project_sync.py \
    --config my_project_config.yaml \
    --decomposition output/{org}/{repo}/E00001/decomposition.json \
    --provider github \
    --dry-run
```

### Phase 5: 確認

```bash
# GitHub Issues確認
gh issue list --repo {owner}/{repo} --limit 30

# ADO WorkItems確認
az boards query --wiql "SELECT [System.Id], [System.Title] FROM WorkItems" \
    --org https://dev.azure.com/{ado_org} -o table

# データ本体確認
cat output/_registry/{org}/{repo}/E00001/F00001/S00001/_item.json
```

---

## 🔄 パイプライン詳細

### 各ステージの詳細

| ステージ | 入力 | 出力 | インストラクション要件 |
|----------|------|------|----------------------|
| **epic** | config.yaml | Epic定義 | ビジネスゴール、測定可能な完了条件、スコープ境界 |
| **feature** | Epic | features.json | 1-2スプリント完了、3-7 Story に分解可能 |
| **story** | features.json | decomposition.json | INVEST原則、Story Points、Acceptance Criteria |
| **task** | decomposition.json | decomposition.json（Task追加） | 2-8時間、単一責務、依存関係明示 |
| **validate** | decomposition.json | 検証結果 | 品質基準チェック |
| **schedule** | decomposition.json | schedule.json | 依存関係解析、日程最適化 |
| **sync** | decomposition.json + schedule.json | GitHub/ADO | Issue/WorkItem 作成 |

### Task カテゴリ（05_task 準拠）

| カテゴリ | 説明 | 見積もり目安 |
|----------|------|-------------|
| implementation | コード実装 | 4時間 |
| test | テスト作成 | 2時間 |
| review | コードレビュー | 1時間 |
| documentation | ドキュメント作成 | 1時間 |
| investigation | 技術調査 | 2時間 |
| config | 設定・構成 | 2時間 |

---

## 📁 重要ファイル・ディレクトリ

| パス | 用途 | 状態確認コマンド |
|------|------|-----------------|
| `*_config.yaml` | プロジェクト設定 | `cat config.yaml` |
| `output/_registry/` | **データ本体（Source of Truth）** | `ls -la output/_registry/` |
| `output/{org}/{repo}/E00001/decomposition.json` | 分解結果 | `cat ...` |
| `providers/` | GitHub/ADO/GitLabプロバイダー | - |
| `docs/KEY_SPEC.md` | 統一キー仕様 | - |

---

## 🔑 統一キー仕様（KEY_SPEC）

```
{org}/{repo}/{epic_id}/{feature_id}/{story_id}

例: nobu007/tokyo_career_up/E00001/F00001/S00001
```

| レベル | 形式 | 最大件数 |
|--------|------|----------|
| Epic | `E00001` | 99,999件/プロジェクト |
| Feature | `F00001` | 99,999件/Epic |
| Story | `S00001` | 99,999件/Feature |
| Task | `T00001` | 99,999件/Story |

---

## 📦 データ本体（_registry）

```
output/_registry/
└── {org}/
    └── {repo}/
        └── E00001/
            ├── _item.json           # Epic本体
            └── F00001/
                ├── _item.json       # Feature本体
                └── S00001/
                    └── _item.json   # Story本体 + external_refs
```

### _item.json 形式

```json
{
  "key": "nobu007/tokyo_career_up/E00001/F00001/S00001",
  "item_type": "story",
  "title": "マスタデータ設計",
  "external_refs": {
    "github": "45",     // GitHub Issue #45
    "ado": "21"         // ADO WorkItem #21
  }
}
```

---

## ⚙️ 設定ファイル必須項目

### 方法A: PROJECT_REGISTRY を使う（推奨）

`project_sync.py` の `PROJECT_REGISTRY` に登録済みなら設定ファイル不要：

```bash
# プロジェクトIDを指定するだけ
python project_sync.py --project enterprise-rag-system -d decomposition.json --all-providers
```

新規プロジェクトを追加する場合は `project_sync.py` の `PROJECT_REGISTRY` を編集：

```python
PROJECT_REGISTRY = {
    "my-new-project": {
        "description": "新規プロジェクト説明",
        "github": {"owner": "nobu007", "repo": "my-new-project"},
        "gitlab": {"project_path": "jinno-ai/my-new-project"},
        "azure_devops": {"organization": "jin5770808", "project": "tokyo-career-up"},
    },
}
```

### 方法B: 設定ファイルを使う（従来方式）

```yaml
# my_project_config.yaml
project:
  name: "my-project"
  org: "nobu007"              # GitHub組織/ユーザー（必須）
  repo: "my-repo"             # リポジトリ名（必須）
  provider: "github"          # github | ado | gitlab

  github:
    owner: "nobu007"
    repo: "my-repo"
    project_number: 2         # GitHub Projects V2 番号

  azure_devops:
    organization: "jin5770808"
    project: "tokyo-career-up"

epic:
  goal: "プロジェクトの目標を記述"  # 必須
  success_metrics:
    - metric: "KPI名"
      target: "目標値"
```

---

## 🚫 禁止事項

| ❌ やってはいけない | ✅ 正しい方法 |
|--------------------|--------------|
| 設定ファイルなしで実行 | 必ず `--config` を指定 |
| 認証なしで同期 | `gh auth status` / `az login` を先に実行 |
| `_registry` を直接編集 | `project_sync.py` 経由で更新 |
| ハードコードされたID | 統一キー形式を使用 |
| 日付付きファイル生成 | 固定ファイル名で上書き |

---

## 🔧 トラブルシューティング

### GitHub認証エラー

```bash
gh auth refresh -s project -s read:project
# ブラウザで認証を完了
```

### ADO認証エラー

```bash
az login
az devops configure --defaults organization=https://dev.azure.com/{org}
```

### 同期が途中で停止

```bash
# ドライランで確認
python project_sync.py --config config.yaml --provider github --dry-run

# データ本体の状態確認
ls -la output/_registry/{org}/{repo}/E00001/
```

### キー重複エラー

```bash
# レジストリをクリア（注意：データ消失）
rm -rf output/_registry/{org}/{repo}/
# 再同期
python project_sync.py --config config.yaml --provider github
```

---

## 📚 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| [README.md](./README.md) | ツール概要・クイックスタート |
| [docs/KEY_SPEC.md](./docs/KEY_SPEC.md) | 統一キー仕様 |
| [docs/DATA_ARCHITECTURE.md](./docs/DATA_ARCHITECTURE.md) | データ本体アーキテクチャ |
| [config_template.yaml](./config_template.yaml) | 設定ファイルテンプレート |

---

## 🔄 典型的なユースケース

### 新規プロジェクトの立ち上げ

```bash
# 1. 設定作成
cp config_template.yaml new_project_config.yaml
# 2. org, repo, epic.goal を編集
# 3. 全自動実行
python epic_manager.py --config new_project_config.yaml --mode full-pipeline
# 4. GitHub同期
python project_sync.py --config new_project_config.yaml \
    --decomposition output/{org}/{repo}/E00001/decomposition.json \
    --provider github
```

### 既存Epicへの追加

```bash
# decomposition.jsonを手動編集またはLLMで再生成
python llm_decomposer.py --config config.yaml --epic-id E00002

# 差分同期（新規のみ作成）
python project_sync.py --config config.yaml \
    --decomposition output/{org}/{repo}/E00002/decomposition.json \
    --provider github
```

### GitHub → ADO 移行

```bash
# GitHub Projectからエクスポート
python github_project_export.py --config config.yaml --output work_items.json

# ADOにインポート
python project_sync.py --config config.yaml --items work_items.json --provider ado
```

---

**このツールはデータ本体（`_registry`）を Source of Truth として管理します。**
**プロバイダー（GitHub/ADO/GitLab）はビュー/インターフェースに過ぎません。**
