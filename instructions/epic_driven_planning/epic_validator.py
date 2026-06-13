#!/usr/bin/env python3
"""
Epic Validator - Epic/Feature/Story 品質チェック＆自動改善

機能:
- Epic品質ゲートのチェック
- Feature/Story の品質検証
- 自動修正提案・適用
- レポート生成

使用例:
    python epic_validator.py --config config.yaml --fix
"""

import argparse
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
import re


@dataclass
class ValidationResult:
    """検証結果"""
    rule_id: str
    rule_name: str
    passed: bool
    message: str
    severity: str  # error, warning, info
    fix_suggestion: Optional[str] = None
    auto_fixable: bool = False


@dataclass
class ValidationReport:
    """検証レポート"""
    target: str
    results: List[ValidationResult]

    @property
    def passed(self) -> bool:
        return all(r.passed or r.severity != 'error' for r in self.results)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == 'error')

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == 'warning')


class EpicValidator:
    """Epic品質検証クラス"""

    # 検証ルール定義
    EPIC_RULES = [
        {
            "id": "E001",
            "name": "title_has_business_value",
            "description": "タイトルがビジネス価値を表現しているか",
            "severity": "error",
            "check": "_check_title_business_value",
        },
        {
            "id": "E002",
            "name": "acceptance_criteria_count",
            "description": "受け入れ条件が3-7個あるか",
            "severity": "error",
            "check": "_check_acceptance_criteria_count",
        },
        {
            "id": "E003",
            "name": "in_out_scope_defined",
            "description": "In/Out Scopeが定義されているか",
            "severity": "error",
            "check": "_check_scope_defined",
        },
        {
            "id": "E004",
            "name": "owner_assigned",
            "description": "Epic OwnerとTechnical Leadが割り当てられているか",
            "severity": "error",
            "check": "_check_owner_assigned",
        },
        {
            "id": "E005",
            "name": "metrics_measurable",
            "description": "成功指標が測定可能か",
            "severity": "warning",
            "check": "_check_metrics_measurable",
        },
        {
            "id": "E006",
            "name": "goal_not_too_long",
            "description": "ゴールが簡潔か（200文字以内）",
            "severity": "warning",
            "check": "_check_goal_length",
        },
        {
            "id": "E007",
            "name": "has_background",
            "description": "背景が記述されているか",
            "severity": "warning",
            "check": "_check_has_background",
        },
    ]

    FEATURE_RULES = [
        {
            "id": "F001",
            "name": "independently_releasable",
            "description": "独立してリリース可能か",
            "severity": "warning",
            "check": "_check_feature_releasable",
        },
        {
            "id": "F002",
            "name": "has_stories",
            "description": "Storyが存在するか",
            "severity": "error",
            "check": "_check_feature_has_stories",
        },
    ]

    STORY_RULES = [
        {
            "id": "S001",
            "name": "fits_in_sprint",
            "description": "1スプリント（40h）以内か",
            "severity": "error",
            "check": "_check_story_fits_sprint",
        },
        {
            "id": "S002",
            "name": "has_acceptance_criteria",
            "description": "受け入れ条件があるか",
            "severity": "error",
            "check": "_check_story_has_ac",
        },
        {
            "id": "S003",
            "name": "estimate_assigned",
            "description": "工数見積もりがあるか",
            "severity": "error",
            "check": "_check_story_has_estimate",
        },
    ]

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.epic = config.get('epic', {})
        self.stakeholders = config.get('stakeholders', {})
        self.decomposition_data: Optional[Dict[str, Any]] = None

    def validate(self) -> Dict[str, Any]:
        """全体検証のメイン処理"""
        reports = []

        # Epic検証
        epic_report = self._validate_epic()
        reports.append(epic_report)

        # Feature/Story検証（分解データがある場合）
        if self.decomposition_data:
            for feature in self.decomposition_data.get('features', []):
                feature_report = self._validate_feature(feature)
                reports.append(feature_report)

                for story in feature.get('stories', []):
                    story_report = self._validate_story(story)
                    reports.append(story_report)

        # 結果を集計
        total_errors = sum(r.error_count for r in reports)
        total_warnings = sum(r.warning_count for r in reports)
        passed = all(r.passed for r in reports)

        return {
            "passed": passed,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "reports": [self._report_to_dict(r) for r in reports],
            "errors": [
                r.message for report in reports
                for r in report.results
                if not r.passed and r.severity == 'error'
            ],
            "warnings": [
                r.message for report in reports
                for r in report.results
                if not r.passed and r.severity == 'warning'
            ],
        }

    def _validate_epic(self) -> ValidationReport:
        """Epic検証"""
        results = []

        for rule in self.EPIC_RULES:
            check_method = getattr(self, rule['check'], None)
            if check_method:
                result = check_method(rule)
                results.append(result)

        return ValidationReport(target="Epic", results=results)

    def _validate_feature(self, feature: Dict[str, Any]) -> ValidationReport:
        """Feature検証"""
        results = []

        for rule in self.FEATURE_RULES:
            check_method = getattr(self, rule['check'], None)
            if check_method:
                result = check_method(rule, feature)
                results.append(result)

        return ValidationReport(target=f"Feature:{feature.get('id', 'N/A')}", results=results)

    def _validate_story(self, story: Dict[str, Any]) -> ValidationReport:
        """Story検証"""
        results = []

        for rule in self.STORY_RULES:
            check_method = getattr(self, rule['check'], None)
            if check_method:
                result = check_method(rule, story)
                results.append(result)

        return ValidationReport(target=f"Story:{story.get('id', 'N/A')}", results=results)

    # ===== Epic検証メソッド =====

    def _check_title_business_value(self, rule: Dict) -> ValidationResult:
        """タイトルがビジネス価値を表現しているか"""
        goal = self.epic.get('goal', '')

        # 技術的すぎる表現を検出
        tech_keywords = ['実装', 'API', 'DB', 'サーバー', 'クラス', 'メソッド']
        has_tech_only = any(kw in goal for kw in tech_keywords)

        # 価値表現を検出
        value_keywords = ['提供', '削減', '向上', '改善', '実現', 'できる', '可能']
        has_value = any(kw in goal for kw in value_keywords)

        passed = has_value and len(goal) > 10

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message="ゴールにビジネス価値が含まれています" if passed else "ゴールにビジネス価値の表現が不足しています",
            severity=rule['severity'],
            fix_suggestion="「誰に」「何を」「なぜ」の観点で書き直してください" if not passed else None,
            auto_fixable=False
        )

    def _check_acceptance_criteria_count(self, rule: Dict) -> ValidationResult:
        """受け入れ条件が適切な範囲内か"""
        metrics = self.epic.get('success_metrics', [])
        scope_in = self.epic.get('scope', {}).get('in_scope', [])

        # 仮の条件数を計算
        ac_count = len(metrics) + min(len(scope_in), 3)

        # 設定から上限を取得（デフォルト: 3-7）
        validation_config = self.config.get('validation', {})
        min_criteria = validation_config.get('min_acceptance_criteria', 3)
        max_criteria = validation_config.get('max_acceptance_criteria', 7)

        passed = min_criteria <= ac_count <= max_criteria

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message=f"受け入れ条件数: {ac_count}（推定）" if passed else f"受け入れ条件が{ac_count}個です（{min_criteria}-{max_criteria}個が推奨）",
            severity=rule['severity'],
            fix_suggestion="成功指標を追加するか、スコープを調整してください" if not passed else None,
            auto_fixable=False
        )

    def _check_scope_defined(self, rule: Dict) -> ValidationResult:
        """In/Out Scopeが定義されているか"""
        scope = self.epic.get('scope', {})
        in_scope = scope.get('in_scope', [])
        out_scope = scope.get('out_of_scope', [])

        passed = len(in_scope) > 0 and len(out_scope) > 0

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message="In/Out Scopeが定義されています" if passed else "In ScopeまたはOut of Scopeが未定義です",
            severity=rule['severity'],
            fix_suggestion="設定ファイルのscope.in_scopeとscope.out_of_scopeを定義してください" if not passed else None,
            auto_fixable=False
        )

    def _check_owner_assigned(self, rule: Dict) -> ValidationResult:
        """オーナーが割り当てられているか"""
        # 設定でスキップ可能
        validation_config = self.config.get('validation', {})
        if validation_config.get('skip_owner_check', False):
            return ValidationResult(
                rule_id=rule['id'],
                rule_name=rule['name'],
                passed=True,
                message="オーナーチェックはスキップされました（skip_owner_check=true）",
                severity=rule['severity'],
            )

        epic_owner = self.stakeholders.get('epic_owner', '')
        tech_lead = self.stakeholders.get('technical_lead', '') or self.stakeholders.get('tech_lead', '')

        passed = bool(epic_owner) and bool(tech_lead) and epic_owner != '未割り当て' and tech_lead != '未割り当て'

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message="責任者が割り当てられています" if passed else "Epic OwnerまたはTechnical Leadが未割り当てです",
            severity=rule['severity'],
            fix_suggestion="設定ファイルのstakeholders.epic_ownerとstakeholders.tech_leadを設定してください" if not passed else None,
            auto_fixable=False
        )

    def _check_metrics_measurable(self, rule: Dict) -> ValidationResult:
        """成功指標が測定可能か"""
        metrics = self.epic.get('success_metrics', [])

        if not metrics:
            return ValidationResult(
                rule_id=rule['id'],
                rule_name=rule['name'],
                passed=False,
                message="成功指標が未定義です",
                severity=rule['severity'],
                fix_suggestion="epic.success_metricsに数値目標を含む指標を追加してください",
                auto_fixable=False
            )

        # 数値を含む指標をチェック
        measurable_count = 0
        for metric in metrics:
            target = str(metric.get('target', ''))
            if re.search(r'\d+', target):
                measurable_count += 1

        passed = measurable_count >= len(metrics) * 0.5

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message=f"測定可能な指標: {measurable_count}/{len(metrics)}" if passed else "測定可能な指標（数値を含む）が少ないです",
            severity=rule['severity'],
            fix_suggestion="各指標に具体的な数値目標を設定してください" if not passed else None,
            auto_fixable=False
        )

    def _check_goal_length(self, rule: Dict) -> ValidationResult:
        """ゴールが簡潔か"""
        goal = self.epic.get('goal', '')
        length = len(goal.replace('\n', ''))
        passed = length <= 200

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message=f"ゴール文字数: {length}" if passed else f"ゴールが長すぎます（{length}文字、200文字以内推奨）",
            severity=rule['severity'],
            fix_suggestion="ゴールを1-2文に要約してください" if not passed else None,
            auto_fixable=False
        )

    def _check_has_background(self, rule: Dict) -> ValidationResult:
        """背景が記述されているか"""
        background = self.epic.get('background', '')
        passed = len(background.strip()) >= 20

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message="背景が記述されています" if passed else "背景の記述が不足しています",
            severity=rule['severity'],
            fix_suggestion="なぜこのEpicが必要かを2-3文で記述してください" if not passed else None,
            auto_fixable=False
        )

    # ===== Feature検証メソッド =====

    def _check_feature_releasable(self, rule: Dict, feature: Dict) -> ValidationResult:
        """独立してリリース可能か"""
        deps = feature.get('depends_on', [])
        passed = len(deps) <= 2  # 依存が少なければリリースしやすい

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message=f"依存Feature数: {len(deps)}" if passed else f"依存が多すぎます（{len(deps)}個）",
            severity=rule['severity'],
            fix_suggestion="Featureを分割して依存を減らすことを検討してください" if not passed else None,
            auto_fixable=False
        )

    def _check_feature_has_stories(self, rule: Dict, feature: Dict) -> ValidationResult:
        """Storyが存在するか"""
        stories = feature.get('stories', [])
        passed = len(stories) >= 1

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message=f"Story数: {len(stories)}" if passed else "Storyが存在しません",
            severity=rule['severity'],
            fix_suggestion="Featureを具体的なStoryに分解してください" if not passed else None,
            auto_fixable=False
        )

    # ===== Story検証メソッド =====

    def _check_story_fits_sprint(self, rule: Dict, story: Dict) -> ValidationResult:
        """1スプリント以内か"""
        estimate = story.get('estimate_hours', 0)
        passed = estimate <= 40

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message=f"工数: {estimate}h" if passed else f"工数が大きすぎます（{estimate}h、40h以内推奨）",
            severity=rule['severity'],
            fix_suggestion="Storyをより小さな単位に分割してください" if not passed else None,
            auto_fixable=False
        )

    def _check_story_has_ac(self, rule: Dict, story: Dict) -> ValidationResult:
        """受け入れ条件があるか"""
        ac = story.get('acceptance_criteria', [])
        passed = len(ac) >= 1

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message=f"受け入れ条件数: {len(ac)}" if passed else "受け入れ条件がありません",
            severity=rule['severity'],
            fix_suggestion="完了を判定できる具体的な条件を追加してください" if not passed else None,
            auto_fixable=False
        )

    def _check_story_has_estimate(self, rule: Dict, story: Dict) -> ValidationResult:
        """工数見積もりがあるか"""
        estimate = story.get('estimate_hours', 0)
        passed = estimate > 0

        return ValidationResult(
            rule_id=rule['id'],
            rule_name=rule['name'],
            passed=passed,
            message=f"工数: {estimate}h" if passed else "工数見積もりがありません",
            severity=rule['severity'],
            fix_suggestion="estimate_hoursを設定してください（1-40h）" if not passed else None,
            auto_fixable=True
        )

    def auto_fix(self) -> Dict[str, Any]:
        """自動修正を適用"""
        # 現時点では自動修正の対象は限定的
        # 将来的に拡張可能
        return {
            "success": True,
            "fixes_applied": 0,
            "message": "自動修正対象はありませんでした"
        }

    def _report_to_dict(self, report: ValidationReport) -> Dict[str, Any]:
        """レポートを辞書に変換"""
        return {
            "target": report.target,
            "passed": report.passed,
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "results": [
                {
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "passed": r.passed,
                    "message": r.message,
                    "severity": r.severity,
                    "fix_suggestion": r.fix_suggestion,
                }
                for r in report.results
            ]
        }

    def generate_report_markdown(self) -> str:
        """Markdownレポートを生成"""
        result = self.validate()

        status_emoji = "✅" if result['passed'] else "❌"

        lines = [
            f"# 品質検証レポート {status_emoji}",
            "",
            f"生成日時: {datetime.now().isoformat()}",
            "",
            "## サマリー",
            "",
            f"- **ステータス**: {'合格' if result['passed'] else '不合格'}",
            f"- **エラー数**: {result['total_errors']}",
            f"- **警告数**: {result['total_warnings']}",
            "",
        ]

        if result['errors']:
            lines.extend([
                "## エラー（修正必須）",
                "",
            ])
            for error in result['errors']:
                lines.append(f"- ❌ {error}")
            lines.append("")

        if result['warnings']:
            lines.extend([
                "## 警告（推奨修正）",
                "",
            ])
            for warning in result['warnings']:
                lines.append(f"- ⚠️ {warning}")
            lines.append("")

        lines.extend([
            "## 詳細結果",
            "",
        ])

        for report in result['reports']:
            status = "✅" if report['passed'] else "❌"
            lines.append(f"### {report['target']} {status}")
            lines.append("")

            for r in report['results']:
                icon = "✅" if r['passed'] else ("❌" if r['severity'] == 'error' else "⚠️")
                lines.append(f"- {icon} **{r['rule_id']}** {r['rule_name']}: {r['message']}")
                if r['fix_suggestion']:
                    lines.append(f"  - 💡 {r['fix_suggestion']}")

            lines.append("")

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Epic品質検証ツール")
    parser.add_argument('--config', '-c', required=True, help='設定ファイルパス')
    parser.add_argument('--decomposition', '-d', help='分解データJSONパス')
    parser.add_argument('--output', '-o', help='レポート出力パス')
    parser.add_argument('--fix', action='store_true', help='自動修正を適用')
    parser.add_argument('--format', '-f', choices=['markdown', 'json'], default='markdown')

    args = parser.parse_args()

    # 設定読み込み
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    validator = EpicValidator(config)

    # 分解データ読み込み
    if args.decomposition:
        with open(args.decomposition, 'r', encoding='utf-8') as f:
            validator.decomposition_data = json.load(f)

    # 検証実行
    result = validator.validate()

    # 自動修正
    if args.fix:
        fix_result = validator.auto_fix()
        print(f"自動修正: {fix_result['message']}")

    # 出力
    if args.format == 'markdown':
        output = validator.generate_report_markdown()
    else:
        output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"✅ レポート出力: {args.output}")
    else:
        print(output)

    # 終了コード
    return 0 if result['passed'] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
