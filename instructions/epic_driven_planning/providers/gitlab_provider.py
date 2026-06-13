#!/usr/bin/env python3
"""
GitLab Provider - GitLab Issues/Epics/Boards 連携

機能:
- GitLab Issues の作成/更新
- GitLab Epics の作成（Premiumのみ）
- ラベル・マイルストーンの自動作成
- Issue リレーション（親子関係）
- Time Estimate の設定

必要な認証:
- GITLAB_TOKEN 環境変数（推奨）
- または config の gitlab.token
- glab CLI がインストールされている場合は代替として使用可能

API参考:
- https://docs.gitlab.com/ee/api/issues.html
- https://docs.gitlab.com/ee/api/epics.html
- https://docs.gitlab.com/ee/api/labels.html
- https://docs.gitlab.com/ee/api/milestones.html
"""

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Any, List, Optional

from .base_provider import (
    BaseProvider, WorkItem, SyncResult, ItemType, ItemStatus
)


class GitLabProvider(BaseProvider):
    """GitLab プロバイダー - Issues/Epics/Boards 連携"""

    # GitLabのItem Typeマッピング（Issueのラベルで表現）
    DEFAULT_TYPE_LABELS = {
        ItemType.EPIC: "Epic",
        ItemType.FEATURE: "Feature",
        ItemType.STORY: "Story",
        ItemType.TASK: "Task",
        ItemType.BUG: "Bug",
    }

    # GitLabのステータスマッピング（Issueラベル or Epic state）
    DEFAULT_STATUS_LABELS = {
        ItemStatus.BACKLOG: "Backlog",
        ItemStatus.TODO: "To Do",
        ItemStatus.IN_PROGRESS: "Doing",
        ItemStatus.IN_REVIEW: "In Review",
        ItemStatus.DONE: "Done",
        ItemStatus.CLOSED: "Closed",
    }

    # GitLabのpriorityラベルマッピング
    DEFAULT_PRIORITY_LABELS = {
        "high": "priority::high",
        "medium": "priority::medium",
        "low": "priority::low",
    }

    @property
    def provider_name(self) -> str:
        return "gitlab"

    def _validate_config(self):
        """設定の検証"""
        gitlab = self.config.get('project', {}).get('gitlab', {})

        self.host = gitlab.get('host', 'https://gitlab.com')
        self.project_id = gitlab.get('project_id', '')
        self.group_id = gitlab.get('group_id', '')  # Epic用（Premium）
        self.token = gitlab.get('token') or os.environ.get('GITLAB_TOKEN', '')
        self.api_version = gitlab.get('api_version', 'v4')

        # 同期設定
        sync_cfg = self.config.get('gitlab_sync', {})
        self.type_labels = dict(self.DEFAULT_TYPE_LABELS)
        self.type_labels.update(sync_cfg.get('type_labels', {}))

        self.status_labels = dict(self.DEFAULT_STATUS_LABELS)
        self.status_labels.update(sync_cfg.get('status_labels', {}))

        self.priority_labels = dict(self.DEFAULT_PRIORITY_LABELS)
        self.priority_labels.update(sync_cfg.get('priority_labels', {}))

        # 機能フラグ
        self.enable_epics = bool(sync_cfg.get('enable_epics', False))  # Premium機能
        self.enable_time_tracking = bool(sync_cfg.get('enable_time_tracking', True))
        self.enable_due_date = bool(sync_cfg.get('enable_due_date', True))
        self.enable_weight = bool(sync_cfg.get('enable_weight', False))  # Premium機能
        self.use_scoped_labels = bool(sync_cfg.get('use_scoped_labels', True))  # :: 形式
        self.enable_milestones = bool(sync_cfg.get('enable_milestones', True))  # マイルストーン

        # キャッシュ
        self._created_labels: set = set()
        self._milestone_cache: Dict[str, int] = {}  # name -> id マッピング

        if not self.project_id:
            self.log("Warning: gitlab.project_id is not configured")

    @property
    def base_url(self) -> str:
        """API ベースURL"""
        return f"{self.host}/api/{self.api_version}"

    @property
    def project_url(self) -> str:
        """プロジェクトAPI URL"""
        encoded_id = urllib.parse.quote(str(self.project_id), safe='')
        return f"{self.base_url}/projects/{encoded_id}"

    @property
    def group_url(self) -> str:
        """グループAPI URL（Epic用）"""
        encoded_id = urllib.parse.quote(str(self.group_id), safe='')
        return f"{self.base_url}/groups/{encoded_id}"

    def _request_json(
        self,
        method: str,
        url: str,
        body: Optional[Any] = None,
        content_type: str = "application/json",
    ) -> Optional[Dict[str, Any]]:
        """HTTP リクエストを実行してJSONを返す"""
        if self.dry_run:
            self.log(f"{method} {url}")
            if body:
                self.log(f"  Body: {json.dumps(body, ensure_ascii=False)[:200]}...")
            return {}

        headers = {
            "Accept": "application/json",
            "Content-Type": content_type,
        }
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token

        data = None
        if body is not None:
            if isinstance(body, (str, bytes)):
                data = body if isinstance(body, bytes) else body.encode("utf-8")
            else:
                data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                payload = resp.read()
                if not payload:
                    return {}
                return json.loads(payload.decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self.log(f"HTTP {e.code} for {url}: {error_body}")
            return None
        except urllib.error.URLError as e:
            self.log(f"Network error for {url}: {e}")
            return None

    def _run_glab(self, args: List[str], check: bool = True) -> Optional[str]:
        """glab CLIを実行（フォールバック用）"""
        if self.dry_run:
            self.log(f"glab {' '.join(args)}")
            return None

        cmd = ["glab"] + args
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
            return None

    def authenticate(self) -> bool:
        """認証確認"""
        if self.dry_run:
            self.log("Skipping authentication check in dry-run mode")
            return True

        if not self.token:
            # glab CLIでフォールバック
            result = self._run_glab(["auth", "status"], check=False)
            if result is None:
                self.log("GITLAB_TOKEN is not set and glab CLI is not authenticated")
                return False
            return True

        # APIで認証確認
        url = f"{self.base_url}/user"
        result = self._request_json("GET", url)
        if result and "id" in result:
            self.log(f"Authenticated as: {result.get('username', 'unknown')}")
            return True

        self.log("Authentication failed")
        return False

    def _build_labels(self, item: WorkItem) -> List[str]:
        """WorkItemからラベルリストを構築"""
        labels = list(item.labels)

        # タイプラベル追加
        type_label = self.type_labels.get(item.item_type)
        if type_label and type_label not in labels:
            labels.append(type_label)

        # 優先度ラベル追加
        priority_label = self.priority_labels.get(item.priority)
        if priority_label and priority_label not in labels:
            labels.append(priority_label)

        return labels

    def _build_description(self, item: WorkItem) -> str:
        """WorkItemから説明文を構築"""
        parts = []

        if item.description:
            parts.append(item.description)

        if item.acceptance_criteria:
            parts.append("\n## Acceptance Criteria\n")
            for ac in item.acceptance_criteria:
                parts.append(f"- [ ] {ac}")

        if item.depends_on:
            parts.append("\n## Dependencies\n")
            for dep in item.depends_on:
                parts.append(f"- {dep}")

        if item.unified_key:
            parts.append(f"\n---\n_Unified Key: `{item.unified_key}`_")

        return "\n".join(parts)

    def _estimate_to_seconds(self, hours: int) -> int:
        """時間見積もりを秒に変換（GitLab形式）"""
        return hours * 3600

    def _estimate_to_duration(self, hours: int) -> str:
        """時間見積もりをGitLab duration形式に変換"""
        if hours >= 8:
            days = hours // 8
            remaining_hours = hours % 8
            if remaining_hours:
                return f"{days}d {remaining_hours}h"
            return f"{days}d"
        return f"{hours}h"

    def create_item(self, item: WorkItem) -> Optional[str]:
        """Issueを作成"""
        # Epic の場合は別処理（Premium機能）
        if item.item_type == ItemType.EPIC and self.enable_epics and self.group_id:
            return self._create_epic(item)

        labels = self._build_labels(item)
        description = self._build_description(item)

        body: Dict[str, Any] = {
            "title": item.title,
            "description": description,
        }

        if labels:
            body["labels"] = ",".join(labels)

        if item.assignee:
            # assignee_ids が必要だが、ユーザー名からID解決が必要
            # 一旦スキップ（将来: ユーザー検索API）
            pass

        # マイルストーン設定
        if self.enable_milestones and item.milestone:
            milestone_id = self._milestone_cache.get(item.milestone)
            if milestone_id:
                body["milestone_id"] = milestone_id

        if self.enable_due_date and item.end_date:
            body["due_date"] = item.end_date

        if self.enable_weight and item.estimate_hours:
            # weight はStory Points的な意味（1-10程度）
            # estimate_hoursから簡易変換
            body["weight"] = min(10, max(1, item.estimate_hours // 4))

        url = f"{self.project_url}/issues"
        result = self._request_json("POST", url, body)

        if result and "iid" in result:
            issue_iid = str(result["iid"])

            # Time tracking を設定
            if self.enable_time_tracking and item.estimate_hours > 0:
                self._set_time_estimate(issue_iid, item.estimate_hours)

            return issue_iid

        return None

    def _create_epic(self, item: WorkItem) -> Optional[str]:
        """Epicを作成（Premium機能）"""
        if not self.group_id:
            self.log("Warning: group_id is required for Epics")
            return None

        description = self._build_description(item)

        body: Dict[str, Any] = {
            "title": item.title,
            "description": description,
        }

        if self.enable_due_date:
            if item.start_date:
                body["start_date_fixed"] = item.start_date
            if item.end_date:
                body["due_date_fixed"] = item.end_date

        url = f"{self.group_url}/epics"
        result = self._request_json("POST", url, body)

        if result and "iid" in result:
            return f"epic:{result['iid']}"

        return None

    def _set_time_estimate(self, issue_iid: str, hours: int) -> bool:
        """Time Estimateを設定"""
        duration = self._estimate_to_duration(hours)
        url = f"{self.project_url}/issues/{issue_iid}/time_estimate"
        body = {"duration": duration}
        result = self._request_json("POST", url, body)
        return result is not None

    def update_item(self, item: WorkItem) -> bool:
        """Issueを更新"""
        if not item.external_id:
            return False

        # Epic の場合
        if item.external_id.startswith("epic:"):
            return self._update_epic(item)

        labels = self._build_labels(item)
        description = self._build_description(item)

        body: Dict[str, Any] = {
            "title": item.title,
            "description": description,
        }

        if labels:
            body["labels"] = ",".join(labels)

        # マイルストーン設定
        if self.enable_milestones and item.milestone:
            milestone_id = self._milestone_cache.get(item.milestone)
            if milestone_id:
                body["milestone_id"] = milestone_id

        if self.enable_due_date and item.end_date:
            body["due_date"] = item.end_date

        url = f"{self.project_url}/issues/{item.external_id}"
        result = self._request_json("PUT", url, body)

        if result is not None:
            # Time tracking を更新
            if self.enable_time_tracking and item.estimate_hours > 0:
                self._set_time_estimate(item.external_id, item.estimate_hours)
            return True

        return False

    def _update_epic(self, item: WorkItem) -> bool:
        """Epicを更新（Premium機能）"""
        if not self.group_id or not item.external_id:
            return False

        epic_iid = item.external_id.replace("epic:", "")
        description = self._build_description(item)

        body: Dict[str, Any] = {
            "title": item.title,
            "description": description,
        }

        if self.enable_due_date:
            if item.start_date:
                body["start_date_fixed"] = item.start_date
            if item.end_date:
                body["due_date_fixed"] = item.end_date

        url = f"{self.group_url}/epics/{epic_iid}"
        result = self._request_json("PUT", url, body)
        return result is not None

    def get_item(self, external_id: str) -> Optional[WorkItem]:
        """Issue IDで取得"""
        if external_id.startswith("epic:"):
            return self._get_epic(external_id)

        url = f"{self.project_url}/issues/{external_id}"
        result = self._request_json("GET", url)

        if not result:
            return None

        return self._parse_issue(result)

    def _get_epic(self, external_id: str) -> Optional[WorkItem]:
        """Epic IDで取得"""
        if not self.group_id:
            return None

        epic_iid = external_id.replace("epic:", "")
        url = f"{self.group_url}/epics/{epic_iid}"
        result = self._request_json("GET", url)

        if not result:
            return None

        return WorkItem(
            id=external_id,
            title=result.get("title", ""),
            description=result.get("description", ""),
            item_type=ItemType.EPIC,
            priority="medium",
            external_id=external_id,
            start_date=result.get("start_date"),
            end_date=result.get("due_date"),
        )

    def _parse_issue(self, data: Dict[str, Any]) -> WorkItem:
        """API レスポンスからWorkItemを生成"""
        labels = data.get("labels", [])

        # タイプを推定
        item_type = ItemType.STORY
        for itype, label in self.type_labels.items():
            if label in labels:
                item_type = itype
                break

        # 優先度を推定
        priority = "medium"
        for prio, label in self.priority_labels.items():
            if label in labels:
                priority = prio
                break

        # ステータスを推定
        status = ItemStatus.BACKLOG
        state = data.get("state", "opened")
        if state == "closed":
            status = ItemStatus.CLOSED
        else:
            for stat, label in self.status_labels.items():
                if label in labels:
                    status = stat
                    break

        # 見積もり時間
        estimate_hours = 0
        time_stats = data.get("time_stats", {})
        if time_stats.get("time_estimate"):
            estimate_hours = time_stats["time_estimate"] // 3600

        return WorkItem(
            id=str(data.get("iid", "")),
            title=data.get("title", ""),
            description=data.get("description", ""),
            item_type=item_type,
            priority=priority,
            estimate_hours=estimate_hours,
            status=status,
            external_id=str(data.get("iid", "")),
            external_url=data.get("web_url"),
            labels=[l for l in labels if l not in self.type_labels.values()
                    and l not in self.priority_labels.values()
                    and l not in self.status_labels.values()],
            end_date=data.get("due_date"),
        )

    def find_item_by_title(self, title: str) -> Optional[WorkItem]:
        """タイトルでIssueを検索"""
        # URL エンコード
        encoded_title = urllib.parse.quote(title)
        url = f"{self.project_url}/issues?search={encoded_title}&in=title"
        result = self._request_json("GET", url)

        if not result:
            return None

        # リスト形式で返ってくる
        if isinstance(result, list) and len(result) > 0:
            # タイトル完全一致を優先
            for issue in result:
                if issue.get("title") == title:
                    return self._parse_issue(issue)
            # 部分一致の最初のものを返す
            return self._parse_issue(result[0])

        return None

    def create_label(self, name: str, color: str = "#428BCA") -> bool:
        """ラベルを作成"""
        if name in self._created_labels:
            return True

        # 色の形式を調整（# を除去）
        color_code = color.lstrip('#')

        body = {
            "name": name,
            "color": f"#{color_code}",
        }

        url = f"{self.project_url}/labels"
        result = self._request_json("POST", url, body)

        if result is not None:
            self._created_labels.add(name)
            return True

        # 既存ラベルの場合もTrueを返す
        if result is None:
            self._created_labels.add(name)
            return True

        return False

    def create_milestone(self, name: str, description: str = "", start_date: Optional[str] = None, due_date: Optional[str] = None) -> Optional[int]:
        """マイルストーンを作成し、IDを返す"""
        # キャッシュチェック
        if name in self._milestone_cache:
            return self._milestone_cache[name]

        # まず既存を検索
        existing_id = self._find_milestone_by_title(name)
        if existing_id:
            self._milestone_cache[name] = existing_id
            return existing_id

        body: Dict[str, Any] = {
            "title": name,
        }

        if description:
            body["description"] = description
        if start_date:
            body["start_date"] = start_date
        if due_date:
            body["due_date"] = due_date

        url = f"{self.project_url}/milestones"
        result = self._request_json("POST", url, body)

        if result and "id" in result:
            milestone_id = result["id"]
            self._milestone_cache[name] = milestone_id
            self.log(f"Created milestone: {name} (ID: {milestone_id})")
            return milestone_id

        # 作成失敗（409などで既存の場合は再検索）
        existing_id = self._find_milestone_by_title(name)
        if existing_id:
            self._milestone_cache[name] = existing_id
            return existing_id

        return None

    def _find_milestone_by_title(self, title: str) -> Optional[int]:
        """タイトルでマイルストーンを検索"""
        url = f"{self.project_url}/milestones?search={urllib.parse.quote(title)}"
        result = self._request_json("GET", url)

        if result and isinstance(result, list):
            for ms in result:
                if ms.get("title") == title:
                    return ms.get("id")
        return None

    def get_or_create_milestone(self, name: str, description: str = "", start_date: Optional[str] = None, due_date: Optional[str] = None) -> Optional[int]:
        """マイルストーンを取得または作成"""
        return self.create_milestone(name, description, start_date, due_date)

    def add_to_project(self, external_id: str) -> Optional[str]:
        """IssueをBoardに追加（GitLabでは自動なのでIDをそのまま返す）"""
        # GitLab では Issue は自動的に Board に表示される
        return external_id

    def update_project_fields(
        self,
        project_item_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        estimate: Optional[int] = None,
        status: Optional[ItemStatus] = None
    ) -> bool:
        """プロジェクトフィールドを更新"""
        if project_item_id.startswith("epic:"):
            # Epic の日付更新
            return self._update_epic_dates(project_item_id, start_date, end_date)

        body: Dict[str, Any] = {}

        if self.enable_due_date and end_date:
            body["due_date"] = end_date

        if status:
            status_label = self.status_labels.get(status)
            if status_label:
                body["add_labels"] = status_label
                # 他のステータスラベルを削除
                other_status_labels = [
                    l for s, l in self.status_labels.items() if s != status
                ]
                if other_status_labels:
                    body["remove_labels"] = ",".join(other_status_labels)

        if body:
            url = f"{self.project_url}/issues/{project_item_id}"
            result = self._request_json("PUT", url, body)
            if result is None:
                return False

        # Time tracking
        if self.enable_time_tracking and estimate and estimate > 0:
            self._set_time_estimate(project_item_id, estimate)

        return True

    def _update_epic_dates(
        self,
        external_id: str,
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> bool:
        """Epicの日付を更新"""
        if not self.group_id:
            return False

        epic_iid = external_id.replace("epic:", "")
        body: Dict[str, Any] = {}

        if start_date:
            body["start_date_fixed"] = start_date
        if end_date:
            body["due_date_fixed"] = end_date

        if not body:
            return True

        url = f"{self.group_url}/epics/{epic_iid}"
        result = self._request_json("PUT", url, body)
        return result is not None

    def set_parent_child_relation(self, child_id: str, parent_id: str) -> bool:
        """親子関係を設定（Issue links または Epic-Issue関係）"""
        # Epic -> Issue の関係（Premium機能）
        if parent_id.startswith("epic:") and not child_id.startswith("epic:"):
            return self._link_issue_to_epic(child_id, parent_id)

        # Issue -> Issue の関係（related として設定）
        return self._create_issue_link(child_id, parent_id, "relates_to")

    def _link_issue_to_epic(self, issue_iid: str, epic_external_id: str) -> bool:
        """IssueをEpicにリンク（Premium機能）"""
        if not self.group_id:
            return False

        epic_iid = epic_external_id.replace("epic:", "")

        body = {
            "issue_id": f"{self.project_id}#{issue_iid}"
        }

        url = f"{self.group_url}/epics/{epic_iid}/issues"
        result = self._request_json("POST", url, body)
        return result is not None

    def _create_issue_link(
        self,
        source_iid: str,
        target_iid: str,
        link_type: str = "relates_to"
    ) -> bool:
        """Issue間のリンクを作成"""
        body = {
            "target_project_id": self.project_id,
            "target_issue_iid": target_iid,
            "link_type": link_type,  # relates_to, blocks, is_blocked_by
        }

        url = f"{self.project_url}/issues/{source_iid}/links"
        result = self._request_json("POST", url, body)
        return result is not None

    def close_item(self, external_id: str) -> bool:
        """Issueをクローズ"""
        if external_id.startswith("epic:"):
            return self._close_epic(external_id)

        body = {"state_event": "close"}
        url = f"{self.project_url}/issues/{external_id}"
        result = self._request_json("PUT", url, body)
        return result is not None

    def _close_epic(self, external_id: str) -> bool:
        """Epicをクローズ"""
        if not self.group_id:
            return False

        epic_iid = external_id.replace("epic:", "")
        body = {"state_event": "close"}
        url = f"{self.group_url}/epics/{epic_iid}"
        result = self._request_json("PUT", url, body)
        return result is not None

    def sync_items(self, items: List[WorkItem]) -> SyncResult:
        """複数の作業項目を同期"""
        result = SyncResult(success=True)

        # 認証
        if not self.authenticate():
            result.add_error("Authentication failed")
            return result

        # ラベル作成
        all_labels = set()
        for item in items:
            all_labels.update(self._build_labels(item))
        for label in all_labels:
            self.create_label(label)

        # マイルストーン作成（日付情報も含める）
        if self.enable_milestones:
            milestone_items = [item for item in items if item.milestone]
            milestone_map: Dict[str, Dict[str, Optional[str]]] = {}

            for item in milestone_items:
                ms = item.milestone
                if ms not in milestone_map:
                    milestone_map[ms] = {"start_date": None, "end_date": None}

                # 最も早い開始日と最も遅い終了日を取得
                if item.start_date:
                    current_start = milestone_map[ms]["start_date"]
                    if not current_start or item.start_date < current_start:
                        milestone_map[ms]["start_date"] = item.start_date

                if item.end_date:
                    current_end = milestone_map[ms]["end_date"]
                    if not current_end or item.end_date > current_end:
                        milestone_map[ms]["end_date"] = item.end_date

            for ms_name, dates in milestone_map.items():
                self.create_milestone(
                    ms_name,
                    description=f"Milestone: {ms_name}",
                    start_date=dates["start_date"],
                    due_date=dates["end_date"]
                )

        # ID マッピング（内部ID -> GitLab IID）
        id_mapping: Dict[str, str] = {}

        def register_mapping(item: WorkItem, external_id: str) -> None:
            id_mapping[item.id] = external_id
            if item.unified_key:
                id_mapping[item.unified_key] = external_id

        # 項目を同期（親から順に処理するためソート）
        sorted_items = sorted(items, key=lambda x: (
            0 if x.item_type == ItemType.EPIC else
            1 if x.item_type == ItemType.FEATURE else
            2 if x.item_type == ItemType.STORY else 3
        ))

        for item in sorted_items:
            try:
                # 既存項目を検索
                existing = self.find_item_by_title(item.title)

                if existing and existing.external_id:
                    # 更新
                    item.external_id = existing.external_id
                    if self.update_item(item):
                        result.updated += 1
                        register_mapping(item, existing.external_id)
                        self.update_project_fields(
                            existing.external_id,
                            start_date=item.start_date,
                            end_date=item.end_date,
                            estimate=item.estimate_hours,
                            status=item.status,
                        )
                        result.items.append({
                            "id": item.id,
                            "unified_key": item.unified_key,
                            "external_id": existing.external_id,
                            "action": "updated",
                        })
                    else:
                        result.add_warning(f"Update failed: {item.effective_key}")
                else:
                    # 新規作成
                    external_id = self.create_item(item)
                    if external_id:
                        result.created += 1
                        register_mapping(item, external_id)
                        item.external_id = external_id

                        # プロジェクトフィールド更新
                        project_item_id = self.add_to_project(external_id)
                        if project_item_id:
                            self.update_project_fields(
                                project_item_id,
                                start_date=item.start_date,
                                end_date=item.end_date,
                                estimate=item.estimate_hours,
                                status=item.status,
                            )

                        result.items.append({
                            "id": item.id,
                            "unified_key": item.unified_key,
                            "external_id": external_id,
                            "action": "created",
                        })
                    else:
                        result.add_error(f"Create failed: {item.effective_key}")

            except Exception as e:
                result.add_error(f"Error processing {item.effective_key}: {str(e)}")

        # 親子関係を設定（2パス目）
        for item in items:
            if not item.parent_id:
                continue

            child_id = id_mapping.get(item.unified_key or item.id)
            parent_id = id_mapping.get(item.parent_id)

            if child_id and parent_id and child_id != parent_id:
                if not self.set_parent_child_relation(child_id, parent_id):
                    result.add_warning(
                        f"Failed to set parent relation: {item.effective_key} -> {item.parent_id}"
                    )

        return result
