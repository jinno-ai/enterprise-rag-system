# Active AUTO Decisions (cache) — safe to delete

## AUTO:autopilot.lint:no_lint_gate
- Status: ACTIVE
- Chosen: lint ゲートなし、test ゲート（pytest）のみ
- Policy: locality + industry_convention
- Expires After Runs: 20
- Linked: AMB-AUTO-001
- Revert Triggers: lint 設定ファイルの追加

## AUTO:ResultRanker.batch_pairing:index_based
- Status: ACTIVE
- Chosen: バッチ経路にも index ベース・ペアリングを適用（helper 共有化は後続）
- Policy: reversibility + blast_radius_min
- Expires After Runs: 20
- Linked: AMB-AUTO-002 / CFLT-RANK-001
- Revert Triggers: primary_evidence_contradiction
