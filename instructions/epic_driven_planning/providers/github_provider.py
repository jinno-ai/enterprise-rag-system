#!/usr/bin/env python3
"""
GitHub Provider - GitHub Projects V2 連携

機能:
- GitHub Issues の作成/更新
- GitHub Projects V2 へのアイテム追加
- カスタムフィールド（Start Date, End Date, Estimate）の更新
- ラベル・マイルストーンの自動作成

必要な認証:
- gh CLI がインストール・認証済みであること
- または GITHUB_TOKEN 環境変数が設定されていること

既知の制限（2026-01時点）:
- GitHub Projects V2 の View（RoadMap, Board, Table）作成APIは存在しない
  - createProjectV2View mutation は未提供
  - 回避策: gh project copy でテンプレートプロジェクトからビュー設定ごとコピー
- カスタムフィールドの作成は可能だが、ビュー設定への追加は手動が必要
"""

import subprocess
import json
import re
import os
from typing import Dict, Any, List, Optional
from .base_provider import (
    BaseProvider, WorkItem, SyncResult, ItemType, ItemStatus
)


class GitHubProvider(BaseProvider):
    """GitHub Projects V2 プロバイダー"""

    @property
    def provider_name(self) -> str:
        return "github"

    def _validate_config(self):
        """設定の検証"""
        github = self.config.get('project', {}).get('github', {})

        if not github.get('owner'):
            raise ValueError("github.owner is required")
        if not github.get('repo'):
            raise ValueError("github.repo is required")

        self.owner = github['owner']
        self.repo = github['repo']
        self.project_number = github.get('project_number', 0)

        # フィールド名設定
        sync_config = self.config.get('github_sync', {})
        self.field_names = sync_config.get('fields', {
            'start_date': 'Start Date',
            'end_date': 'End Date',
            'estimate': 'Estimate Hours',
            'status': 'Status',
        })

        # キャッシュ
        self._project_id: Optional[str] = None
        self._field_ids: Dict[str, str] = {}
        self._created_labels: set = set()
        self._created_milestones: set = set()

    def _run_gh(self, args: List[str], check: bool = True) -> Optional[str]:
        """gh CLIを実行"""
        if self.dry_run:
            self.log(f"gh {' '.join(args)}")
            return None

        cmd = ["gh"] + args
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding='utf-8', errors='replace'
            )

            if check and result.returncode != 0:
                self.log(f"Warning: {result.stderr}")
                return None

            return result.stdout.strip()
        except FileNotFoundError:
            raise RuntimeError("gh CLI is not installed. Please install GitHub CLI.")

    def _run_gh_api(self, endpoint: str, method: str = "GET",
                    data: Optional[Dict] = None) -> Optional[Dict]:
        """gh api コマンドを実行"""
        args = ["api", endpoint, "-X", method]

        if data:
            for key, value in data.items():
                if isinstance(value, bool):
                    args.extend(["-F", f"{key}={str(value).lower()}"])
                elif isinstance(value, (int, float)):
                    args.extend(["-F", f"{key}={value}"])
                else:
                    args.extend(["-f", f"{key}={value}"])

        result = self._run_gh(args, check=False)
        if result:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return None
        return None

    def authenticate(self) -> bool:
        """認証確認"""
        if self.dry_run:
            self.log("Skipping authentication check in dry-run mode")
            return True

        result = self._run_gh(["auth", "status"], check=False)
        if result is None:
            # gh auth status はstderrに出力するため、戻り値なしでもOKの場合がある
            # 実際にAPIを叩いて確認
            test = self._run_gh(["api", "user"], check=False)
            return test is not None
        return True

    def _fetch_project_info(self):
        """プロジェクト情報を取得"""
        if self._project_id:
            return

        if self.project_number <= 0:
            self.log("No project_number configured, skipping project operations")
            return

        # プロジェクトID取得
        query = """
        query($owner: String!, $number: Int!) {
            user(login: $owner) {
                projectV2(number: $number) {
                    id
                    fields(first: 50) {
                        nodes {
                            ... on ProjectV2Field {
                                id
                                name
                            }
                            ... on ProjectV2SingleSelectField {
                                id
                                name
                                options {
                                    id
                                    name
                                }
                            }
                            ... on ProjectV2IterationField {
                                id
                                name
                            }
                        }
                    }
                }
            }
            organization(login: $owner) {
                projectV2(number: $number) {
                    id
                    fields(first: 50) {
                        nodes {
                            ... on ProjectV2Field {
                                id
                                name
                            }
                            ... on ProjectV2SingleSelectField {
                                id
                                name
                                options {
                                    id
                                    name
                                }
                            }
                            ... on ProjectV2IterationField {
                                id
                                name
                            }
                        }
                    }
                }
            }
        }
        """

        if self.dry_run:
            self.log("Would fetch project info via GraphQL")
            return

        # GraphQL実行
        args = [
            "api", "graphql",
            "-f", f"query={query}",
            "-F", f"owner={self.owner}",
            "-F", f"number={self.project_number}"
        ]

        result = self._run_gh(args, check=False)
        if result:
            try:
                data = json.loads(result)

                # ユーザーまたは組織のプロジェクトを取得
                project = None
                if data.get('data', {}).get('user', {}).get('projectV2'):
                    project = data['data']['user']['projectV2']
                elif data.get('data', {}).get('organization', {}).get('projectV2'):
                    project = data['data']['organization']['projectV2']

                if project:
                    self._project_id = project['id']

                    # フィールドIDをキャッシュ
                    for field in project.get('fields', {}).get('nodes', []):
                        if field and 'name' in field:
                            self._field_ids[field['name']] = field['id']

                    self.log(f"Project ID: {self._project_id}")
                    self.log(f"Fields: {list(self._field_ids.keys())}")
                else:
                    self.log("Project not found")

            except json.JSONDecodeError as e:
                self.log(f"Failed to parse project info: {e}")

    def create_item(self, item: WorkItem) -> Optional[str]:
        """Issueを作成"""
        # Issue本文を構築
        body = self._build_issue_body(item)

        args = [
            "issue", "create",
            "--repo", f"{self.owner}/{self.repo}",
            "--title", item.title,
            "--body", body,
        ]

        # ラベル
        for label in item.labels:
            args.extend(["--label", label])

        # マイルストーン
        if item.milestone:
            args.extend(["--milestone", item.milestone])

        # アサイン
        if item.assignee:
            args.extend(["--assignee", item.assignee])

        if self.dry_run:
            self.log(f"Would create issue: {item.title}")
            # dry-runでは仮のIDを返す
            return f"dry-run-{item.id}"

        result = self._run_gh(args)
        if result:
            # URLからIssue番号を抽出
            match = re.search(r'/issues/(\d+)', result)
            if match:
                issue_number = match.group(1)
                self.log(f"Created issue #{issue_number}: {item.title}")
                return issue_number

        return None

    def _build_issue_body(self, item: WorkItem) -> str:
        """Issue本文を構築"""
        sections = []

        # 概要
        sections.append(f"## Overview\n\n{item.description}")

        # 受け入れ条件
        if item.acceptance_criteria:
            ac_list = "\n".join([f"- [ ] {ac}" for ac in item.acceptance_criteria])
            sections.append(f"## Acceptance Criteria\n\n{ac_list}")

        # 見積もり
        if item.estimate_hours > 0:
            sections.append(f"## Estimate\n\n- **Hours**: {item.estimate_hours}h")

        # 依存関係
        if item.depends_on:
            deps = ", ".join([f"`{d}`" for d in item.depends_on])
            sections.append(f"## Dependencies\n\n- **Depends on**: {deps}")

        # メタ情報
        meta = [
            f"- **Internal ID**: `{item.id}`",
            f"- **Type**: {item.item_type.value}",
            f"- **Priority**: {item.priority}",
        ]
        if item.start_date:
            meta.append(f"- **Start Date**: {item.start_date}")
        if item.end_date:
            meta.append(f"- **End Date**: {item.end_date}")

        sections.append(f"## Metadata\n\n" + "\n".join(meta))

        return "\n\n---\n\n".join(sections)

    def update_item(self, item: WorkItem) -> bool:
        """Issueを更新"""
        if not item.external_id:
            return False

        body = self._build_issue_body(item)

        args = [
            "issue", "edit", item.external_id,
            "--repo", f"{self.owner}/{self.repo}",
            "--body", body,
        ]

        if self.dry_run:
            self.log(f"Would update issue #{item.external_id}: {item.title}")
            return True

        result = self._run_gh(args, check=False)
        return result is not None

    def get_item(self, external_id: str) -> Optional[WorkItem]:
        """Issue番号で取得"""
        if self.dry_run:
            return None

        result = self._run_gh([
            "issue", "view", external_id,
            "--repo", f"{self.owner}/{self.repo}",
            "--json", "number,title,body,labels,state"
        ])

        if result:
            try:
                data = json.loads(result)
                return WorkItem(
                    id=f"gh-{data['number']}",
                    title=data['title'],
                    description=data.get('body', ''),
                    item_type=ItemType.STORY,
                    priority="medium",
                    external_id=str(data['number']),
                )
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    def find_item_by_title(self, title: str) -> Optional[WorkItem]:
        """タイトルでIssueを検索"""
        if self.dry_run:
            return None

        # タイトルで検索
        search_query = f'repo:{self.owner}/{self.repo} "{title}" in:title'

        result = self._run_gh([
            "issue", "list",
            "--repo", f"{self.owner}/{self.repo}",
            "--search", f'"{title}" in:title',
            "--json", "number,title",
            "--limit", "5"
        ])

        if result:
            try:
                issues = json.loads(result)
                for issue in issues:
                    if issue['title'] == title:
                        return WorkItem(
                            id=f"gh-{issue['number']}",
                            title=issue['title'],
                            description="",
                            item_type=ItemType.STORY,
                            priority="medium",
                            external_id=str(issue['number']),
                        )
            except json.JSONDecodeError:
                pass

        return None

    def create_label(self, name: str, color: str = "0366d6") -> bool:
        """ラベルを作成"""
        if name in self._created_labels:
            return True

        if self.dry_run:
            self.log(f"Would create label: {name}")
            self._created_labels.add(name)
            return True

        # 既存チェック & 作成
        result = self._run_gh([
            "label", "create", name,
            "--repo", f"{self.owner}/{self.repo}",
            "--color", color,
            "--force"
        ], check=False)

        self._created_labels.add(name)
        return True

    def create_milestone(self, name: str, due_date: Optional[str] = None) -> bool:
        """マイルストーンを作成"""
        if name in self._created_milestones:
            return True

        if self.dry_run:
            self.log(f"Would create milestone: {name}")
            self._created_milestones.add(name)
            return True

        data = {
            "title": name,
            "state": "open"
        }
        if due_date:
            data["due_on"] = f"{due_date}T00:00:00Z"

        result = self._run_gh_api(
            f"repos/{self.owner}/{self.repo}/milestones",
            method="POST",
            data=data
        )

        self._created_milestones.add(name)
        return result is not None

    def add_to_project(self, external_id: str) -> Optional[str]:
        """IssueをProjectに追加"""
        self._fetch_project_info()

        if not self._project_id:
            return None

        if self.dry_run:
            self.log(f"Would add issue #{external_id} to project")
            return f"dry-run-item-{external_id}"

        # Issue URLを取得
        issue_url = f"https://github.com/{self.owner}/{self.repo}/issues/{external_id}"

        # GraphQL mutation
        mutation = """
        mutation($projectId: ID!, $contentId: ID!) {
            addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
                item {
                    id
                }
            }
        }
        """

        # まずIssueのnode_idを取得
        issue_data = self._run_gh([
            "issue", "view", external_id,
            "--repo", f"{self.owner}/{self.repo}",
            "--json", "id"
        ])

        if not issue_data:
            return None

        try:
            issue_info = json.loads(issue_data)
            content_id = issue_info['id']
        except (json.JSONDecodeError, KeyError):
            return None

        # プロジェクトに追加
        args = [
            "api", "graphql",
            "-f", f"query={mutation}",
            "-f", f"projectId={self._project_id}",
            "-f", f"contentId={content_id}"
        ]

        result = self._run_gh(args, check=False)
        if result:
            try:
                data = json.loads(result)
                item_id = data.get('data', {}).get('addProjectV2ItemById', {}).get('item', {}).get('id')
                if item_id:
                    self.log(f"Added issue #{external_id} to project: {item_id}")
                    return item_id
            except json.JSONDecodeError:
                pass

        return None

    def update_project_fields(
        self,
        project_item_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        estimate: Optional[int] = None,
        status: Optional[ItemStatus] = None
    ) -> bool:
        """Projectフィールドを更新"""
        self._fetch_project_info()

        if not self._project_id:
            return False

        success = True

        # Start Date
        if start_date:
            field_id = self._field_ids.get(self.field_names.get('start_date', 'Start Date'))
            if field_id:
                success &= self._update_date_field(project_item_id, field_id, start_date)

        # End Date
        if end_date:
            field_id = self._field_ids.get(self.field_names.get('end_date', 'End Date'))
            if field_id:
                success &= self._update_date_field(project_item_id, field_id, end_date)

        # Estimate
        if estimate is not None:
            field_id = self._field_ids.get(self.field_names.get('estimate', 'Estimate Hours'))
            if field_id:
                success &= self._update_number_field(project_item_id, field_id, estimate)

        return success

    def _update_date_field(self, item_id: str, field_id: str, value: str) -> bool:
        """日付フィールドを更新"""
        if self.dry_run:
            self.log(f"Would update date field {field_id} to {value}")
            return True

        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: Date!) {
            updateProjectV2ItemFieldValue(input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: {date: $value}
            }) {
                projectV2Item {
                    id
                }
            }
        }
        """

        args = [
            "api", "graphql",
            "-f", f"query={mutation}",
            "-f", f"projectId={self._project_id}",
            "-f", f"itemId={item_id}",
            "-f", f"fieldId={field_id}",
            "-f", f"value={value}"
        ]

        result = self._run_gh(args, check=False)
        return result is not None

    def _update_number_field(self, item_id: str, field_id: str, value: int) -> bool:
        """数値フィールドを更新"""
        if self.dry_run:
            self.log(f"Would update number field {field_id} to {value}")
            return True

        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: Float!) {
            updateProjectV2ItemFieldValue(input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: {number: $value}
            }) {
                projectV2Item {
                    id
                }
            }
        }
        """

        args = [
            "api", "graphql",
            "-f", f"query={mutation}",
            "-f", f"projectId={self._project_id}",
            "-f", f"itemId={item_id}",
            "-f", f"fieldId={field_id}",
            "-F", f"value={value}"
        ]

        result = self._run_gh(args, check=False)
        return result is not None
