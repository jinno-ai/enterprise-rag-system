#!/usr/bin/env python3
"""
GitLab Mirror Sync - GitHub → GitLab リポジトリ同期

機能:
- GitHub組織のリポジトリをGitLabグループにミラーリング
- リポジトリが存在しない場合は作成
- 既存リポジトリは git push --mirror で更新

必要な認証:
- GITLAB_TOKEN 環境変数（api スコープ必須）
- gh CLI で GitHub 認証済み

使用例:
    # 環境変数でトークン設定
    export GITLAB_TOKEN="glpat-xxxxx"

    # 全リポジトリを同期
    python gitlab_mirror_sync.py --github-org jinno-ai --gitlab-group jinno-ai

    # 特定のリポジトリのみ
    python gitlab_mirror_sync.py --github-org jinno-ai --gitlab-group jinno-ai --repos ai-hub enterprise-rag-system

    # ドライラン（実際には同期しない）
    python gitlab_mirror_sync.py --github-org jinno-ai --gitlab-group jinno-ai --dry-run
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional


@dataclass
class RepoInfo:
    """リポジトリ情報"""
    name: str
    description: str
    github_url: str
    gitlab_url: Optional[str] = None
    gitlab_id: Optional[int] = None
    exists_on_gitlab: bool = False


class GitLabMirrorSync:
    """GitHub → GitLab リポジトリ同期"""

    def __init__(self, gitlab_token: str, gitlab_host: str = "https://gitlab.com"):
        self.token = gitlab_token
        self.host = gitlab_host.rstrip('/')
        self.api_base = f"{self.host}/api/v4"

    def _gitlab_api(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict] = None
    ) -> Optional[Dict]:
        """GitLab API 呼び出し"""
        url = f"{self.api_base}/{endpoint}"
        headers = {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json",
        }

        request_data = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=request_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            error_body = e.read().decode() if e.fp else ""
            print(f"[ERROR] GitLab API error: {e.code} - {error_body}", file=sys.stderr)
            raise
        except urllib.error.URLError as e:
            print(f"[ERROR] Network error: {e}", file=sys.stderr)
            raise

    def get_group_id(self, group_path: str) -> Optional[int]:
        """グループIDを取得"""
        encoded_path = urllib.parse.quote(group_path, safe='')
        result = self._gitlab_api(f"groups/{encoded_path}")
        return result.get("id") if result else None

    def get_group_projects(self, group_id: int) -> List[Dict]:
        """グループ内のプロジェクト一覧を取得"""
        projects = []
        page = 1
        while True:
            result = self._gitlab_api(f"groups/{group_id}/projects?page={page}&per_page=100")
            if not result:
                break
            projects.extend(result)
            if len(result) < 100:
                break
            page += 1
        return projects

    def get_project(self, project_path: str) -> Optional[Dict]:
        """プロジェクトを取得"""
        encoded_path = urllib.parse.quote(project_path, safe='')
        return self._gitlab_api(f"projects/{encoded_path}")

    def create_project(
        self,
        name: str,
        namespace_id: int,
        description: str = "",
        visibility: str = "private"
    ) -> Dict:
        """プロジェクトを作成"""
        data = {
            "name": name,
            "path": name.lower().replace(" ", "-"),
            "namespace_id": namespace_id,
            "description": description,
            "visibility": visibility,
            "initialize_with_readme": False,
        }
        result = self._gitlab_api("projects", method="POST", data=data)
        if not result:
            raise Exception(f"Failed to create project: {name}")
        return result

    def get_github_repos(self, org: str, repos: Optional[List[str]] = None) -> List[RepoInfo]:
        """GitHub組織のリポジトリ一覧を取得"""
        cmd = ["gh", "repo", "list", org, "--limit", "100", "--json", "name,url,description"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[ERROR] Failed to list GitHub repos: {result.stderr}", file=sys.stderr)
            return []

        github_repos = json.loads(result.stdout)
        repo_list = []

        for repo in github_repos:
            name = repo["name"]
            # 特定のリポジトリのみ処理
            if repos and name not in repos:
                continue

            repo_list.append(RepoInfo(
                name=name,
                description=repo.get("description", "") or "",
                github_url=repo["url"],
            ))

        return repo_list

    def sync_repos(
        self,
        github_org: str,
        gitlab_group: str,
        repos: Optional[List[str]] = None,
        dry_run: bool = False,
        visibility: str = "private"
    ) -> Dict[str, Any]:
        """GitHub → GitLab リポジトリ同期"""
        results = {
            "created": [],
            "updated": [],
            "skipped": [],
            "failed": [],
        }

        # GitLabグループID取得
        group_id = self.get_group_id(gitlab_group)
        if not group_id:
            print(f"[ERROR] GitLab group not found: {gitlab_group}", file=sys.stderr)
            return results

        print(f"[INFO] GitLab group: {gitlab_group} (ID: {group_id})")

        # 既存のGitLabプロジェクト一覧
        existing_projects = {p["name"]: p for p in self.get_group_projects(group_id)}
        print(f"[INFO] Existing GitLab projects: {len(existing_projects)}")

        # GitHubリポジトリ一覧
        github_repos = self.get_github_repos(github_org, repos)
        print(f"[INFO] GitHub repos to sync: {len(github_repos)}")

        for repo in github_repos:
            print(f"\n--- {repo.name} ---")

            # GitLabに既存かチェック
            gitlab_project = existing_projects.get(repo.name)
            if gitlab_project:
                repo.exists_on_gitlab = True
                repo.gitlab_id = gitlab_project["id"]
                # HTTPS URL（トークン認証付き）を使用
                repo.gitlab_url = self._get_https_url_with_token(gitlab_project["http_url_to_repo"])
                print(f"  [EXISTS] GitLab: {gitlab_project['web_url']}")
            else:
                print(f"  [NEW] Will create on GitLab")

            if dry_run:
                if repo.exists_on_gitlab:
                    results["skipped"].append(repo.name)
                else:
                    results["created"].append(repo.name)
                continue

            try:
                # プロジェクトが存在しない場合は作成
                if not repo.exists_on_gitlab:
                    print(f"  Creating GitLab project: {repo.name}")
                    created = self.create_project(
                        name=repo.name,
                        namespace_id=group_id,
                        description=repo.description,
                        visibility=visibility,
                    )
                    repo.gitlab_id = created["id"]
                    # HTTPS URL（トークン認証付き）を使用
                    repo.gitlab_url = self._get_https_url_with_token(created["http_url_to_repo"])
                    print(f"  Created: {created['web_url']}")
                    results["created"].append(repo.name)

                # Git mirror push
                print(f"  Syncing: {repo.github_url} → {repo.gitlab_url}")
                self._git_mirror_push(repo.github_url, repo.gitlab_url, github_org)
                if repo.name not in results["created"]:
                    results["updated"].append(repo.name)

            except Exception as e:
                print(f"  [FAILED] {e}", file=sys.stderr)
                results["failed"].append({"name": repo.name, "error": str(e)})

        return results

    def _get_https_url_with_token(self, http_url: str) -> str:
        """HTTPS URL にトークンを埋め込む"""
        # https://gitlab.com/group/repo.git → https://oauth2:TOKEN@gitlab.com/group/repo.git
        if http_url.startswith("https://"):
            return http_url.replace("https://", f"https://oauth2:{self.token}@")
        return http_url

    def _git_mirror_push(self, github_url: str, gitlab_url: str, github_org: str):
        """Git mirror push を実行"""
        import tempfile
        import shutil

        # 一時ディレクトリでクローン
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_name = github_url.split("/")[-1]
            clone_path = Path(tmpdir) / repo_name

            # GitHub から bare clone
            print(f"    Cloning from GitHub (bare)...")
            cmd = ["git", "clone", "--bare", github_url, str(clone_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Git clone failed: {result.stderr}")

            # GitLab へ push --mirror
            print(f"    Pushing to GitLab (mirror)...")
            cmd = ["git", "-C", str(clone_path), "push", "--mirror", gitlab_url]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                # エラーでも一部成功している場合がある
                if "error" in result.stderr.lower() and "rejected" not in result.stderr.lower():
                    raise Exception(f"Git push failed: {result.stderr}")
                print(f"    [WARN] {result.stderr.strip()}")
            else:
                print(f"    Done!")


def main():
    parser = argparse.ArgumentParser(
        description="GitHub → GitLab リポジトリ同期",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 環境変数でトークン設定
  export GITLAB_TOKEN="glpat-xxxxx"

  # 全リポジトリを同期
  python gitlab_mirror_sync.py --github-org jinno-ai --gitlab-group jinno-ai

  # 特定のリポジトリのみ
  python gitlab_mirror_sync.py --github-org jinno-ai --gitlab-group jinno-ai \\
      --repos ai-hub enterprise-rag-system

  # ドライラン
  python gitlab_mirror_sync.py --github-org jinno-ai --gitlab-group jinno-ai --dry-run
        """
    )

    parser.add_argument('--github-org', required=True, help='GitHub組織名')
    parser.add_argument('--gitlab-group', required=True, help='GitLabグループ名')
    parser.add_argument('--gitlab-host', default='https://gitlab.com', help='GitLabホスト')
    parser.add_argument('--repos', nargs='*', help='同期するリポジトリ名（省略時は全て）')
    parser.add_argument('--visibility', default='private', choices=['private', 'internal', 'public'],
                       help='新規プロジェクトの可視性')
    parser.add_argument('--dry-run', action='store_true', help='実際には同期しない')

    args = parser.parse_args()

    # GitLabトークン取得
    gitlab_token = os.environ.get('GITLAB_TOKEN', '')
    if not gitlab_token:
        print("[ERROR] GITLAB_TOKEN environment variable is required", file=sys.stderr)
        print("  Create a token at: https://gitlab.com/-/user_settings/personal_access_tokens", file=sys.stderr)
        print("  Required scopes: api, write_repository", file=sys.stderr)
        sys.exit(1)

    syncer = GitLabMirrorSync(gitlab_token, args.gitlab_host)

    print("=" * 60)
    print("GitHub → GitLab Repository Sync")
    print("=" * 60)
    print(f"GitHub Org:    {args.github_org}")
    print(f"GitLab Group:  {args.gitlab_group}")
    print(f"Repos:         {args.repos or 'ALL'}")
    print(f"Visibility:    {args.visibility}")
    print(f"Dry Run:       {args.dry_run}")
    print("=" * 60)

    results = syncer.sync_repos(
        github_org=args.github_org,
        gitlab_group=args.gitlab_group,
        repos=args.repos,
        dry_run=args.dry_run,
        visibility=args.visibility,
    )

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Created: {len(results['created'])} - {results['created']}")
    print(f"Updated: {len(results['updated'])} - {results['updated']}")
    print(f"Skipped: {len(results['skipped'])} - {results['skipped']}")
    print(f"Failed:  {len(results['failed'])} - {[f['name'] for f in results['failed']]}")

    if results['failed']:
        sys.exit(1)


if __name__ == "__main__":
    main()
