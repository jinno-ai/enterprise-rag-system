#!/usr/bin/env python3
"""
Schedule Optimizer - 依存関係解析・自動スケジューリング

機能:
- 依存関係からトポロジカルソート
- クリティカルパス計算
- 日程自動最適化
- ガントチャート生成

使用例:
    python schedule_optimizer.py --config config.yaml --output schedule.md
"""

import argparse
import yaml
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ScheduledTask:
    """スケジュール済みタスク"""
    id: str
    title: str
    estimate_hours: int
    depends_on: List[str]
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    feature_id: str = ""
    priority: str = "medium"

    @property
    def duration_days(self) -> int:
        """工数から日数を計算"""
        return max(1, (self.estimate_hours + 7) // 8)


class ScheduleOptimizer:
    """スケジュール最適化クラス"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.schedule_config = config.get('schedule', {})
        self.tasks: Dict[str, ScheduledTask] = {}

        # スケジュール設定
        self.hours_per_day = self.schedule_config.get('hours_per_day', 8)
        self.working_days = set(self.schedule_config.get('working_days', [0, 1, 2, 3, 4]))
        self.holidays = set(self.schedule_config.get('holidays', []))

        # 開始日
        start_date_str = self.schedule_config.get('start_date', datetime.now().strftime('%Y-%m-%d'))
        self.start_date = datetime.strptime(start_date_str, '%Y-%m-%d')

    def load_decomposition(self, decomposition_data: Dict[str, Any]):
        """分解データからタスクを読み込み"""
        for feature in decomposition_data.get('features', []):
            for story in feature.get('stories', []):
                task = ScheduledTask(
                    id=story['id'],
                    title=story['title'],
                    estimate_hours=story.get('estimate_hours', 8),
                    depends_on=story.get('depends_on', []),
                    feature_id=feature['id'],
                    priority=story.get('priority', 'medium'),
                )
                self.tasks[task.id] = task

    def optimize(self) -> Dict[str, Any]:
        """スケジュール最適化のメイン処理"""
        if not self.tasks:
            return {
                "success": False,
                "message": "タスクがありません",
                "tasks": [],
            }

        # トポロジカルソート
        sorted_ids = self._topological_sort()

        # 日程計算
        self._calculate_dates(sorted_ids)

        # 結果を構造化
        return self._build_result()

    def _topological_sort(self) -> List[str]:
        """トポロジカルソートで実行順序を決定"""
        # 入次数カウント
        in_degree = defaultdict(int)
        graph = defaultdict(list)

        all_ids = set(self.tasks.keys())

        for task in self.tasks.values():
            for dep in task.depends_on:
                if dep in all_ids:
                    graph[dep].append(task.id)
                    in_degree[task.id] += 1

        # カーンのアルゴリズム
        queue = [tid for tid in all_ids if in_degree[tid] == 0]
        queue.sort()  # 安定性のためソート

        result = []
        while queue:
            node = queue.pop(0)
            result.append(node)

            for neighbor in sorted(graph[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            queue.sort()

        # 循環依存チェック
        if len(result) != len(all_ids):
            remaining = all_ids - set(result)
            print(f"⚠️ 循環依存検出: {remaining}")
            result.extend(sorted(remaining))

        return result

    def _calculate_dates(self, sorted_ids: List[str]):
        """日程を計算"""
        task_end_dates: Dict[str, datetime] = {}

        for task_id in sorted_ids:
            task = self.tasks[task_id]

            # 開始日 = 依存タスクの最大終了日の翌稼働日 or 基準日
            if task.depends_on:
                dep_ends = [
                    task_end_dates[d] for d in task.depends_on
                    if d in task_end_dates
                ]
                if dep_ends:
                    latest_end = max(dep_ends)
                    task.start_date = self._next_working_day(latest_end + timedelta(days=1))
                else:
                    task.start_date = self._next_working_day(self.start_date)
            else:
                task.start_date = self._next_working_day(self.start_date)

            # 終了日 = 開始日 + 稼働日数
            task.end_date = self._add_working_days(task.start_date, task.duration_days - 1)
            task_end_dates[task_id] = task.end_date

    def _next_working_day(self, date: datetime) -> datetime:
        """次の稼働日を取得"""
        while True:
            if date.weekday() in self.working_days:
                date_str = date.strftime('%Y-%m-%d')
                if date_str not in self.holidays:
                    return date
            date += timedelta(days=1)

    def _add_working_days(self, start: datetime, days: int) -> datetime:
        """稼働日数を加算"""
        current = start
        remaining = days

        while remaining > 0:
            current += timedelta(days=1)
            if current.weekday() in self.working_days:
                date_str = current.strftime('%Y-%m-%d')
                if date_str not in self.holidays:
                    remaining -= 1

        return current

    def _build_result(self) -> Dict[str, Any]:
        """結果を構造化"""
        tasks_data = []

        for task in sorted(self.tasks.values(), key=lambda t: t.start_date or datetime.max):
            tasks_data.append({
                "id": task.id,
                "title": task.title,
                "feature_id": task.feature_id,
                "estimate_hours": task.estimate_hours,
                "duration_days": task.duration_days,
                "depends_on": task.depends_on,
                "start_date": task.start_date.strftime('%Y-%m-%d') if task.start_date else None,
                "end_date": task.end_date.strftime('%Y-%m-%d') if task.end_date else None,
                "priority": task.priority,
            })

        # 統計
        if self.tasks:
            all_starts = [t.start_date for t in self.tasks.values() if t.start_date]
            all_ends = [t.end_date for t in self.tasks.values() if t.end_date]

            min_start = min(all_starts) if all_starts else None
            max_end = max(all_ends) if all_ends else None
            total_days = (max_end - min_start).days + 1 if min_start and max_end else 0
            total_hours = sum(t.estimate_hours for t in self.tasks.values())
        else:
            min_start = max_end = None
            total_days = total_hours = 0

        return {
            "success": True,
            "tasks": tasks_data,
            "summary": {
                "task_count": len(self.tasks),
                "total_hours": total_hours,
                "total_working_days": (total_hours + self.hours_per_day - 1) // self.hours_per_day,
                "calendar_days": total_days,
                "start_date": min_start.strftime('%Y-%m-%d') if min_start else None,
                "end_date": max_end.strftime('%Y-%m-%d') if max_end else None,
            },
            "total_days": total_days,
        }

    def generate_gantt_mermaid(self) -> str:
        """Mermaid形式のガントチャートを生成"""
        result = self.optimize()

        lines = [
            "```mermaid",
            "gantt",
            "    title プロジェクトスケジュール",
            "    dateFormat YYYY-MM-DD",
            "",
        ]

        # Feature別にグループ化
        by_feature = defaultdict(list)
        for task in result['tasks']:
            by_feature[task['feature_id']].append(task)

        for feature_id, tasks in sorted(by_feature.items()):
            lines.append(f"    section {feature_id}")
            for task in sorted(tasks, key=lambda t: t['start_date'] or ''):
                if task['start_date']:
                    task_id = task['id'].lower().replace('-', '_')
                    title = task['title'][:30]
                    lines.append(f"    {title} :{task_id}, {task['start_date']}, {task['duration_days']}d")

        lines.append("```")

        return "\n".join(lines)

    def generate_schedule_markdown(self) -> str:
        """Markdown形式のスケジュールを生成"""
        result = self.optimize()

        lines = [
            "# プロジェクトスケジュール",
            "",
            f"生成日時: {datetime.now().isoformat()}",
            "",
            "## サマリー",
            "",
            f"- タスク数: {result['summary']['task_count']}",
            f"- 総工数: {result['summary']['total_hours']}h",
            f"- 稼働日数: {result['summary']['total_working_days']}日",
            f"- カレンダー日数: {result['summary']['calendar_days']}日",
            f"- 期間: {result['summary']['start_date']} → {result['summary']['end_date']}",
            "",
            "## タスク一覧",
            "",
            "| ID | タイトル | Feature | 開始日 | 終了日 | 工数 | 依存 |",
            "|----|---------|---------|--------|--------|------|------|",
        ]

        for task in result['tasks']:
            deps = ', '.join(task['depends_on']) if task['depends_on'] else '-'
            lines.append(
                f"| {task['id']} | {task['title'][:25]} | {task['feature_id']} | "
                f"{task['start_date']} | {task['end_date']} | {task['estimate_hours']}h | {deps} |"
            )

        lines.extend([
            "",
            "## ガントチャート",
            "",
            self.generate_gantt_mermaid(),
        ])

        return "\n".join(lines)

    def generate_github_dates(self) -> List[Dict[str, Any]]:
        """GitHub Project更新用のデータを生成"""
        result = self.optimize()

        github_data = []
        for task in result['tasks']:
            github_data.append({
                "id": task['id'],
                "start_date": task['start_date'],
                "end_date": task['end_date'],
                "estimate_hours": task['estimate_hours'],
            })

        return github_data


def main():
    parser = argparse.ArgumentParser(description="スケジュール最適化ツール")
    parser.add_argument('--config', '-c', required=True, help='設定ファイルパス')
    parser.add_argument('--decomposition', '-d', help='分解データJSONパス')
    parser.add_argument('--output', '-o', help='出力パス')
    parser.add_argument('--format', '-f', choices=['markdown', 'json', 'mermaid', 'github'], default='markdown')

    args = parser.parse_args()

    # 設定読み込み
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    optimizer = ScheduleOptimizer(config)

    # 分解データ読み込み
    if args.decomposition:
        with open(args.decomposition, 'r', encoding='utf-8') as f:
            decomposition = json.load(f)
        optimizer.load_decomposition(decomposition)

    # 出力生成
    if args.format == 'markdown':
        output = optimizer.generate_schedule_markdown()
    elif args.format == 'mermaid':
        output = optimizer.generate_gantt_mermaid()
    elif args.format == 'github':
        output = json.dumps(optimizer.generate_github_dates(), ensure_ascii=False, indent=2)
    else:
        result = optimizer.optimize()
        output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"✅ 出力: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
