#!/usr/bin/env python3
"""
Epic Decomposer - Epic → Feature → Story 自動分解

機能:
- Epicを3-5個のFeatureに分解
- 各Featureを3-5個のStoryに分解
- 依存関係の自動検出・設定
- 工数の自動見積もり

使用例:
    python epic_decomposer.py --config config.yaml --output features/
"""

import argparse
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class Story:
    """Storyデータ"""
    id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    estimate_hours: int
    priority: str  # high, medium, low
    depends_on: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)


@dataclass
class Feature:
    """Featureデータ"""
    id: str
    title: str
    description: str
    stories: List[Story]
    priority: str
    milestone_id: str = ""
    depends_on: List[str] = field(default_factory=list)


class EpicDecomposer:
    """Epic分解クラス"""

    # デフォルトのFeatureテンプレート
    DEFAULT_FEATURES = [
        {
            "type": "core",
            "title_template": "コア機能: {goal_keyword}",
            "priority": "high",
            "stories": [
                {"type": "setup", "title": "基盤セットアップ", "estimate": 4},
                {"type": "implementation", "title": "主要機能実装", "estimate": 8},
                {"type": "integration", "title": "統合テスト", "estimate": 4},
            ]
        },
        {
            "type": "infrastructure",
            "title_template": "インフラ・設定管理",
            "priority": "high",
            "stories": [
                {"type": "config", "title": "設定管理整備", "estimate": 4},
                {"type": "security", "title": "セキュリティ対応", "estimate": 4},
                {"type": "logging", "title": "ロギング・監視設定", "estimate": 4},
            ]
        },
        {
            "type": "quality",
            "title_template": "品質・テスト基盤",
            "priority": "medium",
            "stories": [
                {"type": "unit_test", "title": "ユニットテスト整備", "estimate": 8},
                {"type": "integration_test", "title": "結合テスト整備", "estimate": 8},
                {"type": "documentation", "title": "ドキュメント整備", "estimate": 4},
            ]
        },
        {
            "type": "optimization",
            "title_template": "パフォーマンス最適化",
            "priority": "medium",
            "stories": [
                {"type": "async", "title": "非同期化・並列化", "estimate": 8},
                {"type": "caching", "title": "キャッシュ導入", "estimate": 4},
                {"type": "monitoring", "title": "メトリクス収集", "estimate": 4},
            ]
        },
    ]

    def __init__(self, config: Dict[str, Any], use_llm: bool = True):
        self.config = config
        self.epic = config.get('epic', {})
        self.decomposition = config.get('decomposition', {})
        self.features: List[Feature] = []
        self.use_llm = use_llm
        self.generation_method = "template"  # or "llm"

    def decompose(self) -> Dict[str, Any]:
        """Epic分解のメイン処理"""
        goal = self.epic.get('goal', '')

        # LLMベースの分解を試行
        if self.use_llm:
            llm_result = self._try_llm_decompose()
            if llm_result:
                self.generation_method = llm_result.get("generation_method", "llm")
                self.features = self._convert_llm_result(llm_result)
                self._set_dependencies()
                result = self._build_result()
                result["generation_method"] = self.generation_method
                return result

        # フォールバック: テンプレートベース
        goal_keyword = self._extract_keyword(goal)
        self.features = self._generate_features(goal_keyword)
        self._set_dependencies()
        result = self._build_result()
        result["generation_method"] = "template"
        return result

    def _try_llm_decompose(self) -> Optional[Dict[str, Any]]:
        """LLMベースの分解を試行"""
        try:
            from llm_decomposer import LLMDecomposer, LLMConfig

            # LLM設定を取得
            llm_config_dict = self.config.get('llm', {})
            llm_config = LLMConfig(
                provider=llm_config_dict.get('provider', 'claude'),
                model=llm_config_dict.get('model', 'claude-sonnet-4-20250514'),
                temperature=llm_config_dict.get('temperature', 0.3)
            )

            decomposer = LLMDecomposer(llm_config)

            result = decomposer.decompose_epic(
                epic_goal=self.epic.get('goal', ''),
                epic_background=self.epic.get('background', ''),
                scope_in=self.epic.get('scope', {}).get('in_scope', []),
                scope_out=self.epic.get('scope', {}).get('out_of_scope', []),
                success_metrics=self.epic.get('success_metrics', []),
                project_context=self.config.get('project', {}).get('context', ''),
                max_features=self.decomposition.get('max_features', 5),
                max_stories_per_feature=self.decomposition.get('max_stories_per_feature', 5)
            )

            return result
        except Exception as e:
            print(f"[WARN] LLM decomposition failed: {e}")
            return None

    def _convert_llm_result(self, llm_result: Dict[str, Any]) -> List[Feature]:
        """LLM結果をFeatureリストに変換"""
        features = []

        for f_data in llm_result.get('features', []):
            stories = []
            for s_data in f_data.get('stories', []):
                story = Story(
                    id=s_data['id'],
                    title=s_data['title'],
                    description=s_data.get('description', ''),
                    acceptance_criteria=s_data.get('acceptance_criteria', []),
                    estimate_hours=s_data.get('estimate_hours', 4),
                    priority=s_data.get('priority', 'medium'),
                    depends_on=s_data.get('depends_on', []),
                    labels=[
                        f"estimate:{s_data.get('estimate_hours', 4)}h",
                        f"priority:{s_data.get('priority', 'medium')}",
                        f"feature:{f_data['id']}"
                    ]
                )
                stories.append(story)

            feature = Feature(
                id=f_data['id'],
                title=f_data['title'],
                description=f_data.get('description', ''),
                stories=stories,
                priority=f_data.get('priority', 'medium'),
                milestone_id=f_data.get('milestone', f"M{len(features) + 1}")
            )
            features.append(feature)

        return features

    def _extract_keyword(self, goal: str) -> str:
        """ゴールからキーワードを抽出"""
        # 簡易的なキーワード抽出（最初の名詞句を取得）
        words = goal.replace('\n', ' ').split()
        return words[0] if words else "機能"

    def _generate_features(self, goal_keyword: str) -> List[Feature]:
        """Featureを生成"""
        features = []

        for idx, template in enumerate(self.DEFAULT_FEATURES):
            feature_id = f"F{idx + 1}"

            # Storyを生成
            stories = []
            for s_idx, story_template in enumerate(template['stories']):
                story_id = f"{feature_id}-S{s_idx + 1}"
                story = Story(
                    id=story_id,
                    title=story_template['title'],
                    description=f"{story_template['title']}を実施",
                    acceptance_criteria=[
                        f"{story_template['title']}が完了している",
                        "テストが通過している",
                        "レビューが完了している"
                    ],
                    estimate_hours=story_template['estimate'],
                    priority=template['priority'],
                    labels=[
                        f"estimate:{story_template['estimate']}h",
                        f"priority:{template['priority']}",
                        f"feature:{feature_id}"
                    ]
                )
                stories.append(story)

            # Featureを作成
            title = template['title_template'].format(goal_keyword=goal_keyword)
            feature = Feature(
                id=feature_id,
                title=title,
                description=f"{title}に関連する機能群",
                stories=stories,
                priority=template['priority'],
                milestone_id=f"M{idx + 1}"
            )
            features.append(feature)

        return features

    def _set_dependencies(self):
        """依存関係を設定"""
        # 基本ルール: インフラ → コア → 品質 → 最適化
        dependency_map = {
            "F1": [],           # コア: 依存なし（最初に着手可能な部分）
            "F2": [],           # インフラ: 依存なし（並列実行可能）
            "F3": ["F1", "F2"], # 品質: コアとインフラが前提
            "F4": ["F1", "F3"], # 最適化: コアと品質が前提
        }

        for feature in self.features:
            feature.depends_on = dependency_map.get(feature.id, [])

            # Story間の依存関係を設定
            for i, story in enumerate(feature.stories):
                if i > 0:
                    story.depends_on = [feature.stories[i-1].id]

    def _build_result(self) -> Dict[str, Any]:
        """結果を構造化"""
        features_data = []
        all_stories = []

        for feature in self.features:
            stories_data = []
            for story in feature.stories:
                story_data = {
                    "id": story.id,
                    "title": story.title,
                    "description": story.description,
                    "acceptance_criteria": story.acceptance_criteria,
                    "estimate_hours": story.estimate_hours,
                    "priority": story.priority,
                    "depends_on": story.depends_on,
                    "labels": story.labels,
                }
                stories_data.append(story_data)
                all_stories.append(story_data)

            feature_data = {
                "id": feature.id,
                "title": feature.title,
                "description": feature.description,
                "priority": feature.priority,
                "milestone_id": feature.milestone_id,
                "depends_on": feature.depends_on,
                "stories": stories_data,
                "total_hours": sum(s.estimate_hours for s in feature.stories),
            }
            features_data.append(feature_data)

        total_hours = sum(f['total_hours'] for f in features_data)

        return {
            "features": features_data,
            "all_stories": all_stories,
            "summary": {
                "feature_count": len(features_data),
                "story_count": len(all_stories),
                "total_hours": total_hours,
                "estimated_days": (total_hours + 7) // 8,
            }
        }

    def generate_markdown(self) -> str:
        """Markdown形式の分解結果を生成"""
        result = self.decompose()

        lines = [
            "# Epic分解結果",
            "",
            f"生成日時: {datetime.now().isoformat()}",
            "",
            "## サマリー",
            "",
            f"- Feature数: {result['summary']['feature_count']}",
            f"- Story数: {result['summary']['story_count']}",
            f"- 総工数: {result['summary']['total_hours']}h ({result['summary']['estimated_days']}日)",
            "",
            "## 階層構造",
            "",
        ]

        for feature in result['features']:
            deps = f" (依存: {', '.join(feature['depends_on'])})" if feature['depends_on'] else ""
            lines.append(f"### {feature['id']}: {feature['title']}{deps}")
            lines.append(f"")
            lines.append(f"**優先度**: {feature['priority']} | **工数**: {feature['total_hours']}h")
            lines.append("")

            for story in feature['stories']:
                s_deps = f" → {', '.join(story['depends_on'])}" if story['depends_on'] else ""
                lines.append(f"- [ ] **{story['id']}**: {story['title']} ({story['estimate_hours']}h){s_deps}")

            lines.append("")

        # ガントチャート
        lines.extend([
            "## ガントチャート（Mermaid）",
            "",
            "```mermaid",
            "gantt",
            "    title Epic 実行計画",
            "    dateFormat YYYY-MM-DD",
            "",
        ])

        for feature in result['features']:
            lines.append(f"    section {feature['title'][:20]}")
            for story in feature['stories']:
                duration = max(1, story['estimate_hours'] // 8)
                lines.append(f"    {story['title'][:25]} :{story['id'].lower().replace('-', '_')}, {duration}d")

        lines.append("```")

        return "\n".join(lines)

    def generate_github_issues(self) -> List[Dict[str, Any]]:
        """GitHub Issue形式のデータを生成"""
        result = self.decompose()
        issues = []

        for feature in result['features']:
            # Feature Issue
            feature_body = f"""## 概要

{feature['description']}

## ストーリー

"""
            for story in feature['stories']:
                feature_body += f"- [ ] #{story['id']}: {story['title']}\n"

            if feature['depends_on']:
                feature_body += f"\n## 依存関係\n\n"
                for dep in feature['depends_on']:
                    feature_body += f"- **Depends on**: #{dep}\n"

            issues.append({
                "type": "feature",
                "id": feature['id'],
                "title": f"[Feature] {feature['title']}",
                "body": feature_body,
                "labels": [f"priority:{feature['priority']}", "feature"],
                "milestone": feature['milestone_id'],
            })

            # Story Issues
            for story in feature['stories']:
                story_body = f"""## 概要

{story['description']}

## 受け入れ条件

"""
                for ac in story['acceptance_criteria']:
                    story_body += f"- [ ] {ac}\n"

                if story['depends_on']:
                    story_body += f"\n## 依存関係\n\n"
                    for dep in story['depends_on']:
                        story_body += f"- **Depends on**: #{dep}\n"

                issues.append({
                    "type": "story",
                    "id": story['id'],
                    "title": f"[Story] {story['title']}",
                    "body": story_body,
                    "labels": story['labels'],
                    "parent_feature": feature['id'],
                })

        return issues


def main():
    parser = argparse.ArgumentParser(description="Epic分解ツール")
    parser.add_argument('--config', '-c', required=True, help='設定ファイルパス')
    parser.add_argument('--output', '-o', default='.concept/decomposition', help='出力ディレクトリ')
    parser.add_argument('--format', '-f', choices=['markdown', 'json', 'github'], default='markdown')
    parser.add_argument('--dry-run', '-n', action='store_true', help='プレビューのみ')

    args = parser.parse_args()

    # 設定読み込み
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    decomposer = EpicDecomposer(config)

    if args.format == 'markdown':
        output = decomposer.generate_markdown()
        if args.dry_run:
            print(output)
        else:
            output_path = Path(args.output)
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "decomposition.md").write_text(output, encoding='utf-8')
            print(f"✅ 出力: {output_path / 'decomposition.md'}")

    elif args.format == 'json':
        result = decomposer.decompose()
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.dry_run:
            print(output)
        else:
            output_path = Path(args.output)
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "decomposition.json").write_text(output, encoding='utf-8')
            print(f"✅ 出力: {output_path / 'decomposition.json'}")

    elif args.format == 'github':
        issues = decomposer.generate_github_issues()
        output = json.dumps(issues, ensure_ascii=False, indent=2)
        if args.dry_run:
            print(output)
        else:
            output_path = Path(args.output)
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "github_issues.json").write_text(output, encoding='utf-8')
            print(f"✅ 出力: {output_path / 'github_issues.json'}")


if __name__ == "__main__":
    main()
