#!/usr/bin/env python3
"""
GitHub Sync - GitHub Project/Issues 連携

機能:
- Epic/Feature/Story → GitHub Issues 作成
- GitHub Project へのアイテム追加
- 日付フィールドの自動設定
- ラベル・マイルストーンの自動作成

使用例:
    python github_sync.py --config config.yaml --sync
"""

import argparse
import subprocess
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class SyncResult:
    """同期結果"""
    success: bool
    issues_created: int
    issues_updated: int
    errors: List[str]


class GitHubSync:
    """GitHub同期クラス"""

    def __init__(self, config: Dict[str, Any], dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run

        # GitHub設定
        github_config = config.get('project', {}).get('github', {})
        self.owner = github_config.get('owner', '')
        self.repo = github_config.get('repo', '')
        self.project_number = github_config.get('project_number', 0)

        # 同期設定
        sync_config = config.get('github_sync', {})
        self.sync_epics = sync_config.get('sync_epics', True)
        self.sync_features = sync_config.get('sync_features', True)
        self.sync_stories = sync_config.get('sync_stories', True)
        self.create_labels = sync_config.get('create_labels', True)
        self.create_milestones = sync_config.get('create_milestones', True)

        # フィールド名
        self.field_names = sync_config.get('fields', {
            'start_date': 'Start Date',
            'end_date': 'End Date',
            'estimate': 'Estimate Hours',
        })

        # 状態
        self.project_id = ""
        self.field_ids = {}
        self.created_issues: Dict[str, int] = {}  # id -> issue_number
        self.existing_issues: Dict[str, int] = {}  # title -> issue_number（冪等性用）

    def run_gh(self, args: List[str], check: bool = True) -> Optional[str]:
        """gh CLIを実行"""
        if self.dry_run:
            print(f"[Dry-run] gh {' '.join(args)}")
            return None

        cmd = ["gh"] + args
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace'
        )

        if check and result.returncode != 0:
            print(f"Warning: {result.stderr}")
            return None

        return result.stdout

    def fetch_project_info(self):
        """プロジェクト情報を取得"""
        if self.dry_run:
            print("[Dry-run] プロジェクト情報取得スキップ")
            return

        # プロジェクトID取得
        result = self.run_gh([
            "project", "view", str(self.project_number),
            "--owner", self.owner, "--format", "json"
        ])
        if result:
            data = json.loads(result)
            self.project_id = data.get("id", "")

        # フィールドID取得
        result = self.run_gh([
            "project", "field-list", str(self.project_number),
            "--owner", self.owner, "--format", "json"
        ])
        if result:
            fields = json.loads(result)
            for f in fields.get("fields", []):
                self.field_ids[f["name"]] = f["id"]

        print(f"Project ID: {self.project_id}")
        print(f"Fields: {list(self.field_ids.keys())}")

    def fetch_existing_issues(self):
        """既存Issueを取得（冪等性確保のため）"""
        if self.dry_run:
            print("[Dry-run] 既存Issue取得スキップ")
            return

        result = self.run_gh([
            "issue", "list",
            "--repo", f"{self.owner}/{self.repo}",
            "--state", "all",
            "--limit", "500",
            "--json", "number,title"
        ])
        if result:
            issues = json.loads(result)
            for issue in issues:
                self.existing_issues[issue["title"]] = issue["number"]
            print(f"既存Issue数: {len(self.existing_issues)}")

    def find_existing_issue(self, title: str) -> Optional[int]:
        """タイトルで既存Issueを検索"""
        return self.existing_issues.get(title)

    def ensure_labels(self, labels: List[str]):
        """ラベルが存在することを確認・作成"""
        if not self.create_labels:
            return

        for label in labels:
            # ラベル存在確認（エラーを無視）
            self.run_gh([
                "label", "create", label,
                "--repo", f"{self.owner}/{self.repo}",
                "--force"
            ], check=False)

    def ensure_milestone(self, milestone_id: str, title: str):
        """マイルストーンが存在することを確認・作成"""
        if not self.create_milestones:
            return

        # マイルストーン作成（既存なら無視）
        self.run_gh([
            "api", f"repos/{self.owner}/{self.repo}/milestones",
            "-f", f"title={title}",
            "-f", "state=open"
        ], check=False)

    def create_issue(self, title: str, body: str, labels: List[str],
                     milestone: str = "", parent_id: str = "") -> Optional[int]:
        """Issueを作成（冪等性: 同名Issueが存在すればスキップ）"""
        # 冪等性チェック: 同名Issueが既に存在するか確認
        existing = self.find_existing_issue(title)
        if existing:
            print(f"[Skip] 既存Issue使用: #{existing} {title}")
            return existing

        args = [
            "issue", "create",
            "--repo", f"{self.owner}/{self.repo}",
            "--title", title,
            "--body", body,
        ]

        if labels:
            for label in labels:
                args.extend(["--label", label])

        if milestone:
            args.extend(["--milestone", milestone])

        if self.dry_run:
            print(f"[Dry-run] Issue作成: {title}")
            return None

        result = self.run_gh(args)
        if result:
            # URLからIssue番号を抽出
            import re
            match = re.search(r'/issues/(\d+)', result)
            if match:
                return int(match.group(1))

        return None

    def add_to_project(self, issue_number: int):
        """IssueをProjectに追加"""
        if not self.project_id:
            return None

        result = self.run_gh([
            "project", "item-add", str(self.project_number),
            "--owner", self.owner,
            "--url", f"https://github.com/{self.owner}/{self.repo}/issues/{issue_number}"
        ])

        # item-id を取得するには別途クエリが必要
        return None

    def update_project_fields(self, item_id: str, start_date: str,
                               end_date: str, estimate: int):
        """Projectフィールドを更新"""
        if not self.project_id or not item_id:
            return

        # Start Date
        start_field = self.field_ids.get(self.field_names['start_date'])
        if start_field and start_date:
            self.run_gh([
                "project", "item-edit",
                "--project-id", self.project_id,
                "--id", item_id,
                "--field-id", start_field,
                "--date", start_date
            ])

        # End Date
        end_field = self.field_ids.get(self.field_names['end_date'])
        if end_field and end_date:
            self.run_gh([
                "project", "item-edit",
                "--project-id", self.project_id,
                "--id", item_id,
                "--field-id", end_field,
                "--date", end_date
            ])

        # Estimate Hours
        estimate_field = self.field_ids.get(self.field_names['estimate'])
        if estimate_field and estimate:
            self.run_gh([
                "project", "item-edit",
                "--project-id", self.project_id,
                "--id", item_id,
                "--field-id", estimate_field,
                "--number", str(estimate)
            ])

    def sync_issues(self, issues_data: List[Dict[str, Any]]) -> SyncResult:
        """Issue一覧を同期"""
        errors = []
        created = 0
        updated = 0
        skipped = 0

        # 既存Issue取得（冪等性確保）
        self.fetch_existing_issues()

        # ラベル確保
        all_labels = set()
        for issue in issues_data:
            all_labels.update(issue.get('labels', []))
        self.ensure_labels(list(all_labels))

        # Issue作成
        for issue in issues_data:
            try:
                # 依存関係をbodyに追加
                body = issue.get('body', '')
                if issue.get('depends_on'):
                    body += f"\n\n## 依存関係\n"
                    for dep in issue['depends_on']:
                        if dep in self.created_issues:
                            body += f"- **Depends on**: #{self.created_issues[dep]}\n"

                issue_number = self.create_issue(
                    title=issue['title'],
                    body=body,
                    labels=issue.get('labels', []),
                    milestone=issue.get('milestone', ''),
                )

                if issue_number:
                    self.created_issues[issue['id']] = issue_number
                    # 既存IssueでなければProjectに追加
                    if issue['title'] not in self.existing_issues:
                        self.add_to_project(issue_number)
                        created += 1
                        print(f"  ✅ #{issue_number}: {issue['title'][:40]}")
                    else:
                        skipped += 1

            except Exception as e:
                errors.append(f"Issue作成失敗 {issue['id']}: {e}")

        print(f"  📊 結果: 作成={created}, スキップ={skipped}, エラー={len(errors)}")

        return SyncResult(
            success=len(errors) == 0,
            issues_created=created,
            issues_updated=updated,
            errors=errors
        )

    def sync_all(self) -> Dict[str, Any]:
        """全データを同期"""
        print("🔄 GitHub同期開始")

        # プロジェクト情報取得
        self.fetch_project_info()

        # 同期実行（issues_dataは外部から渡される想定）
        # ここでは空のデータで結果を返す
        return {
            "success": True,
            "issues_created": 0,
            "issues_updated": 0,
            "errors": [],
            "message": "同期データが必要です。--issues オプションでJSONを指定してください。"
        }

    def sync_from_file(self, issues_file: Path) -> Dict[str, Any]:
        """ファイルからデータを読み込んで同期"""
        with open(issues_file, 'r', encoding='utf-8') as f:
            issues_data = json.load(f)

        print(f"📂 {len(issues_data)}件のIssueを同期")

        # プロジェクト情報取得
        self.fetch_project_info()

        # 同期実行
        result = self.sync_issues(issues_data)

        return {
            "success": result.success,
            "issues_created": result.issues_created,
            "issues_updated": result.issues_updated,
            "errors": result.errors,
        }


def main():
    parser = argparse.ArgumentParser(description="GitHub同期ツール")
    parser.add_argument('--config', '-c', required=True, help='設定ファイルパス')
    parser.add_argument('--issues', '-i', help='Issues JSONファイルパス')
    parser.add_argument('--sync', action='store_true', help='同期を実行')
    parser.add_argument('--dry-run', '-n', action='store_true', help='ドライラン')

    args = parser.parse_args()

    # 設定読み込み
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    sync = GitHubSync(config, dry_run=args.dry_run)

    if args.sync:
        if args.issues:
            result = sync.sync_from_file(Path(args.issues))
        else:
            result = sync.sync_all()

        print(f"\n📊 結果:")
        print(f"  作成: {result['issues_created']}件")
        print(f"  更新: {result['issues_updated']}件")

        if result['errors']:
            print(f"  エラー: {len(result['errors'])}件")
            for error in result['errors']:
                print(f"    - {error}")

        return 0 if result['success'] else 1
    else:
        print("--sync オプションを指定して同期を実行してください")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
