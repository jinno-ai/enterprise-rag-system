# 統一キー仕様書 (KEY_SPEC)

## 概要

Epic-Driven Planning ツールキットで使用する**グローバル一意キー**の仕様。
100+プロジェクト × 100+Epic の全要素を一意に識別・管理する。

---

## 関連インストラクション（階層ナビゲーション）

> **このツールキットは指示書と統合して使用する**
>
> | 階層 | 指示書（md） | ツール（py） |
> |------|--------------|--------------|
> | Epic | [ado_epic_create.md](../../../instructions/software-development-phases/01-planning-requirements/02_epic/ado_epic_create.md) | `epic_generator.py` |
> | Feature | [ado_feature_create.md](../../../instructions/software-development-phases/01-planning-requirements/03_feature/ado_feature_create.md) | `epic_decomposer.py` |
> | Story | [ado_story_create.md](../../../instructions/software-development-phases/01-planning-requirements/04_story/ado_story_create.md) | `epic_decomposer.py` |
> | Task | [ado_task_create.md](../../../instructions/software-development-phases/01-planning-requirements/05_task/ado_task_create.md) | `task_decomposer.py` ★ |
>
> **汎用版**: [epic_driven_planning.md](../../epic_driven_planning.md)
> **統合管理**: `epic_manager.py` で全ステージを統合実行

---

## キー形式

```
{org}/{repo}/{epic_id}/{feature_id}/{story_id}/{task_id}

例:
jinno-ai/enterprise-rag-system/E00001/F00001/S00001/T00001
```

### 階層

| レベル | 形式 | 例 |
|--------|------|-----|
| Organization | `{org}` | `jinno-ai` |
| Project | `{org}/{repo}` | `jinno-ai/enterprise-rag-system` |
| Epic | `{org}/{repo}/{epic_id}` | `jinno-ai/enterprise-rag-system/E00001` |
| Feature | `.../{epic_id}/{feature_id}` | `.../E00001/F00001` |
| Story | `.../{feature_id}/{story_id}` | `.../F00001/S00001` |
| Task | `.../{story_id}/{task_id}` | `.../S00001/T00001` |

---

## 通番規則

### 設定値（KEY_CONFIG）

| 設定項目 | 値 | 説明 |
|----------|-----|------|
| `DIGITS` | **5** | 通番の桁数 |
| `EPIC_PREFIX` | `E` | Epic ID のプレフィックス |
| `FEATURE_PREFIX` | `F` | Feature ID のプレフィックス |
| `STORY_PREFIX` | `S` | Story ID のプレフィックス |
| `TASK_PREFIX` | `T` | Task ID のプレフィックス |
| `SEPARATOR` | `/` | キー階層の区切り文字 |

### 番号範囲

| 項目 | 形式 | 範囲 | 最大件数 |
|------|------|------|----------|
| Epic | `E00001` | 00001〜99999 | 99,999件/プロジェクト |
| Feature | `F00001` | 00001〜99999 | 99,999件/Epic |
| Story | `S00001` | 00001〜99999 | 99,999件/Feature |
| Task | `T00001` | 00001〜99999 | 99,999件/Story |

### 理論最大容量

```
100プロジェクト × 100Epic × 100Feature × 100Story × 10Task
= 1,000,000,000アイテム（10億）
```

---

## 上限超過時の挙動

### エラー

番号が `99999` を超えた場合、`KeyLimitExceededError` を送出：

```python
KeyLimitExceededError: Eの番号が上限を超えました: 100000 > 99999.
KEY_CONFIG.DIGITS を 6 に増やしてください。
```

### 対処方法

1. `key_management.py` の `KEY_CONFIG.DIGITS` を増やす（例: 5→6）
2. 既存データのマイグレーションスクリプトを実行（要作成）
3. 全プロジェクトの再同期

---

## ディレクトリ構造

### 出力フォルダ

```
output/
├── {org}/
│   └── {repo}/
│       └── {epic_id}/
│           ├── decomposition.json   # 統一キー形式
│           ├── schedule.json
│           └── sync_result.json
└── _registry/                        # キー→外部IDマッピング
    └── {org}/
        └── {repo}/
            ├── _index.json           # プロジェクトインデックス
            └── {epic_id}/
                └── {feature_id}/
                    └── {story_id}/
                        └── _item.json
```

### _item.json の形式

```json
{
  "key": "jinno-ai/enterprise-rag-system/E00001/F00001/S00001",
  "item_type": "story",
  "title": "基盤セットアップ",
  "data": { ... },
  "external_refs": {
    "github": "21",
    "gitlab": "456",
    "ado": "WI-789"
  },
  "created_at": "2026-01-27T15:00:00",
  "updated_at": "2026-01-27T16:00:00"
}
```

---

## レガシーID との互換性

### 変換規則

| レガシーID | 統一キー |
|------------|----------|
| `F1` | `{org}/{repo}/E00001/F00001` |
| `F1-S1` | `{org}/{repo}/E00001/F00001/S00001` |
| `F12-S34` | `{org}/{repo}/E00001/F00012/S00034` |

### 変換関数

```python
from key_management import KeyGenerator

gen = KeyGenerator('jinno-ai', 'enterprise-rag-system')
key = gen.from_legacy_id('F1-S1')
# => jinno-ai/enterprise-rag-system/E00001/F00001/S00001
```

---

## 設定変更方法

### 桁数を変更する場合

**⚠️ 破壊的変更**: 既存データとの互換性が失われる

1. `key_management.py` を編集:

```python
@dataclass(frozen=True)
class KeyConfig:
    DIGITS: int = 6  # 5 → 6 に変更
```

2. マイグレーションスクリプトを実行（未実装）

3. 全プロジェクトを再同期

---

## 関連ファイル

| ファイル | 役割 |
|----------|------|
| `key_management.py` | 統一キー管理モジュール（実装） |
| `epic_manager.py` | パイプライン統合（キー使用） |
| `providers/base_provider.py` | プロバイダー基底（unified_keyフィールド） |
| `docs/KEY_SPEC.md` | この仕様書 |

---

## チェックリスト

新規開発・修正時に確認：

- [ ] キー生成は `KeyGenerator` を使用しているか
- [ ] ハードコードされた桁数（`:03d` など）がないか
- [ ] `KEY_CONFIG` を参照しているか
- [ ] 上限超過エラー処理があるか
- [ ] レジストリに外部IDを保存しているか
