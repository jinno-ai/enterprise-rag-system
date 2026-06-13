# Epic テンプレート

> このテンプレートは `epic_driven_planning.md` の原則に従って設計されています

## タイトル形式

**[対象ユーザー]に[価値]を提供する** または **[目標成果]を達成する**

---

## Epic: ${TITLE}

### 背景（Background）

${BACKGROUND}

### 目的（Objective）

${OBJECTIVE}

### ビジネス価値（Business Value）

| 項目 | 内容 |
|------|------|
| 対象ユーザー | ${TARGET_USERS} |
| 期待成果 | ${EXPECTED_OUTCOME} |
| 測定可能KPI | ${KPI} |

### スコープ（Scope）

#### In Scope（含む範囲）

${IN_SCOPE}

#### Out of Scope（含まない範囲）

${OUT_OF_SCOPE}

### 前提条件と制約（Assumptions & Constraints）

| 区分 | 内容 |
|------|------|
| 技術的前提 | ${TECHNICAL_ASSUMPTIONS} |
| リソース制約 | ${RESOURCE_CONSTRAINTS} |
| 期間制約 | ${TIMELINE_CONSTRAINTS} |

### 成功指標（Success Metrics）

| 指標 | 目標値 | 現在値 | 測定方法 |
|------|--------|--------|----------|
| ${METRIC_1_NAME} | ${METRIC_1_TARGET} | ${METRIC_1_CURRENT} | ${METRIC_1_METHOD} |
| ${METRIC_2_NAME} | ${METRIC_2_TARGET} | ${METRIC_2_CURRENT} | ${METRIC_2_METHOD} |

### ステークホルダー（Stakeholders）

| 役割 | 担当者 | 責務 |
|------|--------|------|
| Epic Owner | ${EPIC_OWNER} | ビジネス価値の定義・優先順位の最終決定 |
| Technical Lead | ${TECHNICAL_LEAD} | 技術的実現可能性・アーキテクチャ判断 |
| 関連チーム | ${RELATED_TEAMS} | ${TEAM_RESPONSIBILITIES} |

### 受け入れ条件（Acceptance Criteria）

Epicの完了を判定するための客観的条件:

- [ ] ${AC_1}
- [ ] ${AC_2}
- [ ] ${AC_3}
- [ ] ${AC_4}
- [ ] ${AC_5}

### マイルストーン（Milestones）

| ID | 名前 | 期日 | 成果物 |
|----|------|------|--------|
| M1 | ${MILESTONE_1_NAME} | ${MILESTONE_1_DUE} | ${MILESTONE_1_DELIVERABLE} |
| M2 | ${MILESTONE_2_NAME} | ${MILESTONE_2_DUE} | ${MILESTONE_2_DELIVERABLE} |
| M3 | ${MILESTONE_3_NAME} | ${MILESTONE_3_DUE} | ${MILESTONE_3_DELIVERABLE} |

---

## 品質チェックリスト

Epic作成時に以下を確認:

- [ ] タイトルはビジネスゴールを1文で表現しているか？
- [ ] 背景・目的・ビジネス価値が明確に記述されているか？
- [ ] In Scope / Out of Scope が定義されているか？
- [ ] 受け入れ条件が 3〜7個、測定可能な形で記載されているか？
- [ ] Epic Owner と Technical Lead が明記されているか？
- [ ] 1〜3か月で完了できる粒度か？
- [ ] Feature / Story への分解案が用意されているか？
