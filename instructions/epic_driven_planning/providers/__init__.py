"""
Epic-Driven Planning Providers

サポートするプロジェクト管理ツール:
- GitHub Projects V2 (実装済み)
- GitLab Issues/Epics/Boards (実装済み)
- Azure DevOps Work Items (実装済み)
"""

from .base_provider import (
    BaseProvider,
    WorkItem,
    SyncResult,
    ItemType,
    ItemStatus,
)
from .github_provider import GitHubProvider
from .gitlab_provider import GitLabProvider
from .ado_provider import AzureDevOpsProvider


def get_provider(provider_name: str, config: dict, dry_run: bool = False) -> BaseProvider:
    """プロバイダーファクトリー"""
    providers = {
        "github": GitHubProvider,
        "gitlab": GitLabProvider,
        "azure_devops": AzureDevOpsProvider,
        "ado": AzureDevOpsProvider,
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Unknown provider: {provider_name}. Supported: {list(providers.keys())}")

    return provider_class(config, dry_run=dry_run)


__all__ = [
    "BaseProvider",
    "WorkItem",
    "SyncResult",
    "ItemType",
    "ItemStatus",
    "GitHubProvider",
    "GitLabProvider",
    "AzureDevOpsProvider",
    "get_provider",
]
