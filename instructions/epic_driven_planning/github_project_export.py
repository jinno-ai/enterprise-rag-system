#!/usr/bin/env python3
"""
GitHub Project V2 Exporter - Project items -> WorkItem JSON

Exports GitHub Project items into a WorkItem-compatible JSON list for project_sync.py.

Usage:
  python github_project_export.py --config config.yaml --output output/work_items.json
"""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def run_gh(args: List[str], check: bool = True) -> str:
    """Run gh CLI and return stdout."""
    cmd = ["gh"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def run_graphql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """Run GitHub GraphQL query via gh api graphql."""
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        args.extend(["-F", f"{key}={value}"])
    output = run_gh(args)
    if not output:
        return {}
    return json.loads(output)


def load_config(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def map_item_type(value: Optional[str], labels: List[str]) -> str:
    if value:
        key = normalize_key(value)
        if key in {"epic", "epics"}:
            return "epic"
        if key in {"feature", "features"}:
            return "feature"
        if key in {"story", "userstory", "userstories"}:
            return "story"
        if key in {"task", "tasks"}:
            return "task"
        if key in {"bug", "bugs", "defect"}:
            return "bug"
    # fallback from labels
    label_keys = {normalize_key(l) for l in labels}
    if "epic" in label_keys:
        return "epic"
    if "feature" in label_keys:
        return "feature"
    if "story" in label_keys:
        return "story"
    if "task" in label_keys:
        return "task"
    if "bug" in label_keys or "defect" in label_keys:
        return "bug"
    return "story"


def map_priority(value: Optional[str], labels: List[str]) -> str:
    def pick(val: str) -> Optional[str]:
        key = normalize_key(val)
        if key in {"high", "p0", "p1", "critical", "urgent"}:
            return "high"
        if key in {"medium", "p2", "normal"}:
            return "medium"
        if key in {"low", "p3", "p4", "minor"}:
            return "low"
        return None

    if value:
        mapped = pick(value)
        if mapped:
            return mapped

    for label in labels:
        mapped = pick(label)
        if mapped:
            return mapped

    return "medium"


def map_status(value: Optional[str]) -> str:
    if not value:
        return "backlog"
    key = normalize_key(value)
    if key in {"todo", "backlog", "new"}:
        return "todo"
    if key in {"inprogress", "doing", "active"}:
        return "in_progress"
    if key in {"review", "inreview", "qa", "testing"}:
        return "in_review"
    if key in {"done", "closed", "completed", "resolved"}:
        return "done"
    return "backlog"


def extract_field_values(field_nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for node in field_nodes:
        typename = node.get("__typename")
        field = node.get("field") or {}
        field_name = field.get("name")
        if not field_name:
            continue
        if typename == "ProjectV2ItemFieldSingleSelectValue":
            values[field_name] = node.get("name")
        elif typename == "ProjectV2ItemFieldTextValue":
            values[field_name] = node.get("text")
        elif typename == "ProjectV2ItemFieldNumberValue":
            values[field_name] = node.get("number")
        elif typename == "ProjectV2ItemFieldDateValue":
            values[field_name] = node.get("date")
        elif typename == "ProjectV2ItemFieldIterationValue":
            values[field_name] = node.get("title")
    return values


def build_description(body: str, url: Optional[str], labels: List[str]) -> str:
    parts = []
    if body:
        parts.append(body)
    if labels:
        parts.append("\nLabels:\n" + "\n".join(f"- {l}" for l in labels))
    if url:
        parts.append(f"\nSource: {url}")
    return "\n\n".join(p for p in parts if p).strip()


def export_items(
    config: Dict[str, Any],
    include_drafts: bool = False,
    include_prs: bool = False,
) -> List[Dict[str, Any]]:
    github = config.get("project", {}).get("github", {})
    owner = github.get("owner")
    project_number = github.get("project_number")
    repo = github.get("repo", "")
    if not owner or not project_number:
        raise ValueError("project.github.owner and project.github.project_number are required")

    export_cfg = config.get("github_export", {})
    type_field = export_cfg.get("type_field", "Type")
    status_field = export_cfg.get("status_field", "Status")
    priority_field = export_cfg.get("priority_field", "Priority")
    estimate_field = export_cfg.get("estimate_field", "Estimate")
    start_date_field = export_cfg.get("start_date_field", "Start Date")
    end_date_field = export_cfg.get("end_date_field", "End Date")

    query = """
    query($owner: String!, $number: Int!, $after: String) {
      user(login: $owner) {
        projectV2(number: $number) {
          id
          title
          items(first: 50, after: $after) {
            nodes {
              id
              content {
                __typename
                ... on Issue {
                  id
                  number
                  title
                  body
                  url
                  labels(first: 50) { nodes { name } }
                  assignees(first: 10) { nodes { login } }
                  milestone { title }
                }
                ... on PullRequest {
                  id
                  number
                  title
                  body
                  url
                  labels(first: 50) { nodes { name } }
                  assignees(first: 10) { nodes { login } }
                }
                ... on DraftIssue {
                  title
                  body
                }
              }
              fieldValues(first: 50) {
                nodes {
                  __typename
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field { ... on ProjectV2SingleSelectField { name } }
                  }
                  ... on ProjectV2ItemFieldTextValue {
                    text
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                  ... on ProjectV2ItemFieldNumberValue {
                    number
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                  ... on ProjectV2ItemFieldDateValue {
                    date
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                  ... on ProjectV2ItemFieldIterationValue {
                    title
                    startDate
                    duration
                    field { ... on ProjectV2IterationField { name } }
                  }
                }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
      organization(login: $owner) {
        projectV2(number: $number) {
          id
          title
          items(first: 50, after: $after) {
            nodes {
              id
              content {
                __typename
                ... on Issue {
                  id
                  number
                  title
                  body
                  url
                  labels(first: 50) { nodes { name } }
                  assignees(first: 10) { nodes { login } }
                  milestone { title }
                }
                ... on PullRequest {
                  id
                  number
                  title
                  body
                  url
                  labels(first: 50) { nodes { name } }
                  assignees(first: 10) { nodes { login } }
                }
                ... on DraftIssue {
                  title
                  body
                }
              }
              fieldValues(first: 50) {
                nodes {
                  __typename
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field { ... on ProjectV2SingleSelectField { name } }
                  }
                  ... on ProjectV2ItemFieldTextValue {
                    text
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                  ... on ProjectV2ItemFieldNumberValue {
                    number
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                  ... on ProjectV2ItemFieldDateValue {
                    date
                    field { ... on ProjectV2FieldCommon { name } }
                  }
                  ... on ProjectV2ItemFieldIterationValue {
                    title
                    startDate
                    duration
                    field { ... on ProjectV2IterationField { name } }
                  }
                }
              }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    """

    items: List[Dict[str, Any]] = []
    after: Optional[str] = None

    while True:
        data = run_graphql(query, {"owner": owner, "number": int(project_number), "after": after})
        project = None
        if data.get("data", {}).get("user", {}).get("projectV2"):
            project = data["data"]["user"]["projectV2"]
        elif data.get("data", {}).get("organization", {}).get("projectV2"):
            project = data["data"]["organization"]["projectV2"]

        if not project:
            raise RuntimeError("Project not found. Check owner/project_number and permissions.")

        nodes = project.get("items", {}).get("nodes", [])
        for node in nodes:
            content = node.get("content") or {}
            ctype = content.get("__typename")
            if ctype in {"Issue", "PullRequest"}:
                if ctype == "PullRequest" and not include_prs:
                    continue
                title = content.get("title") or ""
                body = content.get("body") or ""
                url = content.get("url")
                labels = [l["name"] for l in content.get("labels", {}).get("nodes", [])]
                assignees = [a["login"] for a in content.get("assignees", {}).get("nodes", [])]
                milestone = content.get("milestone", {})
                milestone_title = milestone.get("title") if milestone else None
                number = content.get("number")
                item_id = f"GH-{number}" if number is not None else node.get("id")
            elif ctype == "DraftIssue":
                if not include_drafts:
                    continue
                title = content.get("title") or "(draft)"
                body = content.get("body") or ""
                url = None
                labels = []
                assignees = []
                milestone_title = None
                item_id = f"DRAFT-{node.get('id')}"
            else:
                # Unknown/unsupported content type
                continue

            fields = extract_field_values(node.get("fieldValues", {}).get("nodes", []))

            item_type = map_item_type(fields.get(type_field), labels)
            priority = map_priority(fields.get(priority_field), labels)
            status = map_status(fields.get(status_field))

            estimate_raw = fields.get(estimate_field)
            estimate_hours = 0
            if isinstance(estimate_raw, (int, float)):
                estimate_hours = int(estimate_raw)
            else:
                try:
                    estimate_hours = int(float(str(estimate_raw))) if estimate_raw else 0
                except ValueError:
                    estimate_hours = 0

            start_date = fields.get(start_date_field)
            end_date = fields.get(end_date_field)

            labels_with_meta = list(labels)
            if number is not None:
                labels_with_meta.append(f"github:{number}")
            if repo:
                labels_with_meta.append(f"repo:{repo}")

            description = build_description(body, url, labels)

            items.append({
                "id": item_id,
                "title": title,
                "description": description,
                "item_type": item_type,
                "priority": priority,
                "estimate_hours": estimate_hours,
                "status": status,
                "labels": labels_with_meta,
                "assignee": assignees[0] if assignees else None,
                "milestone": milestone_title,
                "start_date": start_date,
                "end_date": end_date,
                "acceptance_criteria": [],
                "depends_on": [],
                "parent_id": None,
            })

        page_info = project.get("items", {}).get("pageInfo", {})
        if page_info.get("hasNextPage"):
            after = page_info.get("endCursor")
        else:
            break

    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Export GitHub Project items to WorkItem JSON")
    parser.add_argument("--config", "-c", required=True, help="Config YAML path")
    parser.add_argument("--output", "-o", required=True, help="Output JSON path")
    parser.add_argument("--include-drafts", action="store_true", help="Include draft items")
    parser.add_argument("--include-prs", action="store_true", help="Include pull requests")

    args = parser.parse_args()

    config = load_config(Path(args.config))
    items = export_items(
        config,
        include_drafts=args.include_drafts,
        include_prs=args.include_prs,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Exported {len(items)} items -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
