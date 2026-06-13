#!/usr/bin/env python3
"""
Azure DevOps Provider - Work Items integration

Auth (優先順位):
1. az CLI ログイン状態（推奨、PATなしで動作）
2. AZURE_DEVOPS_PAT env var
3. project.azure_devops.pat in config

Note: Basic プロセステンプレートでは Epic/Feature/User Story が
使用不可。Issue/Task のみサポート。Agile/Scrum/CMMIプロセスを推奨。
"""

import base64
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


class AzureDevOpsProvider(BaseProvider):
    """Azure DevOps provider using REST API or az CLI."""

    # Basic プロセス用のマッピング（Epic/Feature/User Story 非対応）
    BASIC_PROCESS_TYPES = {
        ItemType.EPIC: "Epic",      # Basic では Epic が存在しない
        ItemType.FEATURE: "Issue",  # Feature → Issue
        ItemType.STORY: "Issue",    # User Story → Issue
        ItemType.TASK: "Task",
        ItemType.BUG: "Issue",      # Bug → Issue
    }

    DEFAULT_WORK_ITEM_TYPES = {
        ItemType.EPIC: "Epic",
        ItemType.FEATURE: "Feature",
        ItemType.STORY: "User Story",
        ItemType.TASK: "Task",
        ItemType.BUG: "Bug",
    }

    DEFAULT_STATES = {
        ItemStatus.BACKLOG: "New",
        ItemStatus.TODO: "New",
        ItemStatus.IN_PROGRESS: "Active",
        ItemStatus.IN_REVIEW: "Active",
        ItemStatus.DONE: "Closed",
        ItemStatus.CLOSED: "Closed",
    }

    DEFAULT_FIELDS = {
        "title": "System.Title",
        "description": "System.Description",
        "tags": "System.Tags",
        "area_path": "System.AreaPath",
        "iteration_path": "System.IterationPath",
        "priority": "Microsoft.VSTS.Common.Priority",
        "start_date": "Microsoft.VSTS.Scheduling.StartDate",
        "target_date": "Microsoft.VSTS.Scheduling.TargetDate",
        "estimate": "Microsoft.VSTS.Scheduling.Effort",
        "story_points": "Microsoft.VSTS.Scheduling.StoryPoints",
        "original_estimate": "Microsoft.VSTS.Scheduling.OriginalEstimate",
        "state": "System.State",
    }

    @property
    def provider_name(self) -> str:
        return "azure_devops"

    def _validate_config(self):
        ado = self.config.get("project", {}).get("azure_devops", {})

        self.organization = ado.get("organization", "")
        self.project = ado.get("project", "")
        self.team = ado.get("team", "")
        self.area_path = ado.get("area_path") or self.project
        self.iteration_path = ado.get("iteration_path") or self.project
        self.pat = ado.get("pat") or os.environ.get("AZURE_DEVOPS_PAT", "")
        self.api_version = ado.get("api_version", "7.0")

        sync_cfg = self.config.get("ado_sync", {})
        self.work_item_types = dict(self.DEFAULT_WORK_ITEM_TYPES)
        self.work_item_types_by_str: Dict[str, str] = {}
        for key, value in sync_cfg.get("work_item_types", {}).items():
            if isinstance(key, ItemType):
                self.work_item_types[key] = value
            else:
                self.work_item_types_by_str[str(key).strip().lower()] = value

        self.state_map = dict(self.DEFAULT_STATES)
        self.state_map_by_str: Dict[str, str] = {}
        for key, value in sync_cfg.get("state_map", {}).items():
            if isinstance(key, ItemStatus):
                self.state_map[key] = value
            else:
                self.state_map_by_str[str(key).strip().lower()] = value

        self.field_names = dict(self.DEFAULT_FIELDS)
        self.field_names.update(sync_cfg.get("fields", {}))

        self.enable_priority_field = bool(sync_cfg.get("enable_priority_field", False))
        self.enable_estimate_field = bool(sync_cfg.get("enable_estimate_field", False))
        self.enable_schedule_fields = bool(sync_cfg.get("enable_schedule_fields", False))
        self.enable_state_updates = bool(sync_cfg.get("enable_state_updates", False))
        self.set_state_on_create = bool(sync_cfg.get("set_state_on_create", False))

        # 認証方式: "az_cli" (推奨) or "pat"
        self.auth_mode = sync_cfg.get("auth_mode", "az_cli")

        # プロセステンプレート: "basic", "agile", "scrum", "cmmi"
        self.process_template = sync_cfg.get("process_template", "auto")
        self._detected_process: Optional[str] = None

        # スプリント自動設定
        self.auto_setup_sprints = bool(sync_cfg.get("auto_setup_sprints", True))
        self.sprint_duration_days = int(sync_cfg.get("sprint_duration_days", 14))
        self.num_sprints = int(sync_cfg.get("num_sprints", 3))

        # WorkItemをスプリントに自動割り当て
        self.auto_assign_to_sprints = bool(sync_cfg.get("auto_assign_to_sprints", True))

        if not self.organization:
            self.log("Warning: azure_devops.organization is not configured")
        if not self.project:
            self.log("Warning: azure_devops.project is not configured")

    @property
    def base_url(self) -> str:
        return f"https://dev.azure.com/{self.organization}/{self.project}/_apis"

    def _run_az_cli(self, args: List[str], check: bool = True) -> Optional[str]:
        """az CLI を実行"""
        if self.dry_run:
            self.log(f"[DRY-RUN] az {' '.join(args)}")
            return None

        cmd = ["az"] + args
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
            raise RuntimeError("az CLI is not installed. Please install Azure CLI.")

    def _detect_process_template(self) -> str:
        """プロジェクトのプロセステンプレートを検出"""
        if self._detected_process:
            return self._detected_process

        if self.process_template != "auto":
            self._detected_process = self.process_template
            return self._detected_process

        result = self._run_az_cli([
            "devops", "project", "show",
            "--project", self.project,
            "--org", f"https://dev.azure.com/{self.organization}",
            "-o", "json"
        ])

        if result:
            try:
                data = json.loads(result)
                template_name = data.get("capabilities", {}).get(
                    "processTemplate", {}
                ).get("templateName", "").lower()

                if "basic" in template_name:
                    self._detected_process = "basic"
                elif "scrum" in template_name:
                    self._detected_process = "scrum"
                elif "agile" in template_name:
                    self._detected_process = "agile"
                elif "cmmi" in template_name:
                    self._detected_process = "cmmi"
                else:
                    self._detected_process = "agile"  # デフォルト

                self.log(f"Detected process template: {self._detected_process}")
            except json.JSONDecodeError:
                self._detected_process = "agile"
        else:
            self._detected_process = "agile"

        return self._detected_process

    def _resolve_work_item_type_for_process(self, item_type: ItemType) -> str:
        """プロセステンプレートに応じたWorkItemタイプを解決"""
        process = self._detect_process_template()

        if process == "basic":
            # Basic では Epic/Feature/User Story が存在しない
            return self.BASIC_PROCESS_TYPES.get(item_type, "Issue")

        # Agile/Scrum/CMMI では通常のマッピング
        return self._resolve_work_item_type(item_type)

    def _auth_header(self) -> str:
        token = base64.b64encode(f":{self.pat}".encode("utf-8")).decode("utf-8")
        return f"Basic {token}"

    def _request_json(
        self,
        method: str,
        url: str,
        body: Optional[Any] = None,
        content_type: str = "application/json",
    ) -> Optional[Dict[str, Any]]:
        if self.dry_run:
            self.log(f"{method} {url}")
            return {}

        headers = {
            "Accept": "application/json",
            "Content-Type": content_type,
        }
        if self.pat:
            headers["Authorization"] = self._auth_header()

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

    def authenticate(self) -> bool:
        if self.dry_run:
            self.log("Skipping authentication check in dry-run mode")
            return True

        # az CLI 認証を優先
        if self.auth_mode == "az_cli" or not self.pat:
            result = self._run_az_cli([
                "devops", "project", "show",
                "--project", self.project,
                "--org", f"https://dev.azure.com/{self.organization}",
                "-o", "json"
            ], check=False)

            if result:
                try:
                    data = json.loads(result)
                    if data.get("name") == self.project:
                        self.log(f"Authenticated via az CLI to project: {self.project}")
                        self.auth_mode = "az_cli"  # az CLI認証成功
                        return True
                except json.JSONDecodeError:
                    pass

        # PAT認証にフォールバック
        if self.pat:
            url = f"https://dev.azure.com/{self.organization}/_apis/projects?api-version={self.api_version}"
            result = self._request_json("GET", url)
            if result is not None:
                self.log("Authenticated via PAT")
                self.auth_mode = "pat"
                return True

        self.log("Authentication failed. Please run 'az login' or set AZURE_DEVOPS_PAT")
        return False

    def _build_tags(self, labels: List[str]) -> Optional[str]:
        cleaned = []
        for label in labels:
            if not label:
                continue
            cleaned.append(str(label).replace(";", ","))
        return "; ".join(sorted(set(cleaned))) if cleaned else None

    def _build_description(self, item: WorkItem) -> str:
        parts = []
        if item.description:
            parts.append(item.description)
        if item.acceptance_criteria:
            parts.append(
                "\nAcceptance Criteria:\n" + "\n".join(f"- {ac}" for ac in item.acceptance_criteria)
            )
        return "\n\n".join(p for p in parts if p)

    def _priority_value(self, priority: str) -> Optional[int]:
        if not priority:
            return None
        key = str(priority).strip().lower()
        if key == "high":
            return 1
        if key == "medium":
            return 2
        if key == "low":
            return 3
        return None

    def _resolve_work_item_type(self, item_type: ItemType) -> str:
        name = self.work_item_types.get(item_type)
        if name:
            return name
        return self.work_item_types_by_str.get(item_type.value, "Task")

    def _resolve_state(self, status: ItemStatus) -> Optional[str]:
        if not status:
            return None
        state = self.state_map.get(status)
        if state:
            return state
        return self.state_map_by_str.get(status.value)

    def create_item(self, item: WorkItem) -> Optional[str]:
        """WorkItemを作成（az CLI または REST API）"""
        # プロセステンプレートに応じたタイプ解決
        work_item_type = self._resolve_work_item_type_for_process(item.item_type)

        # az CLI 認証モードの場合
        if self.auth_mode == "az_cli":
            return self._create_item_via_cli(item, work_item_type)

        # REST API モード
        return self._create_item_via_rest(item, work_item_type)

    def _create_item_via_cli(self, item: WorkItem, work_item_type: str) -> Optional[str]:
        """az CLI経由でWorkItem作成"""
        args = [
            "boards", "work-item", "create",
            "--title", item.title,
            "--type", work_item_type,
            "--org", f"https://dev.azure.com/{self.organization}",
            "--project", self.project,
            "-o", "json"
        ]

        # Description
        description = self._build_description(item)
        if description:
            args.extend(["--description", description])

        # Area Path
        if self.area_path:
            args.extend(["--area", self.area_path])

        # Iteration Path (use --fields instead of --iteration due to known bug)
        if self.iteration_path:
            args.extend(["--fields", f"System.IterationPath={self.iteration_path}"])

        # Priority
        if self.enable_priority_field:
            priority_value = self._priority_value(item.priority)
            if priority_value is not None:
                args.extend(["--fields", f"Microsoft.VSTS.Common.Priority={priority_value}"])

        result = self._run_az_cli(args)
        if result:
            try:
                data = json.loads(result)
                work_item_id = data.get("id")
                if work_item_id:
                    self.log(f"Created {work_item_type} #{work_item_id}: {item.title}")
                    return str(work_item_id)
            except json.JSONDecodeError:
                self.log(f"Failed to parse create response: {result[:100]}")
        return None

    def _create_item_via_rest(self, item: WorkItem, work_item_type: str) -> Optional[str]:
        """REST API経由でWorkItem作成"""
        work_item_type_encoded = urllib.parse.quote(work_item_type)

        patch = []
        patch.append({"op": "add", "path": f"/fields/{self.field_names['title']}", "value": item.title})

        description = self._build_description(item)
        if description:
            patch.append({"op": "add", "path": f"/fields/{self.field_names['description']}", "value": description})

        tags = self._build_tags(item.labels)
        if tags:
            patch.append({"op": "add", "path": f"/fields/{self.field_names['tags']}", "value": tags})

        if self.area_path:
            patch.append({"op": "add", "path": f"/fields/{self.field_names['area_path']}", "value": self.area_path})
        if self.iteration_path:
            patch.append({"op": "add", "path": f"/fields/{self.field_names['iteration_path']}", "value": self.iteration_path})

        if self.enable_priority_field:
            priority_value = self._priority_value(item.priority)
            if priority_value is not None:
                patch.append({"op": "add", "path": f"/fields/{self.field_names['priority']}", "value": priority_value})

        if self.set_state_on_create and item.status:
            state = self._resolve_state(item.status)
            if state:
                patch.append({"op": "add", "path": f"/fields/{self.field_names['state']}", "value": state})

        url = f"{self.base_url}/wit/workitems/${work_item_type_encoded}?api-version={self.api_version}"
        result = self._request_json("POST", url, patch, content_type="application/json-patch+json")
        if result and "id" in result:
            return str(result["id"])
        return None

    def update_item(self, item: WorkItem) -> bool:
        """WorkItem更新"""
        if not item.external_id:
            return False

        # az CLI モードの場合
        if self.auth_mode == "az_cli":
            return self._update_item_via_cli(item)

        # REST API モード
        return self._update_item_via_rest(item)

    def _update_item_via_cli(self, item: WorkItem) -> bool:
        """az CLI経由でWorkItem更新"""
        args = [
            "boards", "work-item", "update",
            "--id", item.external_id,
            "--title", item.title,
            "--org", f"https://dev.azure.com/{self.organization}",
            "-o", "json"
        ]

        description = self._build_description(item)
        if description:
            args.extend(["--description", description])

        fields = []
        tags = self._build_tags(item.labels)
        if tags:
            fields.append(f"System.Tags={tags}")

        if self.enable_priority_field:
            priority_value = self._priority_value(item.priority)
            if priority_value is not None:
                fields.append(f"Microsoft.VSTS.Common.Priority={priority_value}")

        for field in fields:
            args.extend(["--fields", field])

        result = self._run_az_cli(args)
        return result is not None

    def _update_item_via_rest(self, item: WorkItem) -> bool:
        """REST API経由でWorkItem更新"""
        patch = []
        patch.append({"op": "add", "path": f"/fields/{self.field_names['title']}", "value": item.title})

        description = self._build_description(item)
        if description:
            patch.append({"op": "add", "path": f"/fields/{self.field_names['description']}", "value": description})

        tags = self._build_tags(item.labels)
        if tags:
            patch.append({"op": "add", "path": f"/fields/{self.field_names['tags']}", "value": tags})

        if self.enable_priority_field:
            priority_value = self._priority_value(item.priority)
            if priority_value is not None:
                patch.append({"op": "add", "path": f"/fields/{self.field_names['priority']}", "value": priority_value})

        url = f"{self.base_url}/wit/workitems/{item.external_id}?api-version={self.api_version}"
        result = self._request_json("PATCH", url, patch, content_type="application/json-patch+json")
        return result is not None

    def get_item(self, external_id: str) -> Optional[WorkItem]:
        """WorkItemを取得"""
        # az CLI モードの場合
        if self.auth_mode == "az_cli":
            return self._get_item_via_cli(external_id)

        # REST API モード
        return self._get_item_via_rest(external_id)

    def _get_item_via_cli(self, external_id: str) -> Optional[WorkItem]:
        """az CLI経由でWorkItem取得"""
        result = self._run_az_cli([
            "boards", "work-item", "show",
            "--id", external_id,
            "--org", f"https://dev.azure.com/{self.organization}",
            "-o", "json"
        ])

        if result:
            try:
                data = json.loads(result)
                fields = data.get("fields", {})
                title = fields.get("System.Title", "")
                description = fields.get("System.Description", "")

                return WorkItem(
                    id=str(external_id),
                    title=title,
                    description=description,
                    item_type=ItemType.STORY,
                    priority="medium",
                    external_id=str(external_id),
                )
            except json.JSONDecodeError:
                pass
        return None

    def _get_item_via_rest(self, external_id: str) -> Optional[WorkItem]:
        """REST API経由でWorkItem取得"""
        url = f"{self.base_url}/wit/workitems/{external_id}?api-version={self.api_version}"
        result = self._request_json("GET", url)
        if not result:
            return None

        fields = result.get("fields", {})
        title = fields.get(self.field_names["title"], "")
        description = fields.get(self.field_names["description"], "")

        return WorkItem(
            id=str(external_id),
            title=title,
            description=description,
            item_type=ItemType.STORY,
            priority="medium",
            external_id=str(external_id),
        )

    def find_item_by_title(self, title: str) -> Optional[WorkItem]:
        """タイトルでWorkItemを検索"""
        # az CLI モードの場合
        if self.auth_mode == "az_cli":
            return self._find_item_by_title_via_cli(title)

        # REST API モード
        return self._find_item_by_title_via_rest(title)

    def _find_item_by_title_via_cli(self, title: str) -> Optional[WorkItem]:
        """az CLI経由でタイトル検索"""
        # WIQLクエリを使用
        escaped = title.replace("'", "''").replace('"', '\\"')
        wiql = f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{self.project}' AND [System.Title] = '{escaped}'"

        result = self._run_az_cli([
            "boards", "query",
            "--wiql", wiql,
            "--org", f"https://dev.azure.com/{self.organization}",
            "-o", "json"
        ])

        if result:
            try:
                data = json.loads(result)
                if data and len(data) > 0:
                    work_item_id = data[0].get("id")
                    if work_item_id:
                        return self.get_item(str(work_item_id))
            except json.JSONDecodeError:
                pass
        return None

    def _find_item_by_title_via_rest(self, title: str) -> Optional[WorkItem]:
        """REST API経由でタイトル検索"""
        escaped = title.replace("'", "''")
        wiql = {
            "query": (
                "Select [System.Id] From WorkItems "
                f"Where [System.TeamProject] = '{self.project}' "
                f"And [System.Title] = '{escaped}'"
            )
        }
        url = f"{self.base_url}/wit/wiql?api-version={self.api_version}"
        result = self._request_json("POST", url, wiql)
        if not result:
            return None

        items = result.get("workItems") or []
        if not items:
            return None

        work_item_id = items[0].get("id")
        if not work_item_id:
            return None

        return self.get_item(str(work_item_id))

    def create_label(self, name: str, color: str = "") -> bool:
        # ADO tags are applied directly to work items; no global label create needed.
        return True

    def create_milestone(self, name: str, due_date: Optional[str] = None) -> bool:
        """
        Create an Iteration (Sprint) in Azure DevOps.

        Note: Iteration creation via REST API/CLI requires proper project permissions.
        The iteration_path field on work items requires the iteration to exist
        AND be added to the team's iteration list.

        Known issues:
        - az boards work-item update --iteration "Sprint-1" often fails with TF401347
        - Workaround: Use System.IterationPath field via --fields option
        - Iteration names cannot contain: / \\ : < > | " ? *
        """
        # Sanitize name - remove invalid characters
        invalid_chars = ['/', '\\', ':', '<', '>', '|', '"', '?', '*']
        sanitized_name = name
        for char in invalid_chars:
            sanitized_name = sanitized_name.replace(char, '-')

        # az CLI モードの場合
        if self.auth_mode == "az_cli":
            # az CLIではIteration作成APIが直接サポートされていないため、
            # 既存のプロジェクトルートIterationを使用する
            self.log(f"Note: Iteration '{sanitized_name}' will use project root iteration. "
                     "Create iterations manually in Azure DevOps if needed.")
            return True

        # REST API モード（PAT認証）
        url = (
            f"https://dev.azure.com/{self.organization}/{self.project}/_apis"
            f"/wit/classificationnodes/Iterations/{urllib.parse.quote(sanitized_name)}"
            f"?api-version={self.api_version}"
        )

        body: Dict[str, Any] = {"name": sanitized_name}
        if due_date:
            # ADO expects ISO 8601 format for dates
            body["attributes"] = {"finishDate": due_date}

        result = self._request_json("POST", url, body)
        if result is None:
            self.log(f"Warning: Failed to create iteration '{sanitized_name}'. "
                     "It may already exist or require manual creation.")
            # Return True anyway to allow workflow to continue
            return True

        self.log(f"Created iteration: {sanitized_name}")
        return True

    def set_iteration_path(self, work_item_id: str, iteration_name: str) -> bool:
        """
        Set the iteration path for a work item.

        Known issue: az CLI --iteration option often fails with TF401347.
        This method uses REST API PATCH with System.IterationPath field directly.

        Args:
            work_item_id: The work item ID
            iteration_name: The iteration name (will be prefixed with project path)

        Returns:
            True if successful, False otherwise
        """
        # Build full iteration path
        # Format: "ProjectName" or "ProjectName\\Iteration\\SprintName"
        if '\\' in iteration_name or '/' in iteration_name:
            # Already a full path
            iteration_path = iteration_name.replace('/', '\\')
        else:
            # Just the name, build full path
            iteration_path = f"{self.project}\\Iteration\\{iteration_name}"

        patch = [{
            "op": "add",
            "path": f"/fields/{self.field_names['iteration_path']}",
            "value": iteration_path,
        }]

        url = f"{self.base_url}/wit/workitems/{work_item_id}?api-version={self.api_version}"
        result = self._request_json("PATCH", url, patch, content_type="application/json-patch+json")

        if result is None:
            # Fallback: try with project root iteration
            self.log(f"Warning: Failed to set iteration '{iteration_path}', falling back to project root")
            patch[0]["value"] = self.project
            result = self._request_json("PATCH", url, patch, content_type="application/json-patch+json")

        return result is not None

    def setup_sprints_and_team(self, start_date: Optional[str] = None) -> bool:
        """
        スプリント（Iteration）を自動設定し、チームに追加する。

        Args:
            start_date: 最初のスプリント開始日 (ISO形式 YYYY-MM-DD)。省略時は翌月曜

        Returns:
            成功時True
        """
        if self.auth_mode != "az_cli":
            self.log("Sprint setup requires az CLI authentication mode")
            return False

        from datetime import datetime, timedelta

        # 開始日の決定（指定なしの場合は次の月曜日）
        if start_date:
            base_date = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            today = datetime.now()
            # 次の月曜日を計算
            days_until_monday = (7 - today.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            base_date = today + timedelta(days=days_until_monday)

        # 既存のIterationを確認
        existing_iterations = self._get_team_iterations()

        sprint_infos = []
        for i in range(self.num_sprints):
            sprint_start = base_date + timedelta(days=i * self.sprint_duration_days)
            sprint_end = sprint_start + timedelta(days=self.sprint_duration_days - 1)
            sprint_name = f"Sprint {i + 1}"
            sprint_path = f"\\{self.project}\\Iteration\\{sprint_name}"

            sprint_infos.append({
                "name": sprint_name,
                "path": sprint_path,
                "start": sprint_start.strftime("%Y-%m-%d"),
                "end": sprint_end.strftime("%Y-%m-%d"),
            })

        # スプリント日付を設定
        for sprint in sprint_infos:
            # 既存チェック
            if sprint["name"] in existing_iterations:
                self.log(f"Sprint already configured: {sprint['name']}")
                continue

            # 日付設定
            result = self._run_az_cli([
                "boards", "iteration", "project", "update",
                "--org", f"https://dev.azure.com/{self.organization}",
                "--project", self.project,
                "--path", sprint["path"],
                "--start-date", sprint["start"],
                "--finish-date", sprint["end"],
                "-o", "json"
            ], check=False)

            if result:
                self.log(f"Configured sprint: {sprint['name']} ({sprint['start']} - {sprint['end']})")
            else:
                # Iterationが存在しない場合、既存のIteration 1, 2, 3を使う
                iteration_num = int(sprint["name"].split()[-1])
                alt_path = f"\\{self.project}\\Iteration\\Iteration {iteration_num}"
                result = self._run_az_cli([
                    "boards", "iteration", "project", "update",
                    "--org", f"https://dev.azure.com/{self.organization}",
                    "--project", self.project,
                    "--path", alt_path,
                    "--start-date", sprint["start"],
                    "--finish-date", sprint["end"],
                    "-o", "json"
                ], check=False)

                if result:
                    self.log(f"Configured iteration: Iteration {iteration_num} ({sprint['start']} - {sprint['end']})")
                    sprint["path"] = alt_path
                    sprint["name"] = f"Iteration {iteration_num}"

        # チームにスプリントを追加
        for sprint in sprint_infos:
            self._add_iteration_to_team(sprint["name"])

        return True

    def _get_team_iterations(self) -> List[str]:
        """チームに設定済みのIteration名を取得"""
        result = self._run_az_cli([
            "boards", "iteration", "team", "list",
            "--org", f"https://dev.azure.com/{self.organization}",
            "--project", self.project,
            "--team", self.team or f"{self.project} Team",
            "-o", "json"
        ], check=False)

        if result:
            try:
                data = json.loads(result)
                return [item.get("name", "") for item in data]
            except json.JSONDecodeError:
                pass
        return []

    def _add_iteration_to_team(self, iteration_name: str) -> bool:
        """IterationをチームのSprintに追加"""
        # まずIteration IDを取得
        result = self._run_az_cli([
            "boards", "iteration", "project", "list",
            "--org", f"https://dev.azure.com/{self.organization}",
            "--project", self.project,
            "-o", "json"
        ], check=False)

        iteration_id = None
        if result:
            try:
                data = json.loads(result)
                for item in data:
                    if item.get("name") == iteration_name:
                        iteration_id = item.get("identifier")
                        break
                    # 子Iterationもチェック
                    for child in item.get("children", []):
                        if child.get("name") == iteration_name:
                            iteration_id = child.get("identifier")
                            break
            except json.JSONDecodeError:
                pass

        if not iteration_id:
            self.log(f"Could not find iteration ID for: {iteration_name}")
            return False

        # チームに追加
        result = self._run_az_cli([
            "boards", "iteration", "team", "add",
            "--org", f"https://dev.azure.com/{self.organization}",
            "--project", self.project,
            "--team", self.team or f"{self.project} Team",
            "--id", iteration_id,
            "-o", "json"
        ], check=False)

        if result:
            self.log(f"Added iteration to team: {iteration_name}")
            return True
        return False

    def assign_items_to_sprints(self, items: List[WorkItem], id_mapping: Dict[str, str]) -> int:
        """
        WorkItemをスプリントに自動割り当て。
        Feature単位でグループ化し、均等にスプリントに分配する。

        Args:
            items: WorkItemリスト
            id_mapping: 内部ID -> ADO WorkItem ID のマッピング

        Returns:
            割り当てた件数
        """
        if not self.auto_assign_to_sprints:
            return 0

        # Feature単位でグループ化
        features = [item for item in items if item.item_type == ItemType.FEATURE]

        if not features:
            return 0

        # スプリント名のリストを取得
        iterations = self._get_team_iterations()
        sprint_iterations = [it for it in iterations if it.startswith("Sprint") or it.startswith("Iteration")]

        if not sprint_iterations:
            self.log("No sprints configured for assignment")
            return 0

        # Featureを均等に分配
        assigned = 0
        for i, feature in enumerate(features):
            sprint_idx = i % len(sprint_iterations)
            sprint_name = sprint_iterations[sprint_idx]
            iteration_path = f"{self.project}\\{sprint_name}"

            # Feature自体を割り当て
            feature_ado_id = id_mapping.get(feature.id) or id_mapping.get(feature.unified_key or "")
            if feature_ado_id:
                self._update_work_item_iteration(feature_ado_id, iteration_path)
                assigned += 1

            # 子Storyも同じスプリントに割り当て
            for item in items:
                if item.parent_id == feature.id or item.parent_id == feature.unified_key:
                    story_ado_id = id_mapping.get(item.id) or id_mapping.get(item.unified_key or "")
                    if story_ado_id:
                        self._update_work_item_iteration(story_ado_id, iteration_path)
                        assigned += 1

        self.log(f"Assigned {assigned} items to sprints")
        return assigned

    def _update_work_item_iteration(self, work_item_id: str, iteration_path: str) -> bool:
        """WorkItemのIterationPathを更新"""
        result = self._run_az_cli([
            "boards", "work-item", "update",
            "--id", work_item_id,
            "--org", f"https://dev.azure.com/{self.organization}",
            "--fields", f"System.IterationPath={iteration_path}",
            "-o", "none"
        ], check=False)
        return result is not None

    def add_to_project(self, external_id: str) -> Optional[str]:
        # ADO work items appear on boards automatically.
        return external_id

    def update_project_fields(
        self,
        project_item_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        estimate: Optional[int] = None,
        status: Optional[ItemStatus] = None,
    ) -> bool:
        """プロジェクトフィールド更新（スケジュール、見積等）"""
        # az CLI モードの場合
        if self.auth_mode == "az_cli":
            return self._update_project_fields_via_cli(
                project_item_id, start_date, end_date, estimate, status
            )

        # REST API モード
        return self._update_project_fields_via_rest(
            project_item_id, start_date, end_date, estimate, status
        )

    def _update_project_fields_via_cli(
        self,
        project_item_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        estimate: Optional[int] = None,
        status: Optional[ItemStatus] = None,
    ) -> bool:
        """az CLI経由でフィールド更新"""
        fields = []

        if self.enable_schedule_fields:
            if start_date:
                fields.append(f"Microsoft.VSTS.Scheduling.StartDate={start_date}")
            if end_date:
                fields.append(f"Microsoft.VSTS.Scheduling.TargetDate={end_date}")

        if self.enable_estimate_field and estimate is not None:
            fields.append(f"Microsoft.VSTS.Scheduling.Effort={estimate}")

        if self.enable_state_updates and status:
            state = self._resolve_state(status)
            if state:
                fields.append(f"System.State={state}")

        if not fields:
            return True

        args = [
            "boards", "work-item", "update",
            "--id", project_item_id,
            "--org", f"https://dev.azure.com/{self.organization}",
            "-o", "json"
        ]

        for field in fields:
            args.extend(["--fields", field])

        result = self._run_az_cli(args)
        return result is not None

    def _update_project_fields_via_rest(
        self,
        project_item_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        estimate: Optional[int] = None,
        status: Optional[ItemStatus] = None,
    ) -> bool:
        """REST API経由でフィールド更新"""
        patch = []

        if self.enable_schedule_fields:
            if start_date:
                patch.append({
                    "op": "add",
                    "path": f"/fields/{self.field_names['start_date']}",
                    "value": start_date,
                })
            if end_date:
                patch.append({
                    "op": "add",
                    "path": f"/fields/{self.field_names['target_date']}",
                    "value": end_date,
                })

        if self.enable_estimate_field and estimate is not None:
            estimate_field = self.field_names.get("estimate")
            if estimate_field:
                patch.append({
                    "op": "add",
                    "path": f"/fields/{estimate_field}",
                    "value": estimate,
                })

        if self.enable_state_updates and status:
            state = self._resolve_state(status)
            if state:
                patch.append({
                    "op": "add",
                    "path": f"/fields/{self.field_names['state']}",
                    "value": state,
                })

        if not patch:
            return True

        url = f"{self.base_url}/wit/workitems/{project_item_id}?api-version={self.api_version}"
        result = self._request_json("PATCH", url, patch, content_type="application/json-patch+json")
        return result is not None

    def set_parent_child_relation(self, child_id: str, parent_id: str) -> bool:
        """親子関係を設定"""
        # az CLI モードの場合
        if self.auth_mode == "az_cli":
            return self._set_parent_child_via_cli(child_id, parent_id)

        # REST API モード
        return self._set_parent_child_via_rest(child_id, parent_id)

    def _set_parent_child_via_cli(self, child_id: str, parent_id: str) -> bool:
        """az CLI経由で親子関係設定"""
        result = self._run_az_cli([
            "boards", "work-item", "relation", "add",
            "--id", child_id,
            "--relation-type", "Parent",
            "--target-id", parent_id,
            "--org", f"https://dev.azure.com/{self.organization}",
            "-o", "json"
        ])

        if result:
            self.log(f"Set parent relation: #{child_id} -> #{parent_id}")
            return True
        return False

    def _set_parent_child_via_rest(self, child_id: str, parent_id: str) -> bool:
        """REST API経由で親子関係設定"""
        relation = {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": f"https://dev.azure.com/{self.organization}/{self.project}/_apis/wit/workItems/{parent_id}",
            },
        }
        url = f"{self.base_url}/wit/workitems/{child_id}?api-version={self.api_version}"
        result = self._request_json("PATCH", url, [relation], content_type="application/json-patch+json")
        return result is not None

    def sync_items(self, items: List[WorkItem]) -> SyncResult:
        result = SyncResult(success=True)

        if not self.authenticate():
            result.add_error("Authentication failed")
            return result

        # labels and milestones are optional in ADO; keep base behavior as no-op
        all_labels = set()
        for item in items:
            all_labels.update(item.labels)
        for label in all_labels:
            self.create_label(label)

        milestones = set(item.milestone for item in items if item.milestone)
        for ms in milestones:
            self.create_milestone(ms)

        id_mapping: Dict[str, str] = {}

        def register_mapping(item: WorkItem, external_id: str) -> None:
            id_mapping[item.id] = external_id
            if item.unified_key:
                id_mapping[item.unified_key] = external_id

        for item in items:
            try:
                existing = self.find_item_by_title(item.title)
                if existing and existing.external_id:
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
                    external_id = self.create_item(item)
                    if external_id:
                        result.created += 1
                        register_mapping(item, external_id)
                        item.external_id = external_id

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

        # Second pass: set parent-child relations
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

        # Third pass: setup sprints and assign items
        if self.auto_setup_sprints:
            self.log("Setting up sprints...")
            self.setup_sprints_and_team()

        if self.auto_assign_to_sprints:
            self.log("Assigning items to sprints...")
            assigned_count = self.assign_items_to_sprints(items, id_mapping)
            if assigned_count > 0:
                self.log(f"Assigned {assigned_count} items to sprints")

        return result
