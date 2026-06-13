#!/usr/bin/env python3
"""
Project Sync - 汎用プロジェクト管理ツール同期スクリプト

サポートするプロバイダー:
- github: GitHub Projects V2
- gitlab: GitLab Issues/Boards (coming soon)
- azure_devops / ado: Azure DevOps Work Items (coming soon)

使用例:
    # decomposition.json から GitHub Project を更新
    python project_sync.py \
        --config config.yaml \
        --decomposition decomposition.json \
        --provider github

    # スケジュール情報も反映
    python project_sync.py \
        --config config.yaml \
        --decomposition decomposition.json \
        --schedule schedule.json \
        --provider github

    # ドライラン
    python project_sync.py \
        --config config.yaml \
        --decomposition decomposition.json \
        --provider github \
        --dry-run

    # WorkItem JSON から同期
    python project_sync.py \
        --config config.yaml \
        --items work_items.json \
        --provider ado
"""

import argparse
import json
import yaml
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# =============================================================================
# プロジェクト・組織 一元管理マスター
# =============================================================================
# GitHub / GitLab / Azure DevOps の組織名・プロジェクト名を一箇所で管理
# 新しいプロジェクトを追加する場合はここに追記してください
# =============================================================================

PROJECT_REGISTRY = {
    # ---------------------------------------------------------------------
    # プロジェクト定義
    # キー: プロジェクト識別子（任意の名前）
    # ---------------------------------------------------------------------
    "enterprise-rag-system": {
        "description": "Enterprise RAG System - 社内ドキュメント検索基盤",
        "github": {
            "owner": "nobu007",
            "repo": "enterprise-rag-system",
            "project_number": None,  # GitHub Projects V2 番号（設定時）
        },
        "gitlab": {
            "host": "https://gitlab.com",
            "group": "jinno-ai",
            "project": "enterprise-rag-system",
            "project_path": "jinno-ai/enterprise-rag-system",
        },
        "azure_devops": {
            "organization": "jin5770808",
            "project": "tokyo-career-up",
        },
    },
    "ai-hub": {
        "description": "AI Hub - 統合AI開発基盤",
        "github": {
            "owner": "nobu007",
            "repo": "ai-hub",
            "project_number": None,
        },
        "gitlab": {
            "host": "https://gitlab.com",
            "group": "jinno-ai",
            "project": "ai-hub",
            "project_path": "jinno-ai/ai-hub",
        },
        "azure_devops": {
            "organization": "jin5770808",
            "project": "tokyo-career-up",
        },
    },
    "realtime-edge-detection": {
        "description": "Realtime Edge Detection - エッジ検出システム",
        "github": {
            "owner": "jinno-ai",
            "repo": "realtime-edge-detection",
            "project_number": None,
        },
        "gitlab": {
            "host": "https://gitlab.com",
            "group": "jinno-ai",
            "project": "realtime-edge-detection",
            "project_path": "jinno-ai/realtime-edge-detection",
        },
        "azure_devops": {
            "organization": "jin5770808",
            "project": "tokyo-career-up",
        },
    },
    "llm-agent-framework": {
        "description": "LLM Agent Framework",
        "github": {
            "owner": "jinno-ai",
            "repo": "llm-agent-framework",
            "project_number": None,
        },
        "gitlab": {
            "host": "https://gitlab.com",
            "group": "jinno-ai",
            "project": "llm-agent-framework",
            "project_path": "jinno-ai/llm-agent-framework",
        },
        "azure_devops": {
            "organization": "jin5770808",
            "project": "tokyo-career-up",
        },
    },
}

# 組織マッピング（クロスリファレンス用）
ORGANIZATION_MAPPING = {
    "github": {
        "nobu007": "nobu007",           # 個人アカウント
        "jinno-ai": "jinno-ai",         # 組織
    },
    "gitlab": {
        "jinno-ai": "jinno-ai",         # グループ
    },
    "azure_devops": {
        "jin5770808": "jin5770808",     # 組織
        "jinno-ai": "jin5770808",       # GitHub jinno-ai → ADO jin5770808
        "nobu007": "jin5770808",        # GitHub nobu007 → ADO jin5770808
    },
}

def get_project_config(project_id: str, provider: str) -> Dict[str, Any]:
    """
    プロジェクトIDとプロバイダーから設定を取得

    Args:
        project_id: プロジェクト識別子（PROJECT_REGISTRYのキー）
        provider: "github" | "gitlab" | "azure_devops" | "ado"

    Returns:
        プロバイダー固有の設定辞書
    """
    if project_id not in PROJECT_REGISTRY:
        raise ValueError(f"Unknown project: {project_id}. Available: {list(PROJECT_REGISTRY.keys())}")

    project = PROJECT_REGISTRY[project_id]

    # プロバイダー名の正規化
    if provider == "ado":
        provider = "azure_devops"

    if provider not in project:
        raise ValueError(f"Provider '{provider}' not configured for project '{project_id}'")

    return project[provider]


def list_projects() -> None:
    """登録されているプロジェクト一覧を表示"""
    print("\n" + "=" * 80)
    print("📦 登録プロジェクト一覧")
    print("=" * 80)

    for project_id, config in PROJECT_REGISTRY.items():
        print(f"\n🔹 {project_id}")
        print(f"   説明: {config.get('description', 'N/A')}")

        # GitHub
        gh = config.get("github", {})
        if gh:
            print(f"   GitHub:     {gh.get('owner')}/{gh.get('repo')}")

        # GitLab
        gl = config.get("gitlab", {})
        if gl:
            print(f"   GitLab:     {gl.get('project_path')}")

        # Azure DevOps
        ado = config.get("azure_devops", {})
        if ado:
            print(f"   Azure DevOps: {ado.get('organization')}/{ado.get('project')}")

    print("\n" + "=" * 80)


def get_all_provider_configs(project_id: str) -> Dict[str, Dict[str, Any]]:
    """
    プロジェクトの全プロバイダー設定を取得

    Returns:
        {"github": {...}, "gitlab": {...}, "azure_devops": {...}}
    """
    if project_id not in PROJECT_REGISTRY:
        raise ValueError(f"Unknown project: {project_id}")

    project = PROJECT_REGISTRY[project_id]
    return {
        "github": project.get("github", {}),
        "gitlab": project.get("gitlab", {}),
        "azure_devops": project.get("azure_devops", {}),
    }


# プロバイダーのインポート
from providers import (
    get_provider,
    WorkItem,
    ItemType,
    ItemStatus,
    SyncResult,
)


def load_yaml(path: Path) -> Dict[str, Any]:
    """YAMLファイルを読み込み"""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)




def load_json(path: Path) -> Dict[str, Any]:
    """JSONファイルを読み込み"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def convert_decomposition_to_work_items(
    decomposition: Dict[str, Any],
    schedule: Optional[Dict[str, Any]] = None
) -> List[WorkItem]:
    """
    decomposition.json を WorkItem リストに変換

    Args:
        decomposition: epic_decomposer.py の出力
        schedule: schedule_optimizer.py の出力（オプション）
    """
    items: List[WorkItem] = []

    # スケジュール情報をIDでインデックス化
    schedule_by_id: Dict[str, Dict] = {}
    if schedule:
        for task in schedule.get('tasks', []):
            schedule_by_id[task['id']] = task

    # Feature を処理
    for feature in decomposition.get('features', []):
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

            # スケジュール情報があれば反映
            sched = schedule_by_id.get(story_key) or schedule_by_id.get(story_id, {})

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


def normalize_priority(value: Optional[str]) -> str:
    if not value:
        return "medium"
    key = str(value).strip().lower()
    if key in {"high", "p0", "p1", "critical", "urgent"}:
        return "high"
    if key in {"medium", "p2", "normal"}:
        return "medium"
    if key in {"low", "p3", "p4", "minor"}:
        return "low"
    return "medium"


def parse_item_type(value: Optional[str]) -> ItemType:
    if isinstance(value, ItemType):
        return value
    if not value:
        return ItemType.STORY
    key = str(value).strip().lower().replace(" ", "").replace("-", "")
    if key in {"epic", "epics"}:
        return ItemType.EPIC
    if key in {"feature", "features"}:
        return ItemType.FEATURE
    if key in {"story", "userstory", "userstories"}:
        return ItemType.STORY
    if key in {"task", "tasks"}:
        return ItemType.TASK
    if key in {"bug", "bugs", "defect"}:
        return ItemType.BUG
    return ItemType.STORY


def parse_status(value: Optional[str]) -> ItemStatus:
    if not value:
        return ItemStatus.BACKLOG
    key = str(value).strip().lower().replace(" ", "")
    if key in {"backlog", "new"}:
        return ItemStatus.BACKLOG
    if key in {"todo"}:
        return ItemStatus.TODO
    if key in {"inprogress", "doing", "active"}:
        return ItemStatus.IN_PROGRESS
    if key in {"review", "inreview", "qa", "testing"}:
        return ItemStatus.IN_REVIEW
    if key in {"done", "closed", "completed", "resolved"}:
        return ItemStatus.DONE
    return ItemStatus.BACKLOG


def convert_items_to_work_items(raw_items: List[Dict[str, Any]]) -> List[WorkItem]:
    items: List[WorkItem] = []
    for raw in raw_items:
        labels = raw.get("labels") or []
        if isinstance(labels, str):
            labels = [l.strip() for l in labels.split(",") if l.strip()]

        depends_on = raw.get("depends_on") or []
        if isinstance(depends_on, str):
            depends_on = [d.strip() for d in depends_on.split(",") if d.strip()]

        acceptance_criteria = raw.get("acceptance_criteria") or []
        if isinstance(acceptance_criteria, str):
            acceptance_criteria = [a.strip() for a in acceptance_criteria.split("\n") if a.strip()]

        estimate_raw = raw.get("estimate_hours", raw.get("estimate", 0))
        estimate_hours = 0
        if isinstance(estimate_raw, (int, float)):
            estimate_hours = int(estimate_raw)
        else:
            try:
                estimate_hours = int(float(str(estimate_raw))) if estimate_raw else 0
            except ValueError:
                estimate_hours = 0

        item = WorkItem(
            id=raw.get("id") or raw.get("key") or raw.get("title", "item"),
            unified_key=raw.get("unified_key") or raw.get("key"),
            title=raw.get("title", ""),
            description=raw.get("description", ""),
            item_type=parse_item_type(raw.get("item_type") or raw.get("type")),
            priority=normalize_priority(raw.get("priority")),
            estimate_hours=estimate_hours,
            status=parse_status(raw.get("status")),
            parent_id=raw.get("parent_id"),
            depends_on=depends_on,
            labels=labels,
            acceptance_criteria=acceptance_criteria,
            assignee=raw.get("assignee"),
            milestone=raw.get("milestone"),
            start_date=raw.get("start_date"),
            end_date=raw.get("end_date"),
            external_id=raw.get("external_id"),
            external_url=raw.get("external_url"),
        )
        items.append(item)
    return items


def print_summary(result: SyncResult, provider_name: str):
    """同期結果のサマリーを表示"""
    print("\n" + "=" * 60)
    print(f"[SYNC COMPLETE] Provider: {provider_name}")
    print("=" * 60)


def update_registry_external_refs(
    registry_dir: Path,
    sync_items: List[Dict[str, Any]],
    provider: str
) -> int:
    """
    同期結果を _registry の external_refs に反映

    Args:
        registry_dir: _registry ディレクトリ
        sync_items: 同期結果のアイテムリスト
        provider: プロバイダー名 (github, ado, gitlab)

    Returns:
        更新件数
    """
    updated_count = 0

    for item in sync_items:
        unified_key = item.get('unified_key')
        external_id = item.get('external_id')

        if not unified_key or not external_id:
            continue

        # キーからパスを構築
        parts = unified_key.split('/')
        if len(parts) < 3:
            continue

        item_path = registry_dir
        for part in parts:
            item_path = item_path / part
        item_path = item_path / '_item.json'

        if not item_path.exists():
            continue

        try:
            with open(item_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # external_refs を更新
            if 'external_refs' not in data:
                data['external_refs'] = {}

            data['external_refs'][provider] = str(external_id)
            data['updated_at'] = datetime.now().isoformat()

            with open(item_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            updated_count += 1
        except Exception as e:
            print(f"[WARN] Failed to update registry for {unified_key}: {e}")

    if updated_count > 0:
        print(f"\n[REGISTRY] Updated {updated_count} items in {registry_dir}")

    return updated_count

    print(f"\nResults:")
    print(f"  - Created: {result.created}")
    print(f"  - Updated: {result.updated}")
    print(f"  - Skipped: {result.skipped}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  [ERROR] {error}")

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  [WARN] {warning}")

    if result.items:
        print(f"\nProcessed Items ({len(result.items)}):")
        for item in result.items[:10]:  # 最初の10件
            action = item.get('action', 'unknown')
            ext_id = item.get('external_id', '-')
            print(f"  [{action.upper()}] {item['id']} -> #{ext_id}")

        if len(result.items) > 10:
            print(f"  ... and {len(result.items) - 10} more")

    status = "SUCCESS" if result.success else "FAILED"
    print(f"\nStatus: {status}")


def main():
    parser = argparse.ArgumentParser(
        description="汎用プロジェクト管理ツール同期スクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 登録プロジェクト一覧を表示
  python project_sync.py --list-projects

  # プロジェクトIDを指定して同期（設定ファイル不要）
  python project_sync.py --project enterprise-rag-system -d decomposition.json -p github
  python project_sync.py --project enterprise-rag-system -d decomposition.json -p gitlab
  python project_sync.py --project enterprise-rag-system -d decomposition.json -p ado

  # 全プロバイダーに同期
  python project_sync.py --project enterprise-rag-system -d decomposition.json --all-providers

  # 従来の方法（設定ファイル指定）
  python project_sync.py -c config.yaml -d decomposition.json -p github

  # ドライラン（実際には実行しない）
  python project_sync.py --project ai-hub -d decomposition.json -p github --dry-run
        """
    )

    # プロジェクト管理オプション
    parser.add_argument(
        '--list-projects',
        action='store_true',
        help='登録されているプロジェクト一覧を表示'
    )
    parser.add_argument(
        '--project',
        choices=list(PROJECT_REGISTRY.keys()),
        help='プロジェクトID（PROJECT_REGISTRYから選択）'
    )
    parser.add_argument(
        '--all-providers',
        action='store_true',
        help='全プロバイダー（GitHub/GitLab/Azure DevOps）に同期'
    )

    parser.add_argument(
        '--config', '-c',
        help='設定ファイルパス (YAML) - --project指定時は不要'
    )
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        '--decomposition', '-d',
        help='分解データファイルパス (JSON) - epic_decomposer.py の出力'
    )
    input_group.add_argument(
        '--items',
        help='WorkItem一覧ファイルパス (JSON)'
    )
    parser.add_argument(
        '--schedule', '-s',
        help='スケジュールデータファイルパス (JSON) - schedule_optimizer.py の出力'
    )
    parser.add_argument(
        '--provider', '-p',
        choices=['github', 'gitlab', 'azure_devops', 'ado'],
        default='github',
        help='同期先プロバイダー (default: github)'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='ドライラン（実際には実行しない）'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='詳細ログを出力'
    )
    parser.add_argument(
        '--output', '-o',
        help='同期結果の出力先 (JSON)'
    )

    args = parser.parse_args()

    # --list-projects オプションの処理
    if args.list_projects:
        list_projects()
        return 0

    # 入力ファイルのチェック
    if not args.decomposition and not args.items:
        parser.error("--decomposition または --items が必要です（--list-projects以外）")

    try:
        # プロジェクトIDまたは設定ファイルからconfig生成
        if args.project:
            # PROJECT_REGISTRY から設定を動的生成
            print(f"Using project: {args.project}")
            project_configs = get_all_provider_configs(args.project)

            # 全プロバイダー同期モード
            if args.all_providers:
                providers_to_sync = ["github", "gitlab", "azure_devops"]
            else:
                providers_to_sync = [args.provider if args.provider != "ado" else "azure_devops"]

            # 設定を動的構築
            config = {
                "project": {
                    "name": args.project,
                    "registry_dir": "output/_registry",
                }
            }
            # 各プロバイダー設定を追加
            for prov in ["github", "gitlab", "azure_devops"]:
                if project_configs.get(prov):
                    config["project"][prov] = project_configs[prov]
        else:
            if not args.config:
                parser.error("--config または --project が必要です")
            print(f"Loading config: {args.config}")
            config = load_yaml(Path(args.config))
            providers_to_sync = [args.provider if args.provider != "ado" else "azure_devops"]
            if args.all_providers:
                providers_to_sync = ["github", "gitlab", "azure_devops"]

        schedule = None
        if args.items:
            print(f"Loading items: {args.items}")
            raw_items = load_json(Path(args.items))
            if isinstance(raw_items, dict) and "items" in raw_items:
                raw_items = raw_items["items"]
            if not isinstance(raw_items, list):
                raise ValueError("items file must be a JSON list (or {\"items\": [...]})")
            items = convert_items_to_work_items(raw_items)
        else:
            print(f"Loading decomposition: {args.decomposition}")
            decomposition = load_json(Path(args.decomposition))

            if args.schedule:
                print(f"Loading schedule: {args.schedule}")
                schedule = load_json(Path(args.schedule))

            # WorkItem に変換
            print("\nConverting to WorkItems...")
            items = convert_decomposition_to_work_items(decomposition, schedule)

        # サマリー
        print("\nWorkItem summary:")
        counts = {}
        for item in items:
            counts[item.item_type] = counts.get(item.item_type, 0) + 1
        for item_type, count in sorted(counts.items(), key=lambda x: x[0].value):
            print(f"  - {item_type.value}: {count}")
        print(f"  - Total: {len(items)}")

        # 複数プロバイダー同期
        all_results = []
        overall_success = True

        for prov in providers_to_sync:
            print(f"\n{'='*60}")
            print(f"🔄 Syncing to: {prov}")
            print(f"{'='*60}")

            # プロバイダー固有の設定をconfigに反映
            if args.project and prov in config.get("project", {}):
                prov_config = config["project"][prov]
                print(f"   Config: {prov_config}")

            try:
                provider = get_provider(prov, config, dry_run=args.dry_run)

                if args.dry_run:
                    print("[DRY-RUN MODE] No actual changes will be made")

                # 同期実行
                print("\nStarting sync...")
                result = provider.sync_items(items)

                # _registry に external_refs を更新
                if result.success and result.items:
                    registry_dir = Path(config.get('project', {}).get('registry_dir', 'output/_registry'))
                    update_registry_external_refs(registry_dir, result.items, prov)

                # サマリー表示
                print_summary(result, prov)
                all_results.append((prov, result))

                if not result.success:
                    overall_success = False

            except Exception as e:
                print(f"[ERROR] {prov}: {e}")
                if args.verbose:
                    import traceback
                    traceback.print_exc()
                overall_success = False

        # 全体サマリー（複数プロバイダーの場合）
        if len(providers_to_sync) > 1:
            print(f"\n{'='*60}")
            print("📊 全体サマリー")
            print(f"{'='*60}")
            for prov, result in all_results:
                status = "✅" if result.success else "❌"
                print(f"  {status} {prov}: Created={result.created}, Updated={result.updated}, Failed={len(result.errors)}")

        # 結果を出力
        if args.output and all_results:
            # 複数プロバイダーの場合は全結果をまとめる
            output_data = {
                "timestamp": datetime.now().isoformat(),
                "project": args.project,
                "providers": providers_to_sync,
                "dry_run": args.dry_run,
                "overall_success": overall_success,
                "results": [
                    {
                        "provider": prov,
                        "success": res.success,
                        "created": res.created,
                        "updated": res.updated,
                        "skipped": res.skipped,
                        "errors": res.errors,
                    }
                    for prov, res in all_results
                ],
            }

            Path(args.output).write_text(
                json.dumps(output_data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            print(f"\nResults saved to: {args.output}")

        return 0 if overall_success else 1

    except FileNotFoundError as e:
        print(f"[ERROR] File not found: {e}")
        return 1
    except ValueError as e:
        print(f"[ERROR] Invalid value: {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
