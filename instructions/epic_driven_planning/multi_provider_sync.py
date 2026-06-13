#!/usr/bin/env python3
"""
Multi-Provider Ticket Sync - 3環境同期ツール

decomposition.json を読み込み、GitHub/GitLab/Azure DevOps に
Issues/Work Items として同期する
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class SyncResult:
    provider: str
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class MultiProviderSync:
    """3環境同期"""

    def __init__(self, decomposition_path: str = "output/decomposition.json"):
        with open(decomposition_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.features = self.data.get("features", [])

    def sync_to_github(self, owner: str, repo: str) -> SyncResult:
        """GitHub Issues に同期"""
        result = SyncResult(provider="GitHub")

        print(f"\n{'='*60}")
        print(f"📦 GitHub: {owner}/{repo}")
        print(f"{'='*60}")

        for feature in self.features:
            # Feature を Issue として作成
            feature_title = f"[Feature] {feature.get('title', 'N/A')}"
            feature_body = self._build_feature_body(feature)

            try:
                issue = self._gh_create_issue(owner, repo, feature_title, feature_body, ["feature", "epic"])
                if issue:
                    result.created += 1
                    print(f"  ✅ Created Feature: {feature.get('id')}")
                    feature_number = issue.get("number")
                else:
                    result.skipped += 1
                    feature_number = None
            except Exception as e:
                result.failed += 1
                result.errors.append(f"Feature {feature.get('id')}: {e}")
                print(f"  ❌ Failed Feature: {feature.get('id')} - {e}")
                continue

            # Stories を Issue として作成
            for story in feature.get("stories", []):
                story_title = f"[Story] {story.get('title', 'N/A')}"
                story_body = self._build_story_body(story, feature.get('id'))

                try:
                    issue = self._gh_create_issue(owner, repo, story_title, story_body, ["story", f"feature:{feature.get('id')}"])
                    if issue:
                        result.created += 1
                        print(f"    ✅ Created Story: {story.get('id')}")
                    else:
                        result.skipped += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Story {story.get('id')}: {e}")
                    print(f"    ❌ Failed Story: {story.get('id')} - {e}")

        return result

    def _gh_ensure_labels(self, owner: str, repo: str, labels: List[str]):
        """GitHub ラベルを作成（存在しない場合）"""
        for label in labels:
            cmd = ["gh", "label", "create", label, "-R", f"{owner}/{repo}", "--force"]
            subprocess.run(cmd, capture_output=True, text=True)

    def _gh_create_issue(self, owner: str, repo: str, title: str, body: str, labels: List[str]) -> Optional[Dict]:
        """GitHub Issue 作成（gh CLI使用）"""
        # 既存チェック
        check_cmd = ["gh", "issue", "list", "-R", f"{owner}/{repo}", "--search", f'"{title[:50]}"', "--json", "number,title"]
        result = subprocess.run(check_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            existing = json.loads(result.stdout)
            for issue in existing:
                if issue.get("title") == title:
                    print(f"      (skip: already exists #{issue.get('number')})")
                    return None

        # ラベル作成（存在しない場合）
        self._gh_ensure_labels(owner, repo, labels)

        # 作成
        label_args = []
        for label in labels:
            label_args.extend(["--label", label])

        cmd = ["gh", "issue", "create", "-R", f"{owner}/{repo}", "--title", title, "--body", body] + label_args
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(result.stderr)

        # 番号を取得
        url = result.stdout.strip()
        number = int(url.split("/")[-1]) if url else 0
        return {"number": number, "url": url}

    def sync_to_gitlab(self, project_path: str) -> SyncResult:
        """GitLab Issues に同期"""
        result = SyncResult(provider="GitLab")
        token = os.environ.get("GITLAB_TOKEN", "")

        if not token:
            result.errors.append("GITLAB_TOKEN not set")
            return result

        print(f"\n{'='*60}")
        print(f"🦊 GitLab: {project_path}")
        print(f"{'='*60}")

        # プロジェクトID取得
        project_id = self._gitlab_get_project_id(project_path, token)
        if not project_id:
            result.errors.append(f"Project not found: {project_path}")
            return result

        for feature in self.features:
            feature_title = f"[Feature] {feature.get('title', 'N/A')}"
            feature_desc = self._build_feature_body(feature)

            try:
                issue = self._gitlab_create_issue(project_id, feature_title, feature_desc, ["Feature", "Epic"], token)
                if issue:
                    result.created += 1
                    print(f"  ✅ Created Feature: {feature.get('id')}")
                else:
                    result.skipped += 1
            except Exception as e:
                result.failed += 1
                result.errors.append(f"Feature {feature.get('id')}: {e}")
                print(f"  ❌ Failed Feature: {feature.get('id')} - {e}")
                continue

            for story in feature.get("stories", []):
                story_title = f"[Story] {story.get('title', 'N/A')}"
                story_desc = self._build_story_body(story, feature.get('id'))

                try:
                    issue = self._gitlab_create_issue(project_id, story_title, story_desc, ["Story", f"feature::{feature.get('id')}"], token)
                    if issue:
                        result.created += 1
                        print(f"    ✅ Created Story: {story.get('id')}")
                    else:
                        result.skipped += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Story {story.get('id')}: {e}")
                    print(f"    ❌ Failed Story: {story.get('id')} - {e}")

        return result

    def _gitlab_get_project_id(self, project_path: str, token: str) -> Optional[int]:
        """GitLab プロジェクトID取得"""
        encoded = urllib.parse.quote(project_path, safe='')
        url = f"https://gitlab.com/api/v4/projects/{encoded}"
        headers = {"PRIVATE-TOKEN": token}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                return data.get("id")
        except:
            return None

    def _gitlab_create_issue(self, project_id: int, title: str, description: str, labels: List[str], token: str) -> Optional[Dict]:
        """GitLab Issue 作成"""
        # 既存チェック
        check_url = f"https://gitlab.com/api/v4/projects/{project_id}/issues?search={urllib.parse.quote(title[:30])}"
        headers = {"PRIVATE-TOKEN": token}
        req = urllib.request.Request(check_url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                existing = json.loads(resp.read().decode())
                for issue in existing:
                    if issue.get("title") == title:
                        print(f"      (skip: already exists #{issue.get('iid')})")
                        return None
        except:
            pass

        # ラベル作成（存在しない場合）
        for label in labels:
            self._gitlab_ensure_label(project_id, label, token)

        # Issue作成
        url = f"https://gitlab.com/api/v4/projects/{project_id}/issues"
        data = {
            "title": title,
            "description": description,
            "labels": ",".join(labels),
        }
        req_data = json.dumps(data).encode()
        headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    def _gitlab_ensure_label(self, project_id: int, label: str, token: str):
        """GitLab ラベル作成（存在しない場合）"""
        url = f"https://gitlab.com/api/v4/projects/{project_id}/labels"
        data = {"name": label, "color": "#428BCA"}
        req_data = json.dumps(data).encode()
        headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
        try:
            urllib.request.urlopen(req)
        except:
            pass  # 既に存在する場合は無視

    def sync_to_azure_devops(self, org: str, project: str) -> SyncResult:
        """Azure DevOps Work Items に同期"""
        result = SyncResult(provider="Azure DevOps")
        pat = os.environ.get("AZURE_DEVOPS_PAT", "")

        if not pat:
            result.errors.append("AZURE_DEVOPS_PAT not set")
            return result

        print(f"\n{'='*60}")
        print(f"🔷 Azure DevOps: {org}/{project}")
        print(f"{'='*60}")

        # 利用可能なワークアイテムタイプを取得
        available_types = self._ado_get_work_item_types(org, project, pat)
        print(f"   Available types: {available_types}")

        # プロセステンプレートに応じたマッピング
        # Agile: Feature, User Story, Task, Bug
        # Scrum: Feature, Product Backlog Item, Task, Bug
        # Basic: Epic, Issue, Task
        # CMMI: Feature, Requirement, Task, Bug
        if "Feature" in available_types:
            feature_type = "Feature"
            story_type = "User Story" if "User Story" in available_types else "Product Backlog Item" if "Product Backlog Item" in available_types else "Issue"
        elif "Epic" in available_types:
            # Basic テンプレート
            feature_type = "Epic"
            story_type = "Issue"
        else:
            feature_type = "Issue"
            story_type = "Task"

        print(f"   Using: Feature={feature_type}, Story={story_type}")

        for feature in self.features:
            feature_title = feature.get('title', 'N/A')
            feature_desc = self._build_feature_body(feature)

            try:
                wi = self._ado_create_work_item(org, project, feature_type, feature_title, feature_desc, pat)
                if wi:
                    result.created += 1
                    print(f"  ✅ Created {feature_type}: {feature.get('id')}")
                    feature_id = wi.get("id")
                else:
                    result.skipped += 1
                    feature_id = None
            except Exception as e:
                result.failed += 1
                result.errors.append(f"Feature {feature.get('id')}: {e}")
                print(f"  ❌ Failed {feature_type}: {feature.get('id')} - {e}")
                continue

            for story in feature.get("stories", []):
                story_title = story.get('title', 'N/A')
                story_desc = self._build_story_body(story, feature.get('id'))

                try:
                    wi = self._ado_create_work_item(org, project, story_type, story_title, story_desc, pat, parent_id=feature_id)
                    if wi:
                        result.created += 1
                        print(f"    ✅ Created {story_type}: {story.get('id')}")
                    else:
                        result.skipped += 1
                except Exception as e:
                    result.failed += 1
                    result.errors.append(f"Story {story.get('id')}: {e}")
                    print(f"    ❌ Failed {story_type}: {story.get('id')} - {e}")

        return result

    def _ado_get_work_item_types(self, org: str, project: str, pat: str) -> List[str]:
        """利用可能なワークアイテムタイプを取得"""
        import base64
        url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitemtypes?api-version=7.0"
        auth = base64.b64encode(f":{pat}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                return [t.get("name") for t in data.get("value", [])]
        except:
            return []

    def _ado_create_work_item(self, org: str, project: str, work_item_type: str, title: str, description: str, pat: str, parent_id: Optional[int] = None) -> Optional[Dict]:
        """Azure DevOps Work Item 作成"""
        import base64

        # 既存チェック（WIQLで検索）
        wiql_url = f"https://dev.azure.com/{org}/{project}/_apis/wit/wiql?api-version=7.0"
        wiql_query = {
            "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.Title] = '{title}' AND [System.WorkItemType] = '{work_item_type}'"
        }
        auth = base64.b64encode(f":{pat}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(wiql_url, data=json.dumps(wiql_query).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode())
                if result.get("workItems"):
                    print(f"      (skip: already exists #{result['workItems'][0]['id']})")
                    return None
        except:
            pass

        # 作成
        url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/${urllib.parse.quote(work_item_type)}?api-version=7.0"
        operations = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": description},
        ]

        if parent_id:
            operations.append({
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems/{parent_id}"
                }
            })

        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json-patch+json"
        }
        req = urllib.request.Request(url, data=json.dumps(operations).encode(), headers=headers, method="POST")

        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    def _build_feature_body(self, feature: Dict) -> str:
        """Feature の本文を生成"""
        stories = feature.get("stories", [])
        story_list = "\n".join([f"- [ ] {s.get('id')}: {s.get('title')}" for s in stories])

        return f"""## {feature.get('id')}: {feature.get('title')}

{feature.get('description', '')}

### Stories
{story_list}

### Priority
{feature.get('priority', 'medium')}

### Total Hours
{feature.get('total_hours', 0)}h

---
*Generated by Epic-Driven Planning*
"""

    def _build_story_body(self, story: Dict, feature_id: str) -> str:
        """Story の本文を生成"""
        ac = story.get("acceptance_criteria", [])
        ac_list = "\n".join([f"- [ ] {a}" for a in ac])

        return f"""## {story.get('id')}: {story.get('title')}

**Parent Feature:** {feature_id}

{story.get('description', '')}

### Acceptance Criteria
{ac_list}

### Estimate
{story.get('estimate_hours', 0)}h

### Priority
{story.get('priority', 'medium')}

---
*Generated by Epic-Driven Planning*
"""


def main():
    import argparse

    parser = argparse.ArgumentParser(description="3環境同期ツール")
    parser.add_argument("--decomposition", default="output/decomposition.json", help="decomposition.json パス")
    parser.add_argument("--github", nargs=2, metavar=("OWNER", "REPO"), help="GitHub同期")
    parser.add_argument("--gitlab", metavar="PROJECT_PATH", help="GitLab同期")
    parser.add_argument("--ado", nargs=2, metavar=("ORG", "PROJECT"), help="Azure DevOps同期")
    parser.add_argument("--all", action="store_true", help="デフォルト設定で全環境同期")

    args = parser.parse_args()

    syncer = MultiProviderSync(args.decomposition)
    results = []

    if args.all:
        # デフォルト設定
        args.github = ("jinno-ai", "enterprise-rag-system")
        args.gitlab = "jinno-ai/enterprise-rag-system"
        args.ado = ("nobu007", "tokyo_career_up")

    if args.github:
        result = syncer.sync_to_github(args.github[0], args.github[1])
        results.append(result)

    if args.gitlab:
        result = syncer.sync_to_gitlab(args.gitlab)
        results.append(result)

    if args.ado:
        result = syncer.sync_to_azure_devops(args.ado[0], args.ado[1])
        results.append(result)

    # サマリー
    print("\n" + "=" * 60)
    print("📊 同期サマリー")
    print("=" * 60)

    total_created = 0
    total_skipped = 0
    total_failed = 0

    for r in results:
        total_created += r.created
        total_skipped += r.skipped
        total_failed += r.failed
        status = "✅" if r.failed == 0 else "⚠️"
        print(f"  {status} {r.provider}: Created={r.created}, Skipped={r.skipped}, Failed={r.failed}")
        if r.errors:
            for e in r.errors[:3]:
                print(f"      ❌ {e}")

    print("-" * 60)
    print(f"  Total: Created={total_created}, Skipped={total_skipped}, Failed={total_failed}")

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
