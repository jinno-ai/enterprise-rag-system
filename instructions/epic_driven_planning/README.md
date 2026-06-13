# Epic-Driven Planning ツールキット

> Epic → Feature → Story → Task の段階的分解・品質チェック・スケジューリング・プロバイダー同期を提供する汎用ツール群

## 概要

このツールキットは、`01-planning-requirements` インストラクションを完全に自動実行するためのスクリプトを提供します。
**リポジトリ固有の情報は全て引数/設定ファイルで渡す**設計のため、任意のプロジェクトに適用可能です。

## 対応インストラクション（01-planning-requirements）

| ステージ | インストラクション | ツール/モード |
|----------|-------------------|---------------|
| Epic | `02_epic/ado_epic_create.md` | `--mode epic` |
| Feature | `03_feature/ado_feature_create.md` | `--mode feature` |
| Story | `04_story/ado_story_create.md` | `--mode story` |
| Task | `05_task/ado_task_create.md` | `--mode task` |

## ツール構成

```
epic_driven_planning/
├── README.md                    # このファイル
├── AGENTS.md                    # AIエージェント向け指示書
├── config_template.yaml         # 設定ファイルテンプレート
│
├── epic_manager.py              # ★ メイン統合スクリプト（全ステージ管理）
├── epic_generator.py            # Epic生成（02_epic）
├── epic_decomposer.py           # Feature/Story分解（03_feature, 04_story）
├── task_decomposer.py           # Task分解（05_task）★ NEW
├── epic_validator.py            # 品質チェック
├── schedule_optimizer.py        # 依存関係解析・自動スケジューリング
│
├── project_sync.py              # プロバイダー同期（GitHub/GitLab/ADO）
├── github_project_export.py     # GitHub Project -> WorkItem JSON 変換
├── github_sync.py               # GitHub連携（レガシー）
├── llm_decomposer.py            # LLMベース動的分解
│
├── key_management.py            # 統一キー管理（KEY_SPEC準拠）
├── providers/                   # プロバイダー実装
│   ├── __init__.py              # プロバイダーファクトリ
│   ├── base_provider.py         # 抽象基底クラス
│   ├── github_provider.py       # GitHub Projects V2
│   ├── gitlab_provider.py       # GitLab Issues/Boards
│   └── ado_provider.py          # Azure DevOps Work Items
│
├── templates/                   # テンプレート
│   ├── epic_template.md
│   ├── feature_template.md
│   └── story_template.md
│
├── docs/                        # 詳細仕様
│   ├── KEY_SPEC.md              # 統一キー仕様
│   └── DATA_ARCHITECTURE.md     # データ本体アーキテクチャ
│
└── output/                      # 出力ディレクトリ
    ├── {org}/{repo}/{epic_id}/  # プロジェクト別出力
    └── _registry/               # データ本体（Source of Truth）
```

## クイックスタート

### 1. 設定ファイルの作成

```bash
cd hub/instructions/epic_driven_planning
cp config_template.yaml my_project_config.yaml
# org, repo, epic.goal を編集
```

### 2. 全自動パイプライン（推奨）

```bash
# 01-planning-requirements を完全実行（7ステージ）
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

### 3. 個別ステップ実行（01-planning-requirements 準拠）

```bash
# 02_epic: Epic生成（ビジネスゴール定義）
python epic_manager.py --config config.yaml --mode epic

# 03_feature: Feature分解（1-2スプリントの機能単位）
python epic_manager.py --config config.yaml --mode feature

# 04_story: Story分解（1スプリント内で完了、INVEST原則）
python epic_manager.py --config config.yaml --mode story

# 05_task: Task分解（2-8時間の技術タスク）
python epic_manager.py --config config.yaml --mode task

# 品質チェック
python epic_manager.py --config config.yaml --mode validate

# スケジュール最適化
python epic_manager.py --config config.yaml --mode schedule

# プロバイダー同期
python epic_manager.py --config config.yaml --mode sync
```

### 4. プロバイダー同期（3環境対応）

```bash
# ============================================
# 推奨: multi_provider_sync.py（一発コマンド）
# ============================================

# 3環境すべてに同期
python multi_provider_sync.py \
    --github nobu007 ai-hub \
    --gitlab jinno-ai/enterprise-rag-system \
    --ado jin5770808 tokyo-career-up

# 個別プロバイダー
python multi_provider_sync.py --github nobu007 ai-hub
python multi_provider_sync.py --gitlab jinno-ai/enterprise-rag-system
python multi_provider_sync.py --ado jin5770808 tokyo-career-up

# ============================================
# 代替: project_sync.py（プロジェクトID指定）
# ============================================

# プロジェクト一覧表示
python project_sync.py --list-projects

# 全環境同期
python project_sync.py \
    --project enterprise-rag-system \
    --decomposition output/decomposition.json \
    --all-providers

# ============================================
# 従来方式（設定ファイル指定）
# ============================================

# GitHub Projects V2 へ同期
python project_sync.py \
    --config config.yaml \
    --decomposition output/{org}/{repo}/E00001/decomposition.json \
    --provider github

# Azure DevOps へ同期
python project_sync.py \
    --config config.yaml \
    --decomposition output/{org}/{repo}/E00001/decomposition.json \
    --provider ado

# GitLab へ同期
python project_sync.py \
    --config config.yaml \
    --decomposition output/{org}/{repo}/E00001/decomposition.json \
    --provider gitlab

# ドライラン（実際には実行しない）
python project_sync.py \
    --config config.yaml \
    --decomposition output/{org}/{repo}/E00001/decomposition.json \
    --provider github \
    --dry-run
```

## プロジェクト・組織 一元管理

`project_sync.py` の `PROJECT_REGISTRY` で登録済みプロジェクトを管理：

| プロジェクトID | GitHub | GitLab | Azure DevOps |
|--------------|--------|--------|--------------|
| `enterprise-rag-system` | nobu007/enterprise-rag-system | jinno-ai/enterprise-rag-system | jin5770808/tokyo-career-up |
| `ai-hub` | nobu007/ai-hub | jinno-ai/ai-hub | jin5770808/tokyo-career-up |
| `realtime-edge-detection` | jinno-ai/realtime-edge-detection | jinno-ai/realtime-edge-detection | jin5770808/tokyo-career-up |
| `llm-agent-framework` | jinno-ai/llm-agent-framework | jinno-ai/llm-agent-framework | jin5770808/tokyo-career-up |

新規プロジェクト追加は `project_sync.py` の `PROJECT_REGISTRY` を編集してください。

## 設定ファイル例

```yaml
# my_project_config.yaml
project:
  name: "enterprise-rag-system"
  org: "nobu007"                  # 組織/ユーザー（必須）
  repo: "enterprise-rag-system"   # リポジトリ名（必須）
  provider: "github"              # github | gitlab | ado
  output_dir: "output"

  github:
    owner: "nobu007"
    repo: "enterprise-rag-system"
    project_number: 2             # GitHub Projects V2 番号

  gitlab:
    host: "https://gitlab.com"
    project_id: "jinno-ai/enterprise-rag-system"
    group_id: ""                  # Epic用（Premium機能）

  azure_devops:
    organization: "jin5770808"    # 正しい組織名
    project: "tokyo-career-up"    # 正しいプロジェクト名（ハイフン）
    # pat: ""                     # AZURE_DEVOPS_PAT 推奨

schedule:
  start_date: "2026-01-27"
  hours_per_day: 8
  working_days: [0, 1, 2, 3, 4]   # 月-金

epic:
  id: "E00001"                    # Epic ID（省略時は自動生成）
  goal: "社内RAGシステムを構築し、情報検索時間を70%削減する"
  success_metrics:
    - metric: "検索レイテンシ"
      target: "P95 3秒以内"
    - metric: "精度"
      target: "適合率80%以上"
```

## 環境変数

| 変数 | 用途 | 設定方法 |
|------|------|---------|
| `GITHUB_TOKEN` | GitHub API | `gh auth login` で自動設定 |
| `GITLAB_TOKEN` | GitLab API | `export GITLAB_TOKEN="glpat-xxxx"` |
| `AZURE_DEVOPS_PAT` | ADO API | `export AZURE_DEVOPS_PAT="xxxx"` |
| `AZURE_DEVOPS_EXT_PAT` | ADO API（代替） | `export AZURE_DEVOPS_EXT_PAT="xxxx"` |

## 主要コマンド

| コマンド | 説明 | 対応インストラクション |
|---------|------|----------------------|
| `epic_manager.py --mode full-pipeline` | 全自動パイプライン | 01-planning-requirements 全体 |
| `epic_manager.py --mode epic` | Epic生成 | 02_epic |
| `epic_manager.py --mode feature` | Feature分解 | 03_feature |
| `epic_manager.py --mode story` | Story分解 | 04_story |
| `epic_manager.py --mode task` | Task分解 | 05_task |
| `epic_manager.py --mode validate` | 品質チェック | - |
| `epic_manager.py --mode schedule` | スケジュール最適化 | - |
| `epic_manager.py --mode sync` | プロバイダー同期 | - |
| `task_decomposer.py` | Task分解（単独実行） | 05_task |
| **`multi_provider_sync.py`** | **3環境同時同期（推奨）** | - |
| `project_sync.py --list-projects` | 登録プロジェクト一覧 | - |
| `project_sync.py --project X --all-providers` | 全環境同期 | - |
| `project_sync.py --provider github` | GitHub同期 | - |
| `project_sync.py --provider ado` | ADO同期 | - |
| `project_sync.py --provider gitlab` | GitLab同期 | - |

## パイプライン詳細

### 各ステージの入出力

| ステージ | 入力 | 出力 | 品質基準 |
|----------|------|------|----------|
| **epic** | config.yaml | Epic定義 | ビジネスゴール、測定可能な完了条件 |
| **feature** | Epic | features.json | 1-2スプリント完了、3-7 Story に分解可能 |
| **story** | features.json | decomposition.json | INVEST原則、Story Points、AC |
| **task** | decomposition.json | decomposition.json（Task追加） | 2-8時間、単一責務 |
| **validate** | decomposition.json | 検証結果 | 品質基準チェック |
| **schedule** | decomposition.json | schedule.json | 依存関係解析、日程最適化 |
| **sync** | decomposition.json + schedule.json | GitHub/ADO Issues | Issue/WorkItem 作成 |

### Task カテゴリ（05_task 準拠）

| カテゴリ | 説明 | 見積もり目安 |
|----------|------|-------------|
| implementation | コード実装 | 4時間 |
| test | テスト作成 | 2時間 |
| review | コードレビュー | 1時間 |
| documentation | ドキュメント作成 | 1時間 |
| investigation | 技術調査 | 2時間 |
| config | 設定・構成 | 2時間 |

## 統一キー仕様（KEY_SPEC）

```
{org}/{repo}/{epic_id}/{feature_id}/{story_id}/{task_id}

例: nobu007/enterprise-rag-system/E00001/F00001/S00001/T00001
```

| レベル | 形式 | 最大件数 |
|--------|------|----------|
| Epic | `E00001` | 99,999件/プロジェクト |
| Feature | `F00001` | 99,999件/Epic |
| Story | `S00001` | 99,999件/Feature |
| Task | `T00001` | 99,999件/Story |

詳細: [docs/KEY_SPEC.md](docs/KEY_SPEC.md)

## データ本体（Source of Truth）

```
output/_registry/
└── {org}/
    └── {repo}/
        └── E00001/
            ├── _item.json           # Epic本体
            └── F00001/
                ├── _item.json       # Feature本体
                └── S00001/
                    ├── _item.json   # Story本体
                    └── T00001/
                        └── _item.json   # Task本体
```

詳細: [docs/DATA_ARCHITECTURE.md](docs/DATA_ARCHITECTURE.md)

## プロバイダー対応状況

| プロバイダー | 状態 | 機能 |
|-------------|------|------|
| **GitHub** | ✅ 実装済み | Issues作成, Projects V2連携, カスタムフィールド |
| **GitLab** | ✅ 実装済み | Issues作成/更新, Epics（Premium）, ラベル/マイルストーン |
| **Azure DevOps** | ✅ 実装済み | Work Items 作成/更新, 親子リンク, ステート管理 |

### 認証方法

```bash
# GitHub
gh auth login
gh auth refresh -s project -s read:project

# Azure DevOps
az login
az devops configure --defaults organization=https://dev.azure.com/{org}

# GitLab
export GITLAB_TOKEN="glpat-xxxxx"
# または
glab auth login
```

## 設計原則

1. **インストラクション準拠**: 01-planning-requirements の各ステップを忠実に実行
2. **段階的分解**: Epic → Feature → Story → Task の明確な階層
3. **リポジトリ非依存**: 全ての固有情報は設定ファイル/引数で渡す
4. **プロバイダー抽象化**: 同じインターフェースでGitHub/GitLab/ADOに対応
5. **冪等性**: 同じ入力に対して同じ出力を保証
6. **検証ファースト**: 変更前に必ずバリデーションを実行
7. **ドライラン対応**: `--dry-run` で変更内容をプレビュー

## インストラクションとの連携

このツールキットは以下のインストラクションと連携します:

| インストラクション | 連携ツール | 用途 |
|-------------------|-----------|------|
| `02_epic/ado_epic_create.md` | `epic_generator.py` | Epic生成 |
| `03_feature/ado_feature_create.md` | `epic_decomposer.py` | Feature分解 |
| `04_story/ado_story_create.md` | `epic_decomposer.py` | Story分解 |
| `05_task/ado_task_create.md` | `task_decomposer.py` | Task分解 |
| `epic_driven_planning.md` | `epic_manager.py` | 統合管理 |

## トラブルシューティング

### GitHub認証エラー

```bash
gh auth refresh -s project -s read:project
```

### ADO認証エラー

```bash
az login
az devops configure --defaults organization=https://dev.azure.com/{org}
```

### Task分解がスキップされる

```bash
# story ステージを先に実行
python epic_manager.py --config config.yaml --mode story
# その後 task ステージを実行
python epic_manager.py --config config.yaml --mode task
```

### decomposition.json が見つからない

```bash
# feature → story の順で実行
python epic_manager.py --config config.yaml --mode feature
python epic_manager.py --config config.yaml --mode story
```

## ライセンス

内部利用専用
