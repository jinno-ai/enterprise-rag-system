# Story テンプレート

> ユーザーに価値を届ける最小単位（1スプリント以内で完了可能）

---

## Story: ${TITLE}

**Feature**: ${PARENT_FEATURE}
**ID**: ${STORY_ID}
**優先度**: ${PRIORITY}
**工数見積**: ${ESTIMATE_HOURS}h

### ユーザーストーリー形式

> **As a** ${USER_ROLE},
> **I want** ${USER_GOAL},
> **So that** ${USER_BENEFIT}.

### 概要（Overview）

${DESCRIPTION}

### 依存関係（Dependencies）

- **Depends on**: ${DEPENDENCIES}
- **Blocks**: ${BLOCKS}

### 受け入れ条件（Acceptance Criteria）

このStoryの完了を判定する条件:

- [ ] **Given** ${GIVEN_1}, **When** ${WHEN_1}, **Then** ${THEN_1}
- [ ] **Given** ${GIVEN_2}, **When** ${WHEN_2}, **Then** ${THEN_2}
- [ ] ${AC_3}
- [ ] ${AC_4}

### 技術的詳細（Technical Notes）

#### 実装方針

${IMPLEMENTATION_APPROACH}

#### 影響範囲

- ファイル: ${AFFECTED_FILES}
- API: ${AFFECTED_APIS}
- DB: ${AFFECTED_DB}

### テスト観点（Test Considerations）

| テスト種別 | 内容 | 優先度 |
|-----------|------|--------|
| ユニットテスト | ${UNIT_TEST} | ${UNIT_PRIORITY} |
| 結合テスト | ${INTEGRATION_TEST} | ${INTEGRATION_PRIORITY} |
| E2Eテスト | ${E2E_TEST} | ${E2E_PRIORITY} |

### 完了の定義（Definition of Done）

- [ ] コードレビュー完了
- [ ] テストカバレッジ80%以上
- [ ] ドキュメント更新
- [ ] 受け入れ条件すべて満たす

### ラベル

```
estimate:${ESTIMATE_HOURS}h
priority:${PRIORITY}
feature:${PARENT_FEATURE_ID}
```

---

## 品質チェックリスト

Story作成時に以下を確認:

- [ ] 1スプリント（40h）以内で完了できるか？
- [ ] 受け入れ条件が具体的・測定可能か？
- [ ] 工数見積が設定されているか？
- [ ] 依存関係が明確か？
- [ ] ユーザーへの価値が明確か？
