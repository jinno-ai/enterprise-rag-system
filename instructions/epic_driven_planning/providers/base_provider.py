#!/usr/bin/env python3
"""
Base Provider - プロジェクト管理ツール連携の抽象基底クラス

サポート予定:
- GitHub Projects V2
- GitLab Issues/Boards
- Azure DevOps Work Items

設計原則:
- 各プロバイダーは同じインターフェースを実装
- 差異は具象クラスで吸収
- 設定ファイルでプロバイダーを切り替え可能
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime


class ItemType(Enum):
    """作業項目タイプ"""
    EPIC = "epic"
    FEATURE = "feature"
    STORY = "story"
    TASK = "task"
    BUG = "bug"


class ItemStatus(Enum):
    """作業項目ステータス"""
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    CLOSED = "closed"


@dataclass
class WorkItem:
    """プロバイダー共通の作業項目データ"""
    id: str                           # 内部ID (F1-S1など) - レガシー互換
    title: str
    description: str
    item_type: ItemType
    priority: str                     # high, medium, low
    estimate_hours: int = 0
    status: ItemStatus = ItemStatus.BACKLOG

    # 統一キー（100プロジェクト対応）
    unified_key: Optional[str] = None  # org/repo/epic/feature/story

    # 階層関係
    parent_id: Optional[str] = None   # 親項目ID
    depends_on: List[str] = field(default_factory=list)

    # スケジュール
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None    # YYYY-MM-DD

    # メタデータ
    labels: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    assignee: Optional[str] = None
    milestone: Optional[str] = None

    # プロバイダー固有情報
    external_id: Optional[str] = None  # GitHub Issue番号など
    external_url: Optional[str] = None # 作成後のURL

    @property
    def effective_key(self) -> str:
        """使用するキー（統一キー優先、なければレガシーID）"""
        return self.unified_key or self.id

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "id": self.id,
            "unified_key": self.unified_key,
            "title": self.title,
            "description": self.description,
            "item_type": self.item_type.value,
            "priority": self.priority,
            "estimate_hours": self.estimate_hours,
            "status": self.status.value,
            "parent_id": self.parent_id,
            "depends_on": self.depends_on,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "labels": self.labels,
            "acceptance_criteria": self.acceptance_criteria,
            "assignee": self.assignee,
            "milestone": self.milestone,
            "external_id": self.external_id,
            "external_url": self.external_url,
        }


@dataclass
class SyncResult:
    """同期結果"""
    success: bool
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)  # 作成/更新された項目

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.success = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)


class BaseProvider(ABC):
    """プロジェクト管理ツール連携の抽象基底クラス"""

    def __init__(self, config: Dict[str, Any], dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self._validate_config()

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """プロバイダー名を返す"""
        pass

    @abstractmethod
    def _validate_config(self):
        """設定の検証"""
        pass

    @abstractmethod
    def authenticate(self) -> bool:
        """認証を行う"""
        pass

    @abstractmethod
    def create_item(self, item: WorkItem) -> Optional[str]:
        """作業項目を作成し、外部IDを返す"""
        pass

    @abstractmethod
    def update_item(self, item: WorkItem) -> bool:
        """作業項目を更新"""
        pass

    @abstractmethod
    def get_item(self, external_id: str) -> Optional[WorkItem]:
        """外部IDで作業項目を取得"""
        pass

    @abstractmethod
    def find_item_by_title(self, title: str) -> Optional[WorkItem]:
        """タイトルで作業項目を検索"""
        pass

    @abstractmethod
    def create_label(self, name: str, color: str = "") -> bool:
        """ラベルを作成"""
        pass

    @abstractmethod
    def create_milestone(self, name: str, due_date: Optional[str] = None) -> bool:
        """マイルストーンを作成"""
        pass

    @abstractmethod
    def add_to_project(self, external_id: str) -> Optional[str]:
        """項目をプロジェクトボードに追加し、Project Item IDを返す"""
        pass

    @abstractmethod
    def update_project_fields(
        self,
        project_item_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        estimate: Optional[int] = None,
        status: Optional[ItemStatus] = None
    ) -> bool:
        """プロジェクトボードのフィールドを更新"""
        pass

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
            all_labels.update(item.labels)
        for label in all_labels:
            self.create_label(label)

        # マイルストーン作成
        milestones = set(item.milestone for item in items if item.milestone)
        for ms in milestones:
            self.create_milestone(ms)

        # 項目を同期
        id_mapping: Dict[str, str] = {}  # internal_id -> external_id

        for item in items:
            try:
                # 統一キーまたはレガシーIDを使用
                item_key = item.effective_key

                # 既存項目を検索（タイトルまたは統一キーで検索）
                existing = self.find_item_by_title(item.title)

                if existing and existing.external_id:
                    # 更新
                    if self.update_item(item):
                        result.updated += 1
                        id_mapping[item_key] = existing.external_id
                        result.items.append({
                            "id": item.id,
                            "unified_key": item.unified_key,
                            "external_id": existing.external_id,
                            "action": "updated"
                        })
                    else:
                        result.add_warning(f"Update failed: {item_key}")
                else:
                    # 新規作成
                    external_id = self.create_item(item)
                    if external_id:
                        result.created += 1
                        id_mapping[item_key] = external_id
                        item.external_id = external_id

                        # プロジェクトボードに追加
                        project_item_id = self.add_to_project(external_id)
                        if project_item_id:
                            # フィールド更新
                            self.update_project_fields(
                                project_item_id,
                                start_date=item.start_date,
                                end_date=item.end_date,
                                estimate=item.estimate_hours
                            )

                        result.items.append({
                            "id": item.id,
                            "unified_key": item.unified_key,
                            "external_id": external_id,
                            "action": "created"
                        })
                    else:
                        result.add_error(f"Create failed: {item_key}")

            except Exception as e:
                result.add_error(f"Error processing {item.effective_key}: {str(e)}")

        return result

        return result

    def log(self, message: str):
        """ログ出力（dry-runの場合はプレフィックス付き）"""
        prefix = "[DRY-RUN] " if self.dry_run else ""
        print(f"{prefix}{message}")
