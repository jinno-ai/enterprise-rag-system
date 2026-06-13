#!/usr/bin/env python3
"""
プロジェクト同期状況サマリツール

GitHub, GitLab, Azure DevOps のプロジェクト情報を取得し、
Issue/Work Item の状況をサマリ表示する。

使用例:
    python sync_status.py --github owner/repo
    python sync_status.py --gitlab owner/project
    python sync_status.py --ado org/project
    python sync_status.py --all  # 設定ファイルから全プロジェクト
"""

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any


@dataclass
class ProjectSummary:
    """プロジェクトサマリ"""
    provider: str
    project: str
    open_count: int
    closed_count: int
    total_count: int
    milestones: List[Dict[str, Any]]
    labels: Dict[str, int]
    last_updated: Optional[str] = None
    error: Optional[str] = None


class SyncStatusTool:
    """同期状況サマリツール"""

    def __init__(self):
        self.github_token = os.environ.get('GITHUB_TOKEN', os.environ.get('GH_TOKEN', ''))
        self.gitlab_token = os.environ.get('GITLAB_TOKEN', '')
        self.ado_token = os.environ.get('AZURE_DEVOPS_PAT', '')

    def _request_json(
        self,
        url: str,
        headers: Dict[str, str],
        method: str = "GET",
        timeout: int = 10
    ) -> Optional[Any]:
        """HTTP リクエストを実行"""
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            print(f"  ⚠️ HTTP {e.code}: {url[:60]}...")
            return None
        except Exception as e:
            print(f"  ⚠️ Error: {type(e).__name__}: {str(e)[:50]}")
            return None

    def get_github_summary(self, repo: str) -> ProjectSummary:
        """GitHub リポジトリのサマリを取得"""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        base_url = f"https://api.github.com/repos/{repo}"

        # Open Issues
        open_issues = self._request_json(
            f"{base_url}/issues?state=open&per_page=100",
            headers
        ) or []

        # Closed Issues
        closed_issues = self._request_json(
            f"{base_url}/issues?state=closed&per_page=100",
            headers
        ) or []

        # PRを除外
        open_count = len([i for i in open_issues if 'pull_request' not in i])
        closed_count = len([i for i in closed_issues if 'pull_request' not in i])

        # Milestones
        milestones_data = self._request_json(
            f"{base_url}/milestones?state=all",
            headers
        ) or []

        milestones = []
        for ms in milestones_data:
            milestones.append({
                "title": ms.get("title", ""),
                "state": ms.get("state", ""),
                "open": ms.get("open_issues", 0),
                "closed": ms.get("closed_issues", 0),
                "due_date": ms.get("due_on", "")[:10] if ms.get("due_on") else None,
            })

        # Labels count
        labels: Dict[str, int] = {}
        for issue in open_issues:
            if 'pull_request' in issue:
                continue
            for label in issue.get("labels", []):
                name = label.get("name", "")
                labels[name] = labels.get(name, 0) + 1

        return ProjectSummary(
            provider="GitHub",
            project=repo,
            open_count=open_count,
            closed_count=closed_count,
            total_count=open_count + closed_count,
            milestones=milestones,
            labels=labels,
        )

    def get_gitlab_summary(self, project: str) -> ProjectSummary:
        """GitLab プロジェクトのサマリを取得"""
        headers = {"Accept": "application/json"}
        if self.gitlab_token:
            headers["PRIVATE-TOKEN"] = self.gitlab_token

        encoded_project = urllib.parse.quote(project, safe='')
        base_url = f"https://gitlab.com/api/v4/projects/{encoded_project}"

        # Open Issues
        open_issues = self._request_json(
            f"{base_url}/issues?state=opened&per_page=100",
            headers
        ) or []

        # Closed Issues
        closed_issues = self._request_json(
            f"{base_url}/issues?state=closed&per_page=100",
            headers
        ) or []

        open_count = len(open_issues)
        closed_count = len(closed_issues)

        # Milestones (マイルストーン情報のみ取得、Issue数は別途計算)
        milestones_data = self._request_json(
            f"{base_url}/milestones?state=active",
            headers
        ) or []

        # マイルストーン別のIssue数をカウント
        ms_counts: Dict[int, Dict[str, int]] = {}
        for issue in open_issues + closed_issues:
            ms = issue.get("milestone")
            if ms and ms.get("id"):
                ms_id = ms["id"]
                if ms_id not in ms_counts:
                    ms_counts[ms_id] = {"open": 0, "closed": 0}
                if issue.get("state") == "opened":
                    ms_counts[ms_id]["open"] += 1
                else:
                    ms_counts[ms_id]["closed"] += 1

        milestones = []
        for ms in milestones_data:
            ms_id = ms.get("id")
            counts = ms_counts.get(ms_id, {"open": 0, "closed": 0})

            milestones.append({
                "title": ms.get("title", ""),
                "state": ms.get("state", ""),
                "open": counts["open"],
                "closed": counts["closed"],
                "due_date": ms.get("due_date"),
                "start_date": ms.get("start_date"),
            })

        # Labels count
        labels: Dict[str, int] = {}
        for issue in open_issues:
            for label in issue.get("labels", []):
                labels[label] = labels.get(label, 0) + 1

        return ProjectSummary(
            provider="GitLab",
            project=project,
            open_count=open_count,
            closed_count=closed_count,
            total_count=open_count + closed_count,
            milestones=milestones,
            labels=labels,
        )

    def get_ado_summary(self, org_project: str) -> ProjectSummary:
        """Azure DevOps プロジェクトのサマリを取得（Azure CLI使用）"""
        import subprocess

        parts = org_project.split('/')
        if len(parts) != 2:
            return ProjectSummary(
                provider="Azure DevOps",
                project=org_project,
                open_count=0,
                closed_count=0,
                total_count=0,
                milestones=[],
                labels={},
                error="Invalid format. Use: org/project",
            )

        org, project = parts
        org_url = f"https://dev.azure.com/{org}"

        # Azure CLI で Work Item をクエリ
        try:
            # 全Work Itemを取得
            result = subprocess.run(
                [
                    "az", "boards", "query",
                    "--organization", org_url,
                    "--project", project,
                    "--wiql", f"SELECT [System.Id], [System.Title], [System.State] FROM WorkItems WHERE [System.TeamProject] = '{project}'",
                    "-o", "json"
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return ProjectSummary(
                    provider="Azure DevOps",
                    project=org_project,
                    open_count=0,
                    closed_count=0,
                    total_count=0,
                    milestones=[],
                    labels={},
                    error=f"az boards query failed: {result.stderr[:100]}",
                )

            work_items = json.loads(result.stdout)

            # State別にカウント
            open_count = 0
            closed_count = 0
            for wi in work_items:
                state = wi.get("fields", {}).get("System.State", "")
                if state in ("Closed", "Done", "Removed"):
                    closed_count += 1
                else:
                    open_count += 1

            # Iterations (Sprints) を取得
            iterations_result = subprocess.run(
                [
                    "az", "boards", "iteration", "project", "list",
                    "--organization", org_url,
                    "--project", project,
                    "-o", "json"
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            milestones = []
            if iterations_result.returncode == 0:
                try:
                    iterations = json.loads(iterations_result.stdout)
                    for it in iterations.get("value", iterations) if isinstance(iterations, dict) else iterations:
                        if isinstance(it, dict):
                            attrs = it.get("attributes", {})
                            milestones.append({
                                "title": it.get("name", ""),
                                "state": "active" if attrs.get("timeFrame") == "current" else "future",
                                "start_date": attrs.get("startDate", "")[:10] if attrs.get("startDate") else None,
                                "due_date": attrs.get("finishDate", "")[:10] if attrs.get("finishDate") else None,
                            })
                except json.JSONDecodeError:
                    pass

            return ProjectSummary(
                provider="Azure DevOps",
                project=org_project,
                open_count=open_count,
                closed_count=closed_count,
                total_count=open_count + closed_count,
                milestones=milestones,
                labels={},
            )

        except subprocess.TimeoutExpired:
            return ProjectSummary(
                provider="Azure DevOps",
                project=org_project,
                open_count=0,
                closed_count=0,
                total_count=0,
                milestones=[],
                labels={},
                error="Timeout: az command took too long",
            )
        except FileNotFoundError:
            return ProjectSummary(
                provider="Azure DevOps",
                project=org_project,
                open_count=0,
                closed_count=0,
                total_count=0,
                milestones=[],
                labels={},
                error="Azure CLI (az) not found. Install: https://aka.ms/installazurecliwindows",
            )
        except Exception as e:
            return ProjectSummary(
                provider="Azure DevOps",
                project=org_project,
                open_count=0,
                closed_count=0,
                total_count=0,
                milestones=[],
                labels={},
                error=str(e)[:100],
            )

    def print_summary(self, summary: ProjectSummary):
        """サマリを表示"""
        print()
        print(f"{'=' * 60}")
        print(f"  {summary.provider}: {summary.project}")
        print(f"{'=' * 60}")

        if summary.error:
            print(f"  ⚠️ Error: {summary.error}")
            return

        # Issue counts
        total = summary.total_count
        open_pct = (summary.open_count / total * 100) if total > 0 else 0
        closed_pct = (summary.closed_count / total * 100) if total > 0 else 0

        print(f"  📊 Issues/Work Items")
        print(f"     Open:   {summary.open_count:4d} ({open_pct:5.1f}%)")
        print(f"     Closed: {summary.closed_count:4d} ({closed_pct:5.1f}%)")
        print(f"     Total:  {summary.total_count:4d}")

        # Progress bar
        bar_width = 30
        closed_bars = int(closed_pct / 100 * bar_width)
        open_bars = int(open_pct / 100 * bar_width)
        bar = "█" * closed_bars + "░" * open_bars
        print(f"     [{bar}] {closed_pct:.0f}% complete")

        # Milestones
        if summary.milestones:
            print()
            print(f"  📅 Milestones/Iterations ({len(summary.milestones)})")
            for ms in sorted(summary.milestones, key=lambda x: x.get('due_date') or '9999'):
                state = "🟢" if ms.get('state') in ('open', 'active', 'current') else "⚪"
                due = ms.get('due_date') or 'N/A'
                ms_open = ms.get('open', 0)
                ms_closed = ms.get('closed', 0)
                ms_total = ms_open + ms_closed
                if ms_total > 0:
                    print(f"     {state} {ms['title'][:25]:25s} | Due: {due} | {ms_closed}/{ms_total}")
                else:
                    print(f"     {state} {ms['title'][:25]:25s} | Due: {due}")

        # Top Labels
        if summary.labels:
            print()
            print(f"  🏷️ Top Labels (open issues)")
            sorted_labels = sorted(summary.labels.items(), key=lambda x: -x[1])[:5]
            for label, count in sorted_labels:
                print(f"     {label[:20]:20s}: {count}")

    def print_comparison_table(self, summaries: List[ProjectSummary]):
        """複数プロジェクトの比較テーブル"""
        print()
        print("=" * 80)
        print("  プロジェクト同期状況サマリ")
        print("  Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("=" * 80)
        print()
        print(f"{'Provider':<12} {'Project':<35} {'Open':>6} {'Closed':>8} {'Total':>6} {'Progress':>10}")
        print("-" * 80)

        for s in summaries:
            if s.error:
                print(f"{s.provider:<12} {s.project:<35} {'ERROR: ' + s.error}")
                continue

            pct = (s.closed_count / s.total_count * 100) if s.total_count > 0 else 0
            progress = f"{pct:.0f}%"
            print(f"{s.provider:<12} {s.project:<35} {s.open_count:>6} {s.closed_count:>8} {s.total_count:>6} {progress:>10}")

        print("-" * 80)

        # Totals
        total_open = sum(s.open_count for s in summaries if not s.error)
        total_closed = sum(s.closed_count for s in summaries if not s.error)
        total_all = total_open + total_closed
        total_pct = (total_closed / total_all * 100) if total_all > 0 else 0

        print(f"{'TOTAL':<12} {'':<35} {total_open:>6} {total_closed:>8} {total_all:>6} {total_pct:.0f}%")
        print()

    def list_github_repos(self, org: str) -> List[str]:
        """GitHub 組織/ユーザーの全リポジトリを取得"""
        import subprocess
        try:
            result = subprocess.run(
                ["gh", "repo", "list", org, "--limit", "100", "--json", "name", "--jq", ".[].name"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
        except Exception:
            pass
        return []

    def list_gitlab_projects(self, user: str) -> List[str]:
        """GitLab ユーザーの全プロジェクトを取得"""
        url = f"https://gitlab.com/api/v4/users/{user}/projects?per_page=100"
        headers = {}
        if self.gitlab_token:
            headers["PRIVATE-TOKEN"] = self.gitlab_token
        data = self._request_json(url, headers)
        if data:
            return [p.get("path", p.get("name", "")) for p in data]
        return []

    def list_ado_projects(self, org: str) -> List[str]:
        """Azure DevOps 組織の全プロジェクトを取得"""
        import subprocess
        try:
            result = subprocess.run(
                ["az", "devops", "project", "list",
                 "--organization", f"https://dev.azure.com/{org}",
                 "--query", "value[].name", "-o", "tsv"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
        except Exception:
            pass
        return []

    def discover_and_compare(self, github_orgs: List[str], gitlab_users: List[str], ado_orgs: List[str], json_output: bool = False):
        """全リポジトリ/プロジェクトを発見して同期状況を比較"""
        print("🔍 全リポジトリ/プロジェクトを検索中...")
        print()

        # 各プラットフォームのリポジトリ/プロジェクトを収集
        github_repos: Dict[str, List[str]] = {}
        gitlab_projects: Dict[str, List[str]] = {}
        ado_projects: Dict[str, List[str]] = {}

        for org in github_orgs:
            print(f"  📦 GitHub ({org})...")
            github_repos[org] = self.list_github_repos(org)
            print(f"     {len(github_repos[org])} repos found")

        for user in gitlab_users:
            print(f"  📦 GitLab ({user})...")
            gitlab_projects[user] = self.list_gitlab_projects(user)
            print(f"     {len(gitlab_projects[user])} projects found")

        for org in ado_orgs:
            print(f"  📦 Azure DevOps ({org})...")
            ado_projects[org] = self.list_ado_projects(org)
            print(f"     {len(ado_projects[org])} projects found")

        # 全リポジトリ名を正規化して統合
        all_repos: Dict[str, Dict[str, str]] = {}  # normalized_name -> {github: full_path, gitlab: ..., ado: ...}

        for org, repos in github_repos.items():
            for repo in repos:
                normalized = repo.lower().replace('-', '_').replace(' ', '_')
                if normalized not in all_repos:
                    all_repos[normalized] = {"name": repo}
                all_repos[normalized]["github"] = f"{org}/{repo}"

        for user, projects in gitlab_projects.items():
            for proj in projects:
                normalized = proj.lower().replace('-', '_').replace(' ', '_')
                if normalized not in all_repos:
                    all_repos[normalized] = {"name": proj}
                all_repos[normalized]["gitlab"] = f"{user}/{proj}"

        for org, projects in ado_projects.items():
            for proj in projects:
                normalized = proj.lower().replace('-', '_').replace(' ', '_')
                if normalized not in all_repos:
                    all_repos[normalized] = {"name": proj}
                all_repos[normalized]["ado"] = f"{org}/{proj}"

        # 同期状況を分析
        print()
        print("=" * 100)
        print("  リポジトリ/プロジェクト同期状況")
        print("  Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("=" * 100)
        print()

        # ヘッダー
        print(f"{'Name':<40} {'GitHub':<20} {'GitLab':<20} {'ADO':<20}")
        print("-" * 100)

        synced = []
        partial = []
        single = []

        for normalized, info in sorted(all_repos.items()):
            name = info.get("name", normalized)
            gh = "✅" if "github" in info else "❌"
            gl = "✅" if "gitlab" in info else "❌"
            ado = "✅" if "ado" in info else "❌"

            count = sum(1 for k in ["github", "gitlab", "ado"] if k in info)

            if count == 3:
                synced.append((name, info))
            elif count == 2:
                partial.append((name, info))
            else:
                single.append((name, info))

        # 完全同期
        if synced:
            print()
            print("🟢 完全同期 (3プラットフォーム)")
            for name, info in synced:
                gh = info.get("github", "-")
                gl = info.get("gitlab", "-")
                ado = info.get("ado", "-")
                print(f"  {name:<38} {gh:<20} {gl:<20} {ado:<20}")

        # 部分同期
        if partial:
            print()
            print("🟡 部分同期 (2プラットフォーム)")
            for name, info in partial:
                gh = info.get("github", "❌")
                gl = info.get("gitlab", "❌")
                ado = info.get("ado", "❌")
                print(f"  {name:<38} {gh:<20} {gl:<20} {ado:<20}")

        # 単一プラットフォーム
        if single:
            print()
            print("🔴 未同期 (1プラットフォームのみ)")
            for name, info in single:
                gh = info.get("github", "❌")
                gl = info.get("gitlab", "❌")
                ado = info.get("ado", "❌")
                print(f"  {name:<38} {gh:<20} {gl:<20} {ado:<20}")

        # サマリ
        print()
        print("-" * 100)
        total = len(all_repos)
        print(f"合計: {total} プロジェクト")
        print(f"  🟢 完全同期: {len(synced)} ({len(synced)/total*100:.0f}%)" if total > 0 else "")
        print(f"  🟡 部分同期: {len(partial)} ({len(partial)/total*100:.0f}%)" if total > 0 else "")
        print(f"  🔴 未同期:   {len(single)} ({len(single)/total*100:.0f}%)" if total > 0 else "")
        print()

        if json_output:
            output = {
                "synced": [{"name": n, **i} for n, i in synced],
                "partial": [{"name": n, **i} for n, i in partial],
                "single": [{"name": n, **i} for n, i in single],
                "summary": {
                    "total": total,
                    "synced": len(synced),
                    "partial": len(partial),
                    "single": len(single),
                }
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="GitHub/GitLab/Azure DevOps プロジェクト同期状況サマリ"
    )
    parser.add_argument("--github", "-g", action="append", default=[],
                        help="GitHub リポジトリ (owner/repo)")
    parser.add_argument("--gitlab", "-l", action="append", default=[],
                        help="GitLab プロジェクト (owner/project)")
    parser.add_argument("--ado", "-a", action="append", default=[],
                        help="Azure DevOps プロジェクト (org/project)")
    parser.add_argument("--detail", "-d", action="store_true",
                        help="詳細表示")
    parser.add_argument("--json", "-j", action="store_true",
                        help="JSON出力")
    parser.add_argument("--discover", action="store_true",
                        help="全リポジトリ/プロジェクトを自動発見して同期状況をチェック")
    parser.add_argument("--github-orgs", action="append", default=[],
                        help="GitHub 組織/ユーザー (--discover用)")
    parser.add_argument("--gitlab-users", action="append", default=[],
                        help="GitLab ユーザー (--discover用)")
    parser.add_argument("--ado-orgs", action="append", default=[],
                        help="Azure DevOps 組織 (--discover用)")

    args = parser.parse_args()

    tool = SyncStatusTool()
    summaries: List[ProjectSummary] = []

    # --discover モードの場合
    if args.discover:
        github_orgs = args.github_orgs or ["nobu007", "jinno0"]
        gitlab_users = args.gitlab_users or ["a09097066154"]
        ado_orgs = args.ado_orgs or ["jin5770808"]

        tool.discover_and_compare(github_orgs, gitlab_users, ado_orgs, args.json)
        return

    # GitHub
    for repo in args.github:
        print(f"📡 Fetching GitHub: {repo}...")
        summaries.append(tool.get_github_summary(repo))

    # GitLab
    for project in args.gitlab:
        print(f"📡 Fetching GitLab: {project}...")
        summaries.append(tool.get_gitlab_summary(project))

    # Azure DevOps
    for org_project in args.ado:
        print(f"📡 Fetching Azure DevOps: {org_project}...")
        summaries.append(tool.get_ado_summary(org_project))

    if not summaries:
        print("No projects specified. Use --github, --gitlab, or --ado")
        return

    # Output
    if args.json:
        output = []
        for s in summaries:
            output.append({
                "provider": s.provider,
                "project": s.project,
                "open": s.open_count,
                "closed": s.closed_count,
                "total": s.total_count,
                "milestones": s.milestones,
                "error": s.error,
            })
        print(json.dumps(output, indent=2, ensure_ascii=False))
    elif args.detail:
        for s in summaries:
            tool.print_summary(s)
    else:
        tool.print_comparison_table(summaries)

        # 詳細も表示
        for s in summaries:
            tool.print_summary(s)


if __name__ == "__main__":
    main()
