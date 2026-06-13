#!/bin/bash
# GitHub Project Roadmap 日付設定スクリプト
# micro-instruction-engineering 用

PROJECT_ID="PVT_kwHODwwlh84BNkwz"
START_FIELD="PVTF_lAHODwwlh84BNkwzzg8h9d0"
END_FIELD="PVTF_lAHODwwlh84BNkwzzg8h9k4"

set_dates() {
    local ITEM_ID=$1
    local START=$2
    local END=$3
    local ISSUE=$4

    # Start Date
    gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\" itemId: \"$ITEM_ID\" fieldId: \"$START_FIELD\" value: { date: \"$START\" } }) { projectV2Item { id } } }" > /dev/null 2>&1

    # End Date
    gh api graphql -f query="mutation { updateProjectV2ItemFieldValue(input: { projectId: \"$PROJECT_ID\" itemId: \"$ITEM_ID\" fieldId: \"$END_FIELD\" value: { date: \"$END\" } }) { projectV2Item { id } } }" > /dev/null 2>&1

    echo "  ✅ #$ISSUE: $START - $END"
}

echo "🗓️ Roadmap日付設定開始"
echo ""
echo "=== Sprint 1: 基盤構築 (2/3-2/14) ==="
set_dates "PVTI_lAHODwwlh84BNkwzzgkTxsQ" "2026-02-03" "2026-02-14" "4 (F1)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTxsk" "2026-02-03" "2026-02-05" "8 (S1.1)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTxtE" "2026-02-06" "2026-02-09" "9 (S1.2)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTxts" "2026-02-10" "2026-02-14" "10 (S1.3)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx5g" "2026-02-03" "2026-02-14" "27 (F5)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx6c" "2026-02-03" "2026-02-06" "28 (S5.1)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx8M" "2026-02-07" "2026-02-10" "29 (S5.2)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx8w" "2026-02-11" "2026-02-14" "30 (S5.3)"

echo ""
echo "=== Sprint 2: 推論技法 (2/17-2/28) ==="
set_dates "PVTI_lAHODwwlh84BNkwzzgkTxxw" "2026-02-17" "2026-02-28" "12 (F2)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTxyM" "2026-02-17" "2026-02-20" "13 (S2.1)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTxzQ" "2026-02-21" "2026-02-24" "14 (S2.2)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx0o" "2026-02-25" "2026-02-28" "15 (S2.3)"

echo ""
echo "=== Sprint 3: DSPy統合 (3/3-3/14) ==="
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx1M" "2026-03-03" "2026-03-14" "17 (F3)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx1w" "2026-03-03" "2026-03-06" "18 (S3.1)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx2o" "2026-03-07" "2026-03-10" "19 (S3.2)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx3U" "2026-03-11" "2026-03-14" "20 (S3.3)"

echo ""
echo "=== Sprint 4: TextGrad+CLI (3/17-3/28) ==="
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx4E" "2026-03-17" "2026-03-25" "22 (F4)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkT2R0" "2026-03-17" "2026-03-19" "23 (S4.1)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkT2VI" "2026-03-20" "2026-03-22" "24 (S4.2)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx5E" "2026-03-23" "2026-03-25" "25 (S4.3)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTx9Q" "2026-03-17" "2026-03-28" "32 (F6)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTyDE" "2026-03-17" "2026-03-22" "33 (S6.1)"
set_dates "PVTI_lAHODwwlh84BNkwzzgkTyCQ" "2026-03-23" "2026-03-28" "34 (S6.2)"

echo ""
echo "📊 日付設定完了！"
echo "🔗 Roadmap確認: https://github.com/users/jinno-ai/projects/5/views/1"
