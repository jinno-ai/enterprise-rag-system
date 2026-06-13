#!/bin/bash
# GitHub Project日程自動設定スクリプト
# ラベルの工数から開始日・終了日を自動計算

set -e

OWNER="jinno-ai"
PROJECT_NUMBER=1
PROJECT_ID="PVT_kwHODwwlh84BNjPl"
START_DATE_FIELD="PVTF_lAHODwwlh84BNjPlzg8hKEw"
END_DATE_FIELD="PVTF_lAHODwwlh84BNjPlzg8hKFw"
ESTIMATE_FIELD="PVTF_lAHODwwlh84BNjPlzg8hKGc"

# 1日の作業時間（時間）
HOURS_PER_DAY=8

# 今日の日付
TODAY="2026-01-27"

echo "=== GitHub Project 日程自動設定 ==="
echo "開始基準日: $TODAY"
echo ""

# 依存関係とスケジュールの定義
# 依存関係を考慮した順序（クリティカルパス）
# Phase 1: #9, #14 (並列実行可能、依存なし)
# Phase 2: #12 (依存: #14)
# Phase 3: #15 (依存: #12, #14)
# Phase 4: #10, #13, #7 (依存: #15)

declare -A SCHEDULE
# Issue番号: "開始日 終了日 工数"

# === M1: コード品質基盤整備 ===
# Phase 1 (並列): 1/27開始
SCHEDULE[9]="2026-01-27 2026-01-27 4"   # 脆弱性スキャン 4h = 0.5日 → 1日
SCHEDULE[14]="2026-01-27 2026-01-27 4"  # ハードコード排除 4h = 0.5日 → 1日

# Phase 2: #14完了後 (1/28開始)
SCHEDULE[12]="2026-01-28 2026-01-28 8"  # ロギング 8h = 1日

# Phase 3: #12完了後 (1/29開始)
SCHEDULE[15]="2026-01-29 2026-01-29 8"  # DI導入 8h = 1日

# === M2: パフォーマンス最適化 ===
# Phase 4: #15完了後 (1/30開始、並列可能)
SCHEDULE[10]="2026-01-30 2026-01-30 8"  # テスト整備 8h = 1日
SCHEDULE[13]="2026-01-30 2026-01-30 8"  # 非同期化 8h = 1日
SCHEDULE[7]="2026-01-31 2026-01-31 4"   # Prometheus 4h = 0.5日 → 1日

echo "📅 スケジュール一覧:"
echo "┌────────┬────────────┬────────────┬──────┐"
echo "│ Issue  │ 開始日     │ 終了日     │ 工数 │"
echo "├────────┼────────────┼────────────┼──────┤"

for issue in 9 14 12 15 10 13 7; do
    IFS=' ' read -r start end hours <<< "${SCHEDULE[$issue]}"
    printf "│ #%-5s │ %s │ %s │ %2sh  │\n" "$issue" "$start" "$end" "$hours"
done

echo "└────────┴────────────┴────────────┴──────┘"
echo ""

# アイテムIDマッピング
declare -A ITEM_IDS
ITEM_IDS[7]="PVTI_lAHODwwlh84BNjPlzgkSaoc"
ITEM_IDS[9]="PVTI_lAHODwwlh84BNjPlzgkSaog"
ITEM_IDS[10]="PVTI_lAHODwwlh84BNjPlzgkSaoo"
ITEM_IDS[12]="PVTI_lAHODwwlh84BNjPlzgkSaos"
ITEM_IDS[13]="PVTI_lAHODwwlh84BNjPlzgkSaow"
ITEM_IDS[14]="PVTI_lAHODwwlh84BNjPlzgkSao0"
ITEM_IDS[15]="PVTI_lAHODwwlh84BNjPlzgkSao8"

echo "🔄 プロジェクト更新中..."
echo ""

for issue in 9 14 12 15 10 13 7; do
    IFS=' ' read -r start end hours <<< "${SCHEDULE[$issue]}"
    item_id="${ITEM_IDS[$issue]}"

    echo "  Updating #$issue (Start: $start, End: $end, Hours: $hours)..."

    # Start Date更新
    gh project item-edit --project-id "$PROJECT_ID" --id "$item_id" \
        --field-id "$START_DATE_FIELD" --date "$start" 2>/dev/null || echo "    ⚠️ Start Date failed"

    # End Date更新
    gh project item-edit --project-id "$PROJECT_ID" --id "$item_id" \
        --field-id "$END_DATE_FIELD" --date "$end" 2>/dev/null || echo "    ⚠️ End Date failed"

    # Estimate Hours更新
    gh project item-edit --project-id "$PROJECT_ID" --id "$item_id" \
        --field-id "$ESTIMATE_FIELD" --number "$hours" 2>/dev/null || echo "    ⚠️ Estimate failed"

    echo "    ✅ Done"
done

echo ""
echo "=== 完了 ==="
echo ""
echo "📊 ガントチャート (Mermaid形式):"
echo ""
cat << 'MERMAID'
```mermaid
gantt
    title Enterprise RAG System - 開発スケジュール
    dateFormat YYYY-MM-DD

    section M1: コード品質基盤
    #9 脆弱性スキャン    :done, t9, 2026-01-27, 1d
    #14 設定管理整備     :done, t14, 2026-01-27, 1d
    #12 構造化ロギング   :active, t12, 2026-01-28, 1d
    #15 DI導入          :t15, 2026-01-29, 1d

    section M2: パフォーマンス
    #10 テスト整備      :t10, 2026-01-30, 1d
    #13 API非同期化     :crit, t13, 2026-01-30, 1d
    #7 Prometheus      :t7, 2026-01-31, 1d
```
MERMAID

echo ""
echo "🔗 プロジェクトURL: https://github.com/users/jinno-ai/projects/1/views/1"
