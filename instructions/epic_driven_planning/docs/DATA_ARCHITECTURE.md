# データ本体（Source of Truth）アーキテクチャ

## 概要

GitHub / GitLab / Azure DevOps (ADO) に同期する**データ本体**の構成。
プロバイダーは変更可能だが、データ本体は統一キー体系で管理される。

## ディレクトリ構造

```
output/
├── {org}/                          # 組織/ユーザー
│   └── {repo}/                     # リポジトリ
│       └── {epic_id}/              # E00001
│           ├── features.json       # Feature分解結果
│           ├── decomposition.json  # 分解結果（Story + Task）
│           ├── schedule.json       # スケジュール
│           └── sync_result.json    # 同期結果
│
└── _registry/                      # データ本体（Source of Truth）
    └── {org}/
        └── {repo}/
            ├── _index.json         # プロジェクトインデックス
            └── {epic_id}/
                ├── _item.json      # Epic本体
                └── {feature_id}/
                    ├── _item.json  # Feature本体
                    └── {story_id}/
                        ├── _item.json  # Story本体
                        └── {task_id}/
                            └── _item.json  # Task本体 ★
```

## 統一キー形式（KEY_SPEC）

```
{org}/{repo}/{epic_id}/{feature_id}/{story_id}/{task_id}

例:
nobu007/tokyo_career_up/E00001/F00001/S00001/T00001
```

### 番号体系

| 項目 | 形式 | 範囲 | 最大件数 |
|------|------|------|----------|
| Epic | `E00001` | 00001〜99999 | 99,999件/プロジェクト |
| Feature | `F00001` | 00001〜99999 | 99,999件/Epic |
| Story | `S00001` | 00001〜99999 | 99,999件/Feature |
| Task | `T00001` | 00001〜99999 | 99,999件/Story |

**理論最大容量**: 100プロジェクト × 100Epic × 100Feature × 100Story × 10Task = **100億アイテム**

## _item.json 形式

```json
{
  "key": "nobu007/tokyo_career_up/E00001/F00001/S00001",
  "item_type": "story",
  "title": "助成金コースマスタデータ設計・実装",
  "data": {
    "description": "...",
    "acceptance_criteria": [...],
    "estimate_hours": 8,
    "priority": "high",
    "labels": [...]
  },
  "external_refs": {
    "github": "42",          # GitHub Issue番号
    "gitlab": "123",         # GitLab Issue ID
    "ado": "WI-789"          # ADO WorkItem ID
  },
  "created_at": "2026-01-28T00:00:00",
  "updated_at": "2026-01-28T12:00:00"
}
```

## 同期フロー

```
┌─────────────────────────────────────────────────────────┐
│                    データ本体                            │
│                 (_registry/*.json)                       │
│                                                          │
│   nobu007/tokyo_career_up/E00001/F00001/S00001          │
│   ├── key: 統一キー                                      │
│   ├── data: 具体的な内容                                 │
│   └── external_refs: 各プロバイダーのID                   │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   GitHub     │ │   GitLab     │ │   ADO        │
│  Projects V2 │ │   Issues     │ │  WorkItems   │
├──────────────┤ ├──────────────┤ ├──────────────┤
│ Issue #42    │ │ Issue #123   │ │ WI-789       │
└──────────────┘ └──────────────┘ └──────────────┘
```

## 同期の原則

1. **データ本体が正（Source of Truth）**
   - _registry の内容が正しい
   - プロバイダーはデータ本体を反映

2. **作成順序**
   - まず _registry にデータ本体を作成
   - 次に各プロバイダーに同期
   - external_refs に外部IDを記録

3. **更新時**
   - データ本体を更新
   - 変更をプロバイダーに伝播
   - external_refs で紐付け

4. **削除時**
   - データ本体から削除
   - プロバイダーのIssue/WorkItemはクローズ（削除しない）

## 組織名の統一

| プロバイダー | 組織名 | 備考 |
|-------------|--------|------|
| GitHub | `nobu007` | GitHubユーザー名（正） |
| GitLab | `nobu007` | 同一 |
| ADO | `jinno-ai` | ADO組織名（異なる場合あり） |

## 現在のプロジェクト

| プロジェクト | 統一キー基点 | GitHub | ADO |
|-------------|-------------|--------|-----|
| tokyo_career_up | `nobu007/tokyo_career_up` | `nobu007/tokyo_career_up` | `jinno-ai/tokyo-career-up` |

## 使用方法

### 1. データ本体の作成

```bash
# decomposition.jsonから_registryを生成
python key_management.py --generate-registry \
    --input output/nobu007/tokyo_career_up/E00001/decomposition.json
```

### 2. GitHubに同期

```bash
python project_sync.py \
    --config tokyo_career_up_config.yaml \
    --decomposition output/nobu007/tokyo_career_up/E00001/decomposition.json \
    --provider github
```

### 3. ADOに同期

```bash
python project_sync.py \
    --config tokyo_career_up_config.yaml \
    --decomposition output/nobu007/tokyo_career_up/E00001/decomposition.json \
    --provider ado
```

### 4. 外部IDの確認

```bash
# 特定アイテムの外部IDを確認
cat output/_registry/nobu007/tokyo_career_up/E00001/F00001/S00001/_item.json | jq '.external_refs'
```
