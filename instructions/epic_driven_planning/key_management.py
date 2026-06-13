"""
Unified Key Management - グローバル一意キー管理

100+プロジェクトの全要素を一意に識別するための統一キー体系。

■ 設計仕様（KEY_SPEC）
========================
キー形式:
    {org}/{repo}/{epic_id}/{feature_id}/{story_id}

桁数設定（変更時は KEY_CONFIG を編集）:
    - Epic:    E + 5桁 (E00001〜E99999) = 最大99,999件/プロジェクト
    - Feature: F + 5桁 (F00001〜F99999) = 最大99,999件/Epic
    - Story:   S + 5桁 (S00001〜S99999) = 最大99,999件/Feature
    - Task:    T + 5桁 (T00001〜T99999) = 最大99,999件/Story

理論最大容量:
    100プロジェクト × 100Epic × 100Feature × 100Story = 10億アイテム

キー例:
    jinno-ai/enterprise-rag-system/E00001/F00001/S00001

階層:
    - Organization Level: jinno-ai
    - Project Level:      jinno-ai/enterprise-rag-system
    - Epic Level:         jinno-ai/enterprise-rag-system/E00001
    - Feature Level:      jinno-ai/enterprise-rag-system/E00001/F00001
    - Story Level:        jinno-ai/enterprise-rag-system/E00001/F00001/S00001
    - Task Level:         jinno-ai/enterprise-rag-system/E00001/F00001/S00001/T00001

上限超過時の挙動:
    - KeyLimitExceededError を送出
    - 桁数を増やすには KEY_CONFIG.DIGITS を変更し、既存データをマイグレーション
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, ClassVar
from pathlib import Path
from datetime import datetime
import json
import hashlib
import re


# ============================================================
# 🔧 KEY_CONFIG: 統一キー設定（変更はここのみ）
# ============================================================
@dataclass(frozen=True)
class KeyConfig:
    """キー設定（イミュータブル）"""
    DIGITS: int = 5           # 通番の桁数（5桁 = 99999件まで）
    EPIC_PREFIX: str = "E"
    FEATURE_PREFIX: str = "F"
    STORY_PREFIX: str = "S"
    TASK_PREFIX: str = "T"
    SEPARATOR: str = "/"

    @property
    def max_number(self) -> int:
        """最大番号（5桁なら99999）"""
        return (10 ** self.DIGITS) - 1

    @property
    def format_string(self) -> str:
        """フォーマット文字列（例: ':05d'）"""
        return f":0{self.DIGITS}d"

    def format_id(self, prefix: str, number: int) -> str:
        """ID をフォーマット"""
        if number > self.max_number:
            raise KeyLimitExceededError(
                f"{prefix}の番号が上限を超えました: {number} > {self.max_number}. "
                f"KEY_CONFIG.DIGITS を {self.DIGITS + 1} に増やしてください。"
            )
        return f"{prefix}{number:{self.format_string.replace(':', '')}}"

    def parse_id(self, id_str: str) -> tuple:
        """ID をパース（プレフィックス, 番号）"""
        match = re.match(r'^([A-Z])(\d+)$', id_str)
        if not match:
            raise ValueError(f"Invalid ID format: {id_str}")
        return match.group(1), int(match.group(2))


# グローバル設定インスタンス
KEY_CONFIG = KeyConfig()


class KeyLimitExceededError(Exception):
    """キー番号の上限超過エラー"""
    pass


class KeyValidationError(Exception):
    """キー形式の検証エラー"""
    pass


@dataclass
class UnifiedKey:
    """統一キー（Epic/Feature/Story/Task 4階層対応）"""
    org: str
    repo: str
    epic_id: Optional[str] = None
    feature_id: Optional[str] = None
    story_id: Optional[str] = None
    task_id: Optional[str] = None

    @property
    def project_key(self) -> str:
        """プロジェクトレベルキー"""
        return f"{self.org}/{self.repo}"

    @property
    def epic_key(self) -> Optional[str]:
        """Epicレベルキー"""
        if not self.epic_id:
            return None
        return f"{self.project_key}/{self.epic_id}"

    @property
    def feature_key(self) -> Optional[str]:
        """Featureレベルキー"""
        if not self.feature_id:
            return self.epic_key
        return f"{self.epic_key}/{self.feature_id}"

    @property
    def story_key(self) -> Optional[str]:
        """Storyレベルキー"""
        if not self.story_id:
            return self.feature_key
        return f"{self.feature_key}/{self.story_id}"

    @property
    def task_key(self) -> Optional[str]:
        """Taskレベルキー（最も詳細）"""
        if not self.task_id:
            return self.story_key
        return f"{self.story_key}/{self.task_id}"

    @property
    def full_key(self) -> str:
        """最も詳細なキーを返す"""
        if self.task_id:
            return self.task_key
        if self.story_id:
            return self.story_key
        if self.feature_id:
            return self.feature_key
        if self.epic_id:
            return self.epic_key
        return self.project_key

    @property
    def level(self) -> str:
        """キーのレベルを返す"""
        if self.task_id:
            return "task"
        if self.story_id:
            return "story"
        if self.feature_id:
            return "feature"
        if self.epic_id:
            return "epic"
        return "project"

    @classmethod
    def from_string(cls, key_str: str) -> 'UnifiedKey':
        """文字列からキーを生成"""
        parts = key_str.split('/')
        if len(parts) < 2:
            raise KeyValidationError(f"Invalid key format: {key_str}")

        return cls(
            org=parts[0],
            repo=parts[1],
            epic_id=parts[2] if len(parts) > 2 else None,
            feature_id=parts[3] if len(parts) > 3 else None,
            story_id=parts[4] if len(parts) > 4 else None,
            task_id=parts[5] if len(parts) > 5 else None,
        )

    def to_path(self, base_dir: Path) -> Path:
        """キーをファイルシステムパスに変換"""
        path = base_dir / self.org / self.repo
        if self.epic_id:
            path = path / self.epic_id
        if self.feature_id:
            path = path / self.feature_id
        if self.story_id:
            path = path / self.story_id
        if self.task_id:
            path = path / self.task_id
        return path

    def __str__(self) -> str:
        return self.full_key

    def __hash__(self) -> int:
        return hash(self.full_key)


@dataclass
class KeyedItem:
    """統一キー付きアイテム"""
    key: UnifiedKey
    item_type: str  # "epic", "feature", "story", "task"
    title: str
    data: Dict[str, Any] = field(default_factory=dict)
    external_refs: Dict[str, str] = field(default_factory=dict)  # provider -> external_id
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": str(self.key),
            "item_type": self.item_type,
            "title": self.title,
            "data": self.data,
            "external_refs": self.external_refs,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'KeyedItem':
        return cls(
            key=UnifiedKey.from_string(d["key"]),
            item_type=d["item_type"],
            title=d["title"],
            data=d.get("data", {}),
            external_refs=d.get("external_refs", {}),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )


class KeyRegistry:
    """
    統一キーレジストリ

    全プロジェクトのキー→外部ID（Issue番号等）マッピングを管理。
    100プロジェクト×100Epic×10Feature×10Story = 1,000,000アイテムに対応。
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, KeyedItem] = {}
        self._dirty = False

    def _get_index_path(self, org: str, repo: str) -> Path:
        """プロジェクト別インデックスファイルパス"""
        return self.data_dir / org / repo / "_index.json"

    def _get_item_path(self, key: UnifiedKey) -> Path:
        """アイテム個別ファイルパス"""
        return key.to_path(self.data_dir) / "_item.json"

    def register(self, item: KeyedItem) -> None:
        """アイテムを登録"""
        key_str = str(item.key)

        # 既存アイテムの更新
        if key_str in self._cache:
            existing = self._cache[key_str]
            # external_refs をマージ
            existing.external_refs.update(item.external_refs)
            existing.data.update(item.data)
            existing.updated_at = datetime.now().isoformat()
            item = existing
        else:
            item.created_at = datetime.now().isoformat()

        self._cache[key_str] = item
        self._dirty = True

        # 個別ファイルに保存
        item_path = self._get_item_path(item.key)
        item_path.parent.mkdir(parents=True, exist_ok=True)
        item_path.write_text(
            json.dumps(item.to_dict(), ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    def get(self, key: UnifiedKey) -> Optional[KeyedItem]:
        """キーでアイテムを取得"""
        key_str = str(key)

        # キャッシュチェック
        if key_str in self._cache:
            return self._cache[key_str]

        # ファイルから読み込み
        item_path = self._get_item_path(key)
        if item_path.exists():
            data = json.loads(item_path.read_text(encoding='utf-8'))
            item = KeyedItem.from_dict(data)
            self._cache[key_str] = item
            return item

        return None

    def get_external_id(self, key: UnifiedKey, provider: str) -> Optional[str]:
        """キーから外部ID（Issue番号等）を取得"""
        item = self.get(key)
        if item:
            return item.external_refs.get(provider)
        return None

    def set_external_id(self, key: UnifiedKey, provider: str, external_id: str) -> None:
        """外部IDを設定"""
        item = self.get(key)
        if not item:
            # アイテムがなければ作成
            item = KeyedItem(
                key=key,
                item_type=key.level,
                title="",
                external_refs={provider: external_id}
            )
        else:
            item.external_refs[provider] = external_id

        self.register(item)

    def list_by_project(self, org: str, repo: str) -> List[KeyedItem]:
        """プロジェクト内の全アイテムを取得"""
        items = []
        project_dir = self.data_dir / org / repo

        if not project_dir.exists():
            return items

        for item_file in project_dir.rglob("_item.json"):
            data = json.loads(item_file.read_text(encoding='utf-8'))
            items.append(KeyedItem.from_dict(data))

        return items

    def list_all_projects(self) -> List[str]:
        """全プロジェクトキーを取得"""
        projects = []

        for org_dir in self.data_dir.iterdir():
            if org_dir.is_dir() and not org_dir.name.startswith('_'):
                for repo_dir in org_dir.iterdir():
                    if repo_dir.is_dir() and not repo_dir.name.startswith('_'):
                        projects.append(f"{org_dir.name}/{repo_dir.name}")

        return sorted(projects)

    def save_project_index(self, org: str, repo: str) -> None:
        """プロジェクトインデックスを保存"""
        items = self.list_by_project(org, repo)
        index = {
            "project_key": f"{org}/{repo}",
            "updated_at": datetime.now().isoformat(),
            "item_count": len(items),
            "items": {str(item.key): item.to_dict() for item in items}
        }

        index_path = self._get_index_path(org, repo)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )


class KeyGenerator:
    """統一キー生成器（KEY_CONFIG準拠）"""

    def __init__(self, org: str, repo: str, config: KeyConfig = None):
        self.org = org
        self.repo = repo
        self.config = config or KEY_CONFIG
        self._epic_counter = 0
        self._feature_counters: Dict[str, int] = {}
        self._story_counters: Dict[str, int] = {}
        self._task_counters: Dict[str, int] = {}

    def next_epic_key(self, epic_name: Optional[str] = None) -> UnifiedKey:
        """次のEpicキーを生成"""
        self._epic_counter += 1
        epic_id = self.config.format_id(self.config.EPIC_PREFIX, self._epic_counter)
        return UnifiedKey(
            org=self.org,
            repo=self.repo,
            epic_id=epic_id
        )

    def next_feature_key(self, epic_key: UnifiedKey) -> UnifiedKey:
        """次のFeatureキーを生成"""
        epic_str = str(epic_key)
        if epic_str not in self._feature_counters:
            self._feature_counters[epic_str] = 0

        self._feature_counters[epic_str] += 1
        feature_id = self.config.format_id(
            self.config.FEATURE_PREFIX,
            self._feature_counters[epic_str]
        )

        return UnifiedKey(
            org=self.org,
            repo=self.repo,
            epic_id=epic_key.epic_id,
            feature_id=feature_id
        )

    def next_story_key(self, feature_key: UnifiedKey) -> UnifiedKey:
        """次のStoryキーを生成"""
        feature_str = str(feature_key)
        if feature_str not in self._story_counters:
            self._story_counters[feature_str] = 0

        self._story_counters[feature_str] += 1
        story_id = self.config.format_id(
            self.config.STORY_PREFIX,
            self._story_counters[feature_str]
        )

        return UnifiedKey(
            org=self.org,
            repo=self.repo,
            epic_id=feature_key.epic_id,
            feature_id=feature_key.feature_id,
            story_id=story_id
        )

    def next_task_key(self, story_key: UnifiedKey) -> UnifiedKey:
        """次のTaskキーを生成"""
        story_str = str(story_key)
        if story_str not in self._task_counters:
            self._task_counters[story_str] = 0

        self._task_counters[story_str] += 1
        task_id = self.config.format_id(
            self.config.TASK_PREFIX,
            self._task_counters[story_str]
        )

        return UnifiedKey(
            org=self.org,
            repo=self.repo,
            epic_id=story_key.epic_id,
            feature_id=story_key.feature_id,
            story_id=story_key.story_id,
            task_id=task_id
        )

    def from_legacy_id(self, legacy_id: str, epic_id: str = None) -> UnifiedKey:
        """
        レガシーID（F1, F1-S1）から統一キーに変換

        F1     -> {org}/{repo}/{epic}/F00001
        F1-S1  -> {org}/{repo}/{epic}/F00001/S00001
        """
        if epic_id is None:
            epic_id = self.config.format_id(self.config.EPIC_PREFIX, 1)

        if '-' in legacy_id:
            # Story ID (e.g., F1-S1)
            parts = legacy_id.split('-')
            feature_num = int(parts[0][1:])
            story_num = int(parts[1][1:])
            return UnifiedKey(
                org=self.org,
                repo=self.repo,
                epic_id=epic_id,
                feature_id=self.config.format_id(self.config.FEATURE_PREFIX, feature_num),
                story_id=self.config.format_id(self.config.STORY_PREFIX, story_num)
            )
        else:
            # Feature ID (e.g., F1)
            feature_num = int(legacy_id[1:])
            return UnifiedKey(
                org=self.org,
                repo=self.repo,
                epic_id=epic_id,
                feature_id=self.config.format_id(self.config.FEATURE_PREFIX, feature_num)
            )


def migrate_legacy_decomposition(
    legacy_data: Dict[str, Any],
    org: str,
    repo: str,
    epic_id: str = None
) -> Dict[str, Any]:
    """
    レガシー形式のdecomposition.jsonを統一キー形式に変換
    """
    generator = KeyGenerator(org, repo)

    # epic_idが指定されていない場合はKEY_CONFIG準拠で生成
    if epic_id is None:
        epic_id = KEY_CONFIG.format_id(KEY_CONFIG.EPIC_PREFIX, 1)

    result = {
        "project_key": f"{org}/{repo}",
        "epic_key": f"{org}/{repo}/{epic_id}",
        "features": []
    }

    for feature in legacy_data.get("features", []):
        legacy_feature_id = feature["id"]  # e.g., "F1"
        feature_key = generator.from_legacy_id(legacy_feature_id, epic_id)

        new_feature = {
            "key": str(feature_key),
            "legacy_id": legacy_feature_id,
            "title": feature["title"],
            "description": feature.get("description", ""),
            "priority": feature.get("priority", "medium"),
            "milestone_id": feature.get("milestone_id"),
            "depends_on": [],
            "stories": []
        }

        # depends_on を変換
        for dep in feature.get("depends_on", []):
            dep_key = generator.from_legacy_id(dep, epic_id)
            new_feature["depends_on"].append(str(dep_key))

        # Stories を変換
        for story in feature.get("stories", []):
            legacy_story_id = story["id"]  # e.g., "F1-S1"
            story_key = generator.from_legacy_id(legacy_story_id, epic_id)

            new_story = {
                "key": str(story_key),
                "legacy_id": legacy_story_id,
                "title": story["title"],
                "description": story.get("description", ""),
                "acceptance_criteria": story.get("acceptance_criteria", []),
                "estimate_hours": story.get("estimate_hours", 0),
                "priority": story.get("priority", "medium"),
                "depends_on": [],
                "labels": story.get("labels", [])
            }

            # depends_on を変換
            for dep in story.get("depends_on", []):
                dep_key = generator.from_legacy_id(dep, epic_id)
                new_story["depends_on"].append(str(dep_key))

            new_feature["stories"].append(new_story)

        result["features"].append(new_feature)

    result["summary"] = {
        "total_features": len(result["features"]),
        "total_stories": sum(len(f["stories"]) for f in result["features"]),
    }

    return result
