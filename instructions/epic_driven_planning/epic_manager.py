#!/usr/bin/env python3
"""
Epic Manager - Epic-Driven Planning 統合管理スクリプト

対応インストラクション（01-planning-requirements）:
  - 02_epic/ado_epic_create.md    → epic ステージ
  - 03_feature/ado_feature_create.md → feature ステージ
  - 04_story/ado_story_create.md  → story ステージ
  - 05_task/ado_task_create.md    → task ステージ

機能:
- Epic → Feature → Story → Task の段階的分解
- 各レベルでの品質チェック
- 依存関係解析・自動スケジューリング
- GitHub/ADO/GitLab への同期
- 統一キー管理による100+プロジェクト対応

使用例:
    # 全自動パイプライン（01-planning-requirements 完全実行）
    python epic_manager.py --config config.yaml --mode full-pipeline

    # 個別ステップ（01-planning-requirements 準拠）
    python epic_manager.py --config config.yaml --mode epic      # 02_epic
    python epic_manager.py --config config.yaml --mode feature   # 03_feature
    python epic_manager.py --config config.yaml --mode story     # 04_story
    python epic_manager.py --config config.yaml --mode task      # 05_task
    python epic_manager.py --config config.yaml --mode validate  # 品質チェック
    python epic_manager.py --config config.yaml --mode schedule  # スケジュール
    python epic_manager.py --config config.yaml --mode sync      # プロバイダー同期
"""

import argparse
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import subprocess
import json

# サブモジュールのインポート
from epic_generator import EpicGenerator
from epic_decomposer import EpicDecomposer
from epic_validator import EpicValidator
from schedule_optimizer import ScheduleOptimizer
from task_decomposer import TaskDecomposer
from providers import get_provider, WorkItem, ItemType
from key_management import (
    UnifiedKey, KeyedItem, KeyRegistry, KeyGenerator,
    migrate_legacy_decomposition
)


@dataclass
class PipelineResult:
    """パイプライン実行結果"""
    success: bool
    stage: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class EpicManager:
    """Epic-Driven Planning 統合マネージャー"""

    def __init__(self, config_path: str, dry_run: bool = False, verbose: bool = False):
        self.config_path = Path(config_path)
        self.dry_run = dry_run
        self.verbose = verbose
        self.config = self._load_config()

        # プロジェクト情報（統一キー用）
        github_config = self.config.get('project', {}).get('github', {})
        self.org = github_config.get('owner', 'unknown')
        self.repo = github_config.get('repo', 'unknown')

        # epic_id: 設定から取得、なければKEY_CONFIG準拠で生成
        from key_management import KEY_CONFIG
        epic_id_config = self.config.get('epic', {}).get('id')
        if epic_id_config:
            self.epic_id = epic_id_config
        else:
            self.epic_id = KEY_CONFIG.format_id(KEY_CONFIG.EPIC_PREFIX, 1)

        # 出力ディレクトリ（統一キー形式）
        base_output = Path(self.config.get('project', {}).get('output_dir', 'output'))
        self.output_dir = base_output / self.org / self.repo / self.epic_id
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # キーレジストリ
        registry_dir = base_output / "_registry"
        self.registry = KeyRegistry(registry_dir)
        self.key_generator = KeyGenerator(self.org, self.repo)

        # サブモジュール初期化
        self.generator = EpicGenerator(self.config)
        self.decomposer = EpicDecomposer(self.config)
        self.validator = EpicValidator(self.config)
        self.scheduler = ScheduleOptimizer(self.config)
        self.task_decomposer = TaskDecomposer(self.config)

        # 汎用プロバイダー（GitHub/GitLab/ADO）
        provider_name = self.config.get('project', {}).get('provider', 'github')
        self.provider = get_provider(provider_name, self.config, dry_run=dry_run)

    def _load_config(self) -> Dict[str, Any]:
        """設定ファイル読み込み"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # デフォルト値の設定
        config.setdefault('schedule', {})
        config['schedule'].setdefault('hours_per_day', 8)
        config['schedule'].setdefault('working_days', [0, 1, 2, 3, 4])

        return config

    def run_full_pipeline(self) -> PipelineResult:
        """
        全自動パイプライン実行（01-planning-requirements 完全準拠）

        ステージ:
          1. epic     - Epic生成（02_epic/ado_epic_create.md）
          2. feature  - Feature分解（03_feature/ado_feature_create.md）
          3. story    - Story分解（04_story/ado_story_create.md）
          4. task     - Task分解（05_task/ado_task_create.md）
          5. validate - 品質チェック
          6. schedule - スケジュール最適化
          7. sync     - プロバイダー同期
        """
        print("[START] Epic-Driven Planning Pipeline (01-planning-requirements)")
        print("=" * 60)

        stages = [
            ("epic", self._stage_epic, "02_epic/ado_epic_create.md"),
            ("feature", self._stage_feature, "03_feature/ado_feature_create.md"),
            ("story", self._stage_story, "04_story/ado_story_create.md"),
            ("task", self._stage_task, "05_task/ado_task_create.md"),
            ("validate", self._stage_validate, "品質チェック"),
            ("schedule", self._stage_schedule, "スケジュール最適化"),
            ("sync", self._stage_sync, "プロバイダー同期"),
        ]

        results = {}
        for stage_name, stage_func, instruction in stages:
            print(f"\n[STAGE] {stage_name} ({instruction})")
            print("-" * 40)

            result = stage_func()
            results[stage_name] = result

            if not result.success:
                print(f"[FAIL] Stage {stage_name}: {result.message}")
                return PipelineResult(
                    success=False,
                    stage=stage_name,
                    message=f"パイプライン停止: {stage_name}で失敗",
                    data=results,
                    errors=result.errors
                )

            print(f"[OK] Stage {stage_name} completed")

        print("\n" + "=" * 60)
        print("[DONE] Pipeline completed successfully")

        return PipelineResult(
            success=True,
            stage="complete",
            message="全ステージ正常完了（01-planning-requirements 完全実行）",
            data=results
        )

    def _stage_epic(self) -> PipelineResult:
        """
        Stage 1: Epic生成（02_epic/ado_epic_create.md 準拠）

        - ビジネスゴールの定義
        - 測定可能な完了条件
        - スコープの境界定義
        - ステークホルダーの明示
        """
        try:
            epic_data = self.generator.generate()

            # Epic をレジストリに登録
            epic_key = self.key_generator.epic(self.epic_id)
            self.registry.register(KeyedItem(
                key=epic_key,
                item_type='epic',
                title=self.config.get('epic', {}).get('goal', 'Epic'),
                data=epic_data
            ))

            return PipelineResult(
                success=True,
                stage="epic",
                message="Epic生成完了（02_epic/ado_epic_create.md）",
                data={"epic": epic_data}
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                stage="epic",
                message=str(e),
                errors=[str(e)]
            )

    def _stage_feature(self) -> PipelineResult:
        """
        Stage 2: Feature分解（03_feature/ado_feature_create.md 準拠）

        - Epic を 1-2スプリントで完了する機能単位に分解
        - 3-7個の Story に分解できるサイズ
        - 親 Epic への明確な紐付け
        """
        try:
            # Epic → Feature のみ分解
            decomposed = self.decomposer.decompose()

            # レガシー形式を統一キー形式に変換
            unified = migrate_legacy_decomposition(
                decomposed, self.org, self.repo, self.epic_id
            )

            # Feature のみ保存（Story は次のステージ）
            for feature in unified.get('features', []):
                feature_key = UnifiedKey.from_string(feature['key'])
                self.registry.register(KeyedItem(
                    key=feature_key,
                    item_type='feature',
                    title=feature['title'],
                    data=feature
                ))

            # 中間ファイルとして保存
            output_path = self.output_dir / "features.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(unified, f, ensure_ascii=False, indent=2)

            return PipelineResult(
                success=True,
                stage="feature",
                message=f"Feature分解完了: {len(unified.get('features', []))}件（03_feature/ado_feature_create.md）",
                data=unified
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                stage="feature",
                message=str(e),
                errors=[str(e)]
            )

    def _stage_story(self) -> PipelineResult:
        """
        Stage 3: Story分解（04_story/ado_story_create.md 準拠）

        - Feature を 1スプリント内で完了する最小単位に分解
        - INVEST原則の適用
        - Acceptance Criteria（Given-When-Then）
        - Story Points 見積もり
        """
        try:
            # features.json を読み込み
            features_path = self.output_dir / "features.json"
            if not features_path.exists():
                return PipelineResult(
                    success=False,
                    stage="story",
                    message="features.json が見つかりません。先に feature ステージを実行してください。",
                    errors=["features.json not found"]
                )

            with open(features_path, 'r', encoding='utf-8') as f:
                unified = json.load(f)

            # Story をレジストリに登録
            story_count = 0
            for feature in unified.get('features', []):
                for story in feature.get('stories', []):
                    story_key = UnifiedKey.from_string(story['key'])
                    self.registry.register(KeyedItem(
                        key=story_key,
                        item_type='story',
                        title=story['title'],
                        data=story
                    ))
                    story_count += 1

            # decomposition.json として保存（Task追加前）
            output_path = self.output_dir / "decomposition.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(unified, f, ensure_ascii=False, indent=2)

            return PipelineResult(
                success=True,
                stage="story",
                message=f"Story分解完了: {story_count}件（04_story/ado_story_create.md）",
                data=unified
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                stage="story",
                message=str(e),
                errors=[str(e)]
            )

    def _stage_task(self) -> PipelineResult:
        """
        Stage 4: Task分解（05_task/ado_task_create.md 準拠）

        - Story を 2-8時間の技術タスクに分解
        - カテゴリ別（implementation, test, review, documentation）
        - 依存関係の自動検出
        - 時間見積もり
        """
        try:
            # decomposition.json を読み込み
            decomp_path = self.output_dir / "decomposition.json"
            if not decomp_path.exists():
                return PipelineResult(
                    success=False,
                    stage="task",
                    message="decomposition.json が見つかりません。先に story ステージを実行してください。",
                    errors=["decomposition.json not found"]
                )

            with open(decomp_path, 'r', encoding='utf-8') as f:
                decomposition = json.load(f)

            # Task 分解実行
            result = self.task_decomposer.decompose(decomposition)

            # Task をレジストリに登録
            task_count = 0
            for feature in result.get('features', []):
                for story in feature.get('stories', []):
                    for task in story.get('tasks', []):
                        task_key = UnifiedKey.from_string(task['key'])
                        self.registry.register(KeyedItem(
                            key=task_key,
                            item_type='task',
                            title=task['title'],
                            data=task
                        ))
                        task_count += 1

            # decomposition.json を更新（Task 含む）
            with open(decomp_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            summary = result.get('task_summary', {})
            return PipelineResult(
                success=True,
                stage="task",
                message=f"Task分解完了: {task_count}件, {summary.get('total_hours', 0):.1f}h（05_task/ado_task_create.md）",
                data=result
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                stage="task",
                message=str(e),
                errors=[str(e)]
            )

    def _stage_generate(self) -> PipelineResult:
        """Stage 1: Epic生成（レガシー互換）"""
        return self._stage_epic()

    def _stage_decompose(self) -> PipelineResult:
        """Stage 2: Feature/Story分解（レガシー互換 - feature + story を一括実行）"""
        try:
            decomposed = self.decomposer.decompose()

            # レガシー形式を統一キー形式に変換
            unified = migrate_legacy_decomposition(
                decomposed, self.org, self.repo, self.epic_id
            )

            # JSONファイルとして保存
            output_path = self.output_dir / "decomposition.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(unified, f, ensure_ascii=False, indent=2)

            # レジストリに登録
            for feature in unified.get('features', []):
                feature_key = UnifiedKey.from_string(feature['key'])
                self.registry.register(KeyedItem(
                    key=feature_key,
                    item_type='feature',
                    title=feature['title'],
                    data=feature
                ))
                for story in feature.get('stories', []):
                    story_key = UnifiedKey.from_string(story['key'])
                    self.registry.register(KeyedItem(
                        key=story_key,
                        item_type='story',
                        title=story['title'],
                        data=story
                    ))

            return PipelineResult(
                success=True,
                stage="decompose",
                message=f"分解完了: {len(unified.get('features', []))} Features -> {output_path}",
                data=unified
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                stage="decompose",
                message=str(e),
                errors=[str(e)]
            )

    def _stage_validate(self) -> PipelineResult:
        """Stage 3: 品質チェック"""
        try:
            validation_result = self.validator.validate()

            if validation_result['passed']:
                return PipelineResult(
                    success=True,
                    stage="validate",
                    message="品質チェック合格",
                    data=validation_result,
                    warnings=validation_result.get('warnings', [])
                )
            else:
                # 自動修正を試みる
                if not self.dry_run:
                    fixed = self.validator.auto_fix()
                    if fixed['success']:
                        return PipelineResult(
                            success=True,
                            stage="validate",
                            message="品質チェック: 自動修正適用済み",
                            data=fixed,
                            warnings=fixed.get('warnings', [])
                        )

                return PipelineResult(
                    success=False,
                    stage="validate",
                    message="品質チェック失敗",
                    errors=validation_result.get('errors', [])
                )
        except Exception as e:
            return PipelineResult(
                success=False,
                stage="validate",
                message=str(e),
                errors=[str(e)]
            )

    def _stage_schedule(self) -> PipelineResult:
        """Stage 4: スケジュール最適化"""
        try:
            schedule = self.scheduler.optimize()

            # JSONファイルとして保存
            output_path = self.output_dir / "schedule.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(schedule, f, ensure_ascii=False, indent=2)

            return PipelineResult(
                success=True,
                stage="schedule",
                message=f"スケジュール最適化完了: {schedule.get('total_days', 0)}日 -> {output_path}",
                data=schedule
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                stage="schedule",
                message=str(e),
                errors=[str(e)]
            )

    def _stage_sync(self) -> PipelineResult:
        """Stage 5: プロジェクト管理ツール同期（GitHub/GitLab/ADO）"""
        try:
            # 分解データとスケジュールデータを読み込み
            decomp_path = self.output_dir / "decomposition.json"
            schedule_path = self.output_dir / "schedule.json"

            if not decomp_path.exists():
                return PipelineResult(
                    success=False,
                    stage="sync",
                    message="分解データが見つかりません。先にdecomposeを実行してください。",
                    errors=["decomposition.json not found"]
                )

            with open(decomp_path, 'r', encoding='utf-8') as f:
                decomposition = json.load(f)

            schedule = None
            if schedule_path.exists():
                with open(schedule_path, 'r', encoding='utf-8') as f:
                    schedule = json.load(f)

            # WorkItem に変換
            items = self._convert_to_work_items(decomposition, schedule)

            # プロバイダーで同期
            sync_result = self.provider.sync_items(items)

            # レジストリに外部IDを登録
            provider_name = self.provider.provider_name
            for item_result in sync_result.items:
                unified_key = item_result.get('unified_key')
                external_id = item_result.get('external_id')
                if unified_key and external_id:
                    key = UnifiedKey.from_string(unified_key)
                    self.registry.set_external_id(key, provider_name, external_id)

            # プロジェクトインデックスを保存
            self.registry.save_project_index(self.org, self.repo)

            # 結果を保存
            result_path = self.output_dir / "sync_result.json"
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "success": sync_result.success,
                    "created": sync_result.created,
                    "updated": sync_result.updated,
                    "skipped": sync_result.skipped,
                    "items": sync_result.items,
                }, f, ensure_ascii=False, indent=2)

            return PipelineResult(
                success=sync_result.success,
                stage="sync",
                message=f"同期完了: 作成{sync_result.created}, 更新{sync_result.updated}, スキップ{sync_result.skipped}",
                data={"result": sync_result.items},
                errors=sync_result.errors,
                warnings=sync_result.warnings
            )
        except Exception as e:
            return PipelineResult(
                success=False,
                stage="sync",
                message=str(e),
                errors=[str(e)]
            )

    def _convert_to_work_items(self, decomposition: Dict, schedule: Optional[Dict] = None) -> list:
        """decomposition.json（統一キー形式）を WorkItem リストに変換"""
        items = []

        # スケジュール情報をキーでインデックス化
        schedule_by_key = {}
        if schedule:
            for task in schedule.get('tasks', []):
                # 統一キーまたはレガシーIDでインデックス
                task_key = task.get('key') or task.get('id')
                schedule_by_key[task_key] = task

        for feature in decomposition.get('features', []):
            # 統一キーを優先、なければレガシーID
            feature_key = feature.get('key')
            feature_id = feature.get('legacy_id') or feature.get('id')

            # Feature 自体を WorkItem に
            feature_item = WorkItem(
                id=feature_id,
                unified_key=feature_key,
                title=feature['title'],
                description=feature.get('description', ''),
                item_type=ItemType.FEATURE,
                priority=feature.get('priority', 'medium'),
                estimate_hours=feature.get('total_hours', 0),
                depends_on=feature.get('depends_on', []),
                milestone=feature.get('milestone_id'),
                labels=[f"feature:{feature_id}"],
            )
            items.append(feature_item)

            # Story を処理
            for story in feature.get('stories', []):
                story_key = story.get('key')
                story_id = story.get('legacy_id') or story.get('id')
                sched = schedule_by_key.get(story_key) or schedule_by_key.get(story_id, {})

                story_item = WorkItem(
                    id=story_id,
                    unified_key=story_key,
                    title=story['title'],
                    description=story.get('description', ''),
                    item_type=ItemType.STORY,
                    priority=story.get('priority', 'medium'),
                    estimate_hours=story.get('estimate_hours', 0),
                    depends_on=story.get('depends_on', []),
                    parent_id=feature_id,
                    labels=story.get('labels', []),
                    acceptance_criteria=story.get('acceptance_criteria', []),
                    start_date=sched.get('start_date'),
                    end_date=sched.get('end_date'),
                )
                items.append(story_item)

        return items

    def run_single_stage(self, stage: str) -> PipelineResult:
        """単一ステージ実行（01-planning-requirements 準拠）"""
        stage_map = {
            # 01-planning-requirements 準拠ステージ
            "epic": self._stage_epic,           # 02_epic
            "feature": self._stage_feature,     # 03_feature
            "story": self._stage_story,         # 04_story
            "task": self._stage_task,           # 05_task
            "validate": self._stage_validate,
            "schedule": self._stage_schedule,
            "sync": self._stage_sync,
            # レガシー互換
            "generate": self._stage_generate,
            "decompose": self._stage_decompose,
        }

        if stage not in stage_map:
            return PipelineResult(
                success=False,
                stage=stage,
                message=f"不明なステージ: {stage}",
                errors=[f"有効なステージ: {list(stage_map.keys())}"]
            )

        return stage_map[stage]()

    def print_status(self):
        """現在のプロジェクト状態を表示"""
        print("📊 プロジェクト状態")
        print("=" * 60)

        project = self.config.get('project', {})
        print(f"プロジェクト名: {project.get('name', 'N/A')}")
        print(f"GitHub: {project.get('github', {}).get('owner', 'N/A')}/{project.get('github', {}).get('repo', 'N/A')}")

        epic = self.config.get('epic', {})
        print(f"\nEpicゴール: {epic.get('goal', 'N/A')[:50]}...")

        metrics = epic.get('success_metrics', [])
        print(f"成功指標: {len(metrics)}件")

        schedule = self.config.get('schedule', {})
        print(f"\n開始日: {schedule.get('start_date', 'N/A')}")
        print(f"稼働時間: {schedule.get('hours_per_day', 8)}h/日")


def main():
    parser = argparse.ArgumentParser(
        description="Epic-Driven Planning 統合管理ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 全自動パイプライン（01-planning-requirements 完全実行）
  python epic_manager.py --config config.yaml --mode full-pipeline

  # 個別ステップ（01-planning-requirements 準拠）
  python epic_manager.py --config config.yaml --mode epic      # 02_epic
  python epic_manager.py --config config.yaml --mode feature   # 03_feature
  python epic_manager.py --config config.yaml --mode story     # 04_story
  python epic_manager.py --config config.yaml --mode task      # 05_task

  # 後続ステージ
  python epic_manager.py --config config.yaml --mode validate
  python epic_manager.py --config config.yaml --mode schedule
  python epic_manager.py --config config.yaml --mode sync

  # ドライラン（実際の変更なし）
  python epic_manager.py --config config.yaml --mode full-pipeline --dry-run
        """
    )

    parser.add_argument(
        '--config', '-c',
        required=True,
        help='設定ファイルパス (YAML)'
    )

    parser.add_argument(
        '--mode', '-m',
        choices=[
            'full-pipeline',
            # 01-planning-requirements 準拠
            'epic', 'feature', 'story', 'task',
            # 後続ステージ
            'validate', 'schedule', 'sync',
            # レガシー互換
            'generate', 'decompose',
            # ステータス
            'status'
        ],
        default='full-pipeline',
        help='実行モード (default: full-pipeline)'
    )

    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='実際の変更を行わずにプレビュー'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='詳細出力'
    )

    args = parser.parse_args()

    try:
        manager = EpicManager(
            config_path=args.config,
            dry_run=args.dry_run,
            verbose=args.verbose
        )

        if args.mode == 'status':
            manager.print_status()
            return 0

        if args.mode == 'full-pipeline':
            result = manager.run_full_pipeline()
        else:
            result = manager.run_single_stage(args.mode)

        if result.success:
            print(f"\n[OK] {result.message}")
            return 0
        else:
            print(f"\n[FAIL] {result.message}")
            for error in result.errors:
                print(f"  - {error}")
            return 1

    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] Unexpected: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
