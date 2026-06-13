# Feature テンプレート

> Epicを構成する機能のかたまり（1〜2スプリントで完了可能）

---

## Feature: ${TITLE}

**Epic**: ${PARENT_EPIC}
**ID**: ${FEATURE_ID}
**優先度**: ${PRIORITY}
**マイルストーン**: ${MILESTONE}

### 概要（Overview）

${DESCRIPTION}

### ビジネス価値（Business Value）

このFeatureが完了することで:

- ${VALUE_1}
- ${VALUE_2}

### スコープ（Scope）

#### 含む範囲

- ${SCOPE_IN_1}
- ${SCOPE_IN_2}

#### 含まない範囲

- ${SCOPE_OUT_1}

### 依存関係（Dependencies）

| 依存先 | 理由 | 影響 |
|--------|------|------|
| ${DEP_1} | ${DEP_1_REASON} | ${DEP_1_IMPACT} |

### ストーリー一覧（Stories）

| ID | タイトル | 工数 | 優先度 | 依存 |
|----|---------|------|--------|------|
| ${STORY_1_ID} | ${STORY_1_TITLE} | ${STORY_1_ESTIMATE}h | ${STORY_1_PRIORITY} | ${STORY_1_DEPS} |
| ${STORY_2_ID} | ${STORY_2_TITLE} | ${STORY_2_ESTIMATE}h | ${STORY_2_PRIORITY} | ${STORY_2_DEPS} |
| ${STORY_3_ID} | ${STORY_3_TITLE} | ${STORY_3_ESTIMATE}h | ${STORY_3_PRIORITY} | ${STORY_3_DEPS} |

**合計工数**: ${TOTAL_HOURS}h

### 受け入れ条件（Acceptance Criteria）

Feature全体の完了条件:

- [ ] ${AC_1}
- [ ] ${AC_2}
- [ ] ${AC_3}

### リリース可能性（Release Readiness）

| 項目 | 状態 | 備考 |
|------|------|------|
| 独立リリース可能か | ${INDEPENDENTLY_RELEASABLE} | ${RELEASE_NOTES} |
| ロールバック可能か | ${ROLLBACK_CAPABLE} | ${ROLLBACK_NOTES} |
| 段階的リリース可能か | ${GRADUAL_RELEASE} | ${GRADUAL_NOTES} |

---

## 品質チェックリスト

Feature作成時に以下を確認:

- [ ] 1〜2スプリントで完了できる粒度か？
- [ ] 独立してリリース可能か？
- [ ] 3〜5個のStoryに分解されているか？
- [ ] 各Storyには具体的なAcceptance Criteriaがあるか？
- [ ] 依存関係が明確か？
