#!/usr/bin/env python3
"""
Task Decomposer - Story → Task 自動分解

対応インストラクション:
  - 05_task/ado_task_create.md

機能:
- User Story を 2-8時間の技術タスクに分解
- Task の見積もり時間自動算出
- 依存関係の自動検出
- Task テンプレート適用

使用例:
    python task_decomposer.py --config config.yaml
    python task_decomposer.py --config config.yaml --decomposition output/.../decomposition.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import yaml
import re

from key_management import KeyGenerator, KEY_CONFIG


@dataclass
class TaskTemplate:
    """Task テンプレート（05_task/ado_task_create.md 準拠）"""
    category: str  # implementation, test, review, documentation, investigation, config
    verb: str
    estimate_hours: float  # 2-8時間
    description_template: str


# Task カテゴリ別テンプレート
TASK_TEMPLATES: Dict[str, List[TaskTemplate]] = {
    "api": [
        TaskTemplate("implementation", "実装する", 4, "エンドポイントを実装する"),
        TaskTemplate("test", "テストを作成する", 2, "単体テストを作成する"),
        TaskTemplate("documentation", "文書化する", 1, "API仕様書を更新する"),
    ],
    "ui": [
        TaskTemplate("implementation", "作成する", 4, "コンポーネントを作成する"),
        TaskTemplate("test", "テストを作成する", 2, "コンポーネントテストを作成する"),
        TaskTemplate("review", "レビューする", 1, "UI/UXレビューを実施する"),
    ],
    "data": [
        TaskTemplate("implementation", "設計する", 3, "データモデルを設計する"),
        TaskTemplate("implementation", "実装する", 4, "マイグレーションを作成する"),
        TaskTemplate("test", "検証する", 2, "データ整合性を検証する"),
    ],
    "integration": [
        TaskTemplate("investigation", "調査する", 2, "外部API仕様を調査する"),
        TaskTemplate("implementation", "実装する", 4, "連携処理を実装する"),
        TaskTemplate("test", "テストを作成する", 3, "統合テストを作成する"),
    ],
    "config": [
        TaskTemplate("config", "設定する", 2, "環境設定を構成する"),
        TaskTemplate("documentation", "文書化する", 1, "設定手順を文書化する"),
    ],
    "default": [
        TaskTemplate("implementation", "実装する", 4, "機能を実装する"),
        TaskTemplate("test", "テストを作成する", 2, "テストを作成する"),
        TaskTemplate("review", "確認する", 1, "コードレビューを実施する"),
    ],
}


@dataclass
class Task:
    """Task データ（05_task/ado_task_create.md 準拠）"""
    key: str
    id: str  # T00001形式
    title: str
    description: str
    parent_story_key: str
    category: str  # implementation, test, review, documentation, investigation, config
    estimate_hours: float  # 2-8時間
    depends_on: List[str] = field(default_factory=list)
    checklist: List[str] = field(default_factory=list)
    assignee: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "parent_story_key": self.parent_story_key,
            "category": self.category,
            "estimate_hours": self.estimate_hours,
            "depends_on": self.depends_on,
            "checklist": self.checklist,
            "assignee": self.assignee,
        }


class TaskDecomposer:
    """Story → Task 分解器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        # プロジェクト情報
        github_config = config.get('project', {}).get('github', {})
        self.org = config.get('project', {}).get('org') or github_config.get('owner', 'unknown')
        self.repo = config.get('project', {}).get('repo') or github_config.get('repo', 'unknown')

        # キージェネレータ
        self.key_generator = KeyGenerator(self.org, self.repo)

        # Task番号カウンター（Story毎にリセット）
        self.task_counters: Dict[str, int] = {}

    def decompose(self, decomposition: Dict[str, Any]) -> Dict[str, Any]:
        """
        decomposition.json を読み込み、各Story に Task を追加

        Args:
            decomposition: Feature/Story 構造

        Returns:
            Task が追加された decomposition
        """
        result = decomposition.copy()

        for feature in result.get('features', []):
            for story in feature.get('stories', []):
                story_key = story.get('key', '')

                # Story の内容から Task カテゴリを推定
                category = self._detect_category(story)

                # Task を生成
                tasks = self._generate_tasks_for_story(story, category)

                story['tasks'] = [t.to_dict() for t in tasks]

                # Story の合計見積もりを更新
                total_task_hours = sum(t.estimate_hours for t in tasks)
                story['task_breakdown'] = {
                    "total_hours": total_task_hours,
                    "task_count": len(tasks),
                }

        # 統計を追加
        result['task_summary'] = self._calculate_summary(result)

        return result

    def _detect_category(self, story: Dict[str, Any]) -> str:
        """Story の内容から Task カテゴリを推定"""
        title = story.get('title', '').lower()
        description = story.get('description', '').lower()
        labels = [l.lower() for l in story.get('labels', [])]

        text = f"{title} {description} {' '.join(labels)}"

        # キーワードマッチング
        category_keywords = {
            "api": ["api", "endpoint", "rest", "graphql", "バックエンド", "backend"],
            "ui": ["ui", "画面", "フォーム", "コンポーネント", "表示", "ボタン", "frontend"],
            "data": ["データ", "db", "database", "モデル", "マスタ", "テーブル", "スキーマ"],
            "integration": ["連携", "integration", "外部", "third-party", "webhook"],
            "config": ["設定", "config", "環境", "デプロイ", "ci/cd", "インフラ"],
        }

        for category, keywords in category_keywords.items():
            if any(kw in text for kw in keywords):
                return category

        return "default"

    def _generate_tasks_for_story(self, story: Dict[str, Any], category: str) -> List[Task]:
        """Story から Task を生成"""
        story_key = story.get('key', '')
        story_title = story.get('title', '')
        estimate_hours = story.get('estimate_hours', 8)

        # カテゴリに応じたテンプレートを取得
        templates = TASK_TEMPLATES.get(category, TASK_TEMPLATES["default"])

        tasks = []
        task_number = 1

        for template in templates:
            # Task ID 生成
            task_id = KEY_CONFIG.format_id(KEY_CONFIG.TASK_PREFIX, task_number)

            # Task キー生成
            task_key = f"{story_key}/{task_id}"

            # タイトル生成
            task_title = f"{story_title}の{template.description_template}"

            # 見積もり時間調整（Storyの見積もりに比例）
            adjusted_hours = min(
                template.estimate_hours * (estimate_hours / 8),
                8  # 最大8時間
            )
            adjusted_hours = max(adjusted_hours, 2)  # 最小2時間

            task = Task(
                key=task_key,
                id=task_id,
                title=task_title,
                description=self._generate_task_description(story, template),
                parent_story_key=story_key,
                category=template.category,
                estimate_hours=round(adjusted_hours, 1),
                checklist=self._generate_checklist(template),
            )

            tasks.append(task)
            task_number += 1

        # 依存関係を設定（実装 → テスト → レビュー の順）
        self._set_dependencies(tasks)

        return tasks

    def _generate_task_description(self, story: Dict[str, Any], template: TaskTemplate) -> str:
        """Task の説明を生成（05_task/ado_task_create.md テンプレート準拠）"""
        story_title = story.get('title', '')
        story_key = story.get('key', '')

        return f"""## 概要

{story_title}に対する{template.description_template}

## 親 Story との関係

- 親 Story: {story_title}
- 統一キー: {story_key}

## 作業内容

### やること

- [ ] {template.description_template}
- [ ] 完了条件の確認

### やらないこと

- この Task のスコープ外の作業

## 完了条件

- [ ] {template.description_template}が完了している
- [ ] 品質基準を満たしている
"""

    def _generate_checklist(self, template: TaskTemplate) -> List[str]:
        """Task のチェックリストを生成"""
        base_checklist = [f"{template.description_template}が完了"]

        category_checklists = {
            "implementation": [
                "コードがコーディング規約に準拠",
                "エラーハンドリングが実装されている",
            ],
            "test": [
                "テストケースがすべてパス",
                "カバレッジ目標を達成",
            ],
            "review": [
                "レビューコメントがすべて解決",
                "承認を取得",
            ],
            "documentation": [
                "ドキュメントが最新化",
                "リンク切れがない",
            ],
            "investigation": [
                "調査結果が文書化",
                "結論と推奨事項が記載",
            ],
            "config": [
                "設定が環境に適用済み",
                "動作確認が完了",
            ],
        }

        return base_checklist + category_checklists.get(template.category, [])

    def _set_dependencies(self, tasks: List[Task]):
        """Task 間の依存関係を設定"""
        # カテゴリの実行順序
        order = ["investigation", "implementation", "test", "review", "documentation", "config"]

        # カテゴリ別にグループ化
        by_category = {}
        for task in tasks:
            cat = task.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(task)

        # 前のカテゴリの Task に依存
        prev_tasks = []
        for cat in order:
            if cat in by_category:
                for task in by_category[cat]:
                    if prev_tasks:
                        task.depends_on = [t.key for t in prev_tasks]
                prev_tasks = by_category[cat]

    def _calculate_summary(self, decomposition: Dict[str, Any]) -> Dict[str, Any]:
        """Task 統計を計算"""
        total_tasks = 0
        total_hours = 0
        by_category = {}

        for feature in decomposition.get('features', []):
            for story in feature.get('stories', []):
                for task in story.get('tasks', []):
                    total_tasks += 1
                    hours = task.get('estimate_hours', 0)
                    total_hours += hours

                    cat = task.get('category', 'unknown')
                    if cat not in by_category:
                        by_category[cat] = {"count": 0, "hours": 0}
                    by_category[cat]["count"] += 1
                    by_category[cat]["hours"] += hours

        return {
            "total_tasks": total_tasks,
            "total_hours": total_hours,
            "by_category": by_category,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Story → Task 自動分解（05_task/ado_task_create.md 準拠）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python task_decomposer.py --config config.yaml
  python task_decomposer.py --config config.yaml --decomposition output/.../decomposition.json
  python task_decomposer.py --config config.yaml --output output/.../decomposition_with_tasks.json
        """
    )

    parser.add_argument(
        '--config', '-c',
        required=True,
        help='設定ファイルパス (YAML)'
    )

    parser.add_argument(
        '--decomposition', '-d',
        help='入力 decomposition.json パス（指定しない場合は設定から推定）'
    )

    parser.add_argument(
        '--output', '-o',
        help='出力 JSON パス（指定しない場合は入力を上書き）'
    )

    args = parser.parse_args()

    # 設定読み込み
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] 設定ファイルが見つかりません: {config_path}")
        return 1

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # decomposition.json パスを決定
    if args.decomposition:
        decomp_path = Path(args.decomposition)
    else:
        # 設定から推定
        github_config = config.get('project', {}).get('github', {})
        org = config.get('project', {}).get('org') or github_config.get('owner', 'unknown')
        repo = config.get('project', {}).get('repo') or github_config.get('repo', 'unknown')
        epic_id = config.get('epic', {}).get('id') or KEY_CONFIG.format_id(KEY_CONFIG.EPIC_PREFIX, 1)

        base_output = Path(config.get('project', {}).get('output_dir', 'output'))
        decomp_path = base_output / org / repo / epic_id / "decomposition.json"

    if not decomp_path.exists():
        print(f"[ERROR] decomposition.json が見つかりません: {decomp_path}")
        print("先に `python epic_manager.py --mode decompose` を実行してください。")
        return 1

    # decomposition 読み込み
    with open(decomp_path, 'r', encoding='utf-8') as f:
        decomposition = json.load(f)

    print(f"[START] Story → Task 分解")
    print(f"  入力: {decomp_path}")

    # Task 分解実行
    decomposer = TaskDecomposer(config)
    result = decomposer.decompose(decomposition)

    # 出力パスを決定
    output_path = Path(args.output) if args.output else decomp_path

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 結果表示
    summary = result.get('task_summary', {})
    print(f"\n[DONE] Task 分解完了")
    print(f"  総Task数: {summary.get('total_tasks', 0)}")
    print(f"  総見積もり: {summary.get('total_hours', 0):.1f} 時間")
    print(f"  出力: {output_path}")

    print("\nカテゴリ別:")
    for cat, data in summary.get('by_category', {}).items():
        print(f"  - {cat}: {data['count']}件, {data['hours']:.1f}h")

    return 0


if __name__ == "__main__":
    sys.exit(main())
