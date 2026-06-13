#!/usr/bin/env python3
"""
GitHub Project 自動スケジューリングスクリプト

機能:
- ラベルの工数（estimate:Xh）から日程を自動計算
- 依存関係（Depends on: #XX）から順序を決定
- クリティカルパスを考慮したスケジューリング

使用例:
    python auto_schedule.py --owner jinno-ai --project 1 --start-date 2026-01-27
"""

import subprocess
import json
import re
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class Task:
    """タスク情報"""
    issue_number: int
    item_id: str
    title: str
    estimate_hours: int = 8  # デフォルト8h
    depends_on: List[int] = field(default_factory=list)
    milestone: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @property
    def duration_days(self) -> int:
        """工数から日数を計算（8h = 1日）"""
        return max(1, (self.estimate_hours + 7) // 8)

class AutoScheduler:
    """自動スケジューラー"""

    def __init__(self, owner: str, project_number: int, hours_per_day: int = 8):
        self.owner = owner
        self.project_number = project_number
        self.hours_per_day = hours_per_day
        self.tasks: Dict[int, Task] = {}
        self.project_id = ""
        self.field_ids = {}

    def run_gh(self, args: List[str]) -> str:
        """gh CLIを実行"""
        cmd = ["gh"] + args
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            print(f"Warning: {result.stderr}")
        return result.stdout or ""

    def fetch_project_info(self):
        """プロジェクト情報を取得"""
        # プロジェクトID取得
        result = self.run_gh([
            "project", "view", str(self.project_number),
            "--owner", self.owner, "--format", "json"
        ])
        data = json.loads(result)
        self.project_id = data["id"]

        # フィールドID取得
        result = self.run_gh([
            "project", "field-list", str(self.project_number),
            "--owner", self.owner, "--format", "json"
        ])
        fields = json.loads(result)
        for f in fields["fields"]:
            self.field_ids[f["name"]] = f["id"]

        print(f"Project ID: {self.project_id}")
        print(f"Fields: {list(self.field_ids.keys())}")

    def fetch_items(self):
        """アイテム一覧を取得"""
        result = self.run_gh([
            "project", "item-list", str(self.project_number),
            "--owner", self.owner, "--format", "json", "--limit", "100"
        ])
        data = json.loads(result)

        for item in data["items"]:
            if item["content"]["type"] != "Issue":
                continue

            issue_num = item["content"]["number"]

            # 工数をラベルから抽出
            estimate = 8  # デフォルト
            for label in item.get("labels", []):
                match = re.match(r"estimate:(\d+)h", label)
                if match:
                    estimate = int(match.group(1))
                    break

            # 依存関係を本文から抽出（**Depends on**: #XX 形式をサポート）
            depends = []
            body = item["content"].get("body", "") or ""
            # パターン: "Depends on": #XX, "depends on #XX", "Depends on: #XX"
            for match in re.finditer(r"\*?\*?[Dd]epends\s+on\*?\*?[:\s]*#(\d+)", body):
                depends.append(int(match.group(1)))

            # マイルストーン
            milestone = item.get("milestone", {}).get("title", "") if item.get("milestone") else ""

            self.tasks[issue_num] = Task(
                issue_number=issue_num,
                item_id=item["id"],
                title=item["content"]["title"],
                estimate_hours=estimate,
                depends_on=depends,
                milestone=milestone
            )

        print(f"\nLoaded {len(self.tasks)} tasks:")
        for t in self.tasks.values():
            deps = f" (depends: {t.depends_on})" if t.depends_on else ""
            print(f"  #{t.issue_number}: {t.estimate_hours}h{deps} - {t.title[:40]}")

    def topological_sort(self) -> List[int]:
        """依存関係を考慮したトポロジカルソート"""
        # 依存グラフ構築
        in_degree = defaultdict(int)
        graph = defaultdict(list)

        for task in self.tasks.values():
            for dep in task.depends_on:
                if dep in self.tasks:
                    graph[dep].append(task.issue_number)
                    in_degree[task.issue_number] += 1

        # カーンのアルゴリズム
        queue = [t for t in self.tasks if in_degree[t] == 0]
        result = []

        while queue:
            # 同じ深さのタスクは番号順にソート（安定性のため）
            queue.sort()
            node = queue.pop(0)
            result.append(node)

            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 循環依存チェック
        if len(result) != len(self.tasks):
            remaining = set(self.tasks.keys()) - set(result)
            print(f"⚠️ 循環依存を検出: {remaining}")
            # 循環依存のタスクは末尾に追加
            result.extend(sorted(remaining))

        return result

    def calculate_schedule(self, start_date: datetime) -> Dict[int, Task]:
        """スケジュールを計算"""
        order = self.topological_sort()
        print(f"\n実行順序: {order}")

        # 各タスクの終了日を追跡
        task_end_dates: Dict[int, datetime] = {}

        for issue_num in order:
            task = self.tasks[issue_num]

            # 開始日 = 依存タスクの最大終了日 or 基準日
            if task.depends_on:
                dep_ends = [
                    task_end_dates.get(d, start_date)
                    for d in task.depends_on if d in self.tasks
                ]
                task.start_date = max(dep_ends) + timedelta(days=1) if dep_ends else start_date
            else:
                task.start_date = start_date

            # 終了日 = 開始日 + 日数 - 1
            task.end_date = task.start_date + timedelta(days=task.duration_days - 1)
            task_end_dates[issue_num] = task.end_date

        return self.tasks

    def update_project(self):
        """プロジェクトのフィールドを更新"""
        print("\n🔄 プロジェクト更新中...")

        start_field = self.field_ids.get("Start Date")
        end_field = self.field_ids.get("End Date")
        estimate_field = self.field_ids.get("Estimate Hours")

        if not all([start_field, end_field]):
            print("❌ 日付フィールドが見つかりません")
            return

        for task in self.tasks.values():
            if not task.start_date or not task.end_date:
                continue

            print(f"  #{task.issue_number}: {task.start_date.date()} → {task.end_date.date()}")

            # Start Date
            self.run_gh([
                "project", "item-edit",
                "--project-id", self.project_id,
                "--id", task.item_id,
                "--field-id", start_field,
                "--date", task.start_date.strftime("%Y-%m-%d")
            ])

            # End Date
            self.run_gh([
                "project", "item-edit",
                "--project-id", self.project_id,
                "--id", task.item_id,
                "--field-id", end_field,
                "--date", task.end_date.strftime("%Y-%m-%d")
            ])

            # Estimate Hours
            if estimate_field:
                self.run_gh([
                    "project", "item-edit",
                    "--project-id", self.project_id,
                    "--id", task.item_id,
                    "--field-id", estimate_field,
                    "--number", str(task.estimate_hours)
                ])

        print("✅ 完了")

    def print_gantt(self):
        """Mermaid形式のガントチャートを出力"""
        print("\n📊 ガントチャート (Mermaid形式):\n")
        print("```mermaid")
        print("gantt")
        print("    title Project Schedule")
        print("    dateFormat YYYY-MM-DD")
        print()

        # マイルストーン別にグループ化
        by_milestone = defaultdict(list)
        for task in sorted(self.tasks.values(), key=lambda t: t.start_date or datetime.max):
            by_milestone[task.milestone or "Other"].append(task)

        for ms, tasks in by_milestone.items():
            print(f"    section {ms}")
            for task in tasks:
                if task.start_date:
                    duration = task.duration_days
                    title = task.title[:25].replace(":", " ")
                    print(f"    #{task.issue_number} {title} :t{task.issue_number}, "
                          f"{task.start_date.strftime('%Y-%m-%d')}, {duration}d")

        print("```")

    def print_summary(self):
        """サマリーを出力"""
        print("\n📋 スケジュールサマリー:")
        print("=" * 70)
        print(f"{'Issue':<8} {'開始日':<12} {'終了日':<12} {'工数':<6} {'タイトル':<30}")
        print("-" * 70)

        for task in sorted(self.tasks.values(), key=lambda t: t.start_date or datetime.max):
            if task.start_date:
                print(f"#{task.issue_number:<6} "
                      f"{task.start_date.strftime('%Y-%m-%d'):<12} "
                      f"{task.end_date.strftime('%Y-%m-%d'):<12} "
                      f"{task.estimate_hours}h{'':<4} "
                      f"{task.title[:30]}")

        # クリティカルパス計算
        if self.tasks:
            max_end = max((t.end_date for t in self.tasks.values() if t.end_date), default=None)
            min_start = min((t.start_date for t in self.tasks.values() if t.start_date), default=None)
            if max_end and min_start:
                total_days = (max_end - min_start).days + 1
                total_hours = sum(t.estimate_hours for t in self.tasks.values())
                print("-" * 70)
                print(f"プロジェクト期間: {min_start.date()} → {max_end.date()} ({total_days}日)")
                print(f"総工数: {total_hours}h ({total_hours/8:.1f}人日)")

def main():
    parser = argparse.ArgumentParser(description="GitHub Project自動スケジューラー")
    parser.add_argument("--owner", required=True, help="プロジェクトオーナー")
    parser.add_argument("--project", type=int, required=True, help="プロジェクト番号")
    parser.add_argument("--start-date", required=True, help="開始基準日 (YYYY-MM-DD)")
    parser.add_argument("--hours-per-day", type=int, default=8, help="1日の作業時間")
    parser.add_argument("--dry-run", action="store_true", help="実行せずにプレビューのみ")

    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d")

    scheduler = AutoScheduler(args.owner, args.project, args.hours_per_day)

    print("🚀 GitHub Project 自動スケジューラー")
    print(f"   Owner: {args.owner}")
    print(f"   Project: #{args.project}")
    print(f"   Start Date: {start.date()}")
    print()

    scheduler.fetch_project_info()
    scheduler.fetch_items()
    scheduler.calculate_schedule(start)
    scheduler.print_summary()
    scheduler.print_gantt()

    if not args.dry_run:
        scheduler.update_project()
    else:
        print("\n⚠️ Dry-run モード: 実際の更新はスキップされました")

if __name__ == "__main__":
    main()
