#!/usr/bin/env python3
"""
LLM Integration - プロジェクト分析とEpic分解のためのLLM連携

機能:
- プロジェクトコンテキストからFeature/Story自動生成
- Claude/OpenAI API対応
- フォールバック（テンプレートベース）
"""

import os
import json
import subprocess
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """LLM設定"""
    provider: str = "claude"  # claude, openai, ollama, template
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.3


class LLMDecomposer:
    """LLMベースのEpic分解"""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self._check_availability()

    def _check_availability(self) -> bool:
        """LLM APIの利用可否を確認"""
        if self.config.provider == "claude":
            return os.environ.get("ANTHROPIC_API_KEY") is not None
        elif self.config.provider == "openai":
            return os.environ.get("OPENAI_API_KEY") is not None
        elif self.config.provider == "ollama":
            return self._check_ollama()
        return True  # template は常に利用可能

    def _check_ollama(self) -> bool:
        """Ollamaの利用可否を確認"""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def decompose_epic(
        self,
        epic_goal: str,
        epic_background: str,
        scope_in: List[str],
        scope_out: List[str],
        success_metrics: List[Dict[str, str]],
        project_context: Optional[str] = None,
        max_features: int = 5,
        max_stories_per_feature: int = 5
    ) -> Dict[str, Any]:
        """
        LLMを使ってEpicをFeature/Storyに分解

        Returns:
            {
                "features": [
                    {
                        "id": "F1",
                        "title": "...",
                        "description": "...",
                        "priority": "high",
                        "stories": [...]
                    }
                ],
                "generation_method": "llm" | "template"
            }
        """
        prompt = self._build_prompt(
            epic_goal=epic_goal,
            epic_background=epic_background,
            scope_in=scope_in,
            scope_out=scope_out,
            success_metrics=success_metrics,
            project_context=project_context,
            max_features=max_features,
            max_stories_per_feature=max_stories_per_feature
        )

        try:
            if self.config.provider == "claude":
                response = self._call_claude(prompt)
            elif self.config.provider == "openai":
                response = self._call_openai(prompt)
            elif self.config.provider == "ollama":
                response = self._call_ollama(prompt)
            else:
                return self._fallback_template(epic_goal, scope_in, max_features)

            return self._parse_response(response)
        except Exception as e:
            print(f"[WARN] LLM call failed: {e}, using template fallback")
            return self._fallback_template(epic_goal, scope_in, max_features)

    def _build_prompt(
        self,
        epic_goal: str,
        epic_background: str,
        scope_in: List[str],
        scope_out: List[str],
        success_metrics: List[Dict[str, str]],
        project_context: Optional[str],
        max_features: int,
        max_stories_per_feature: int
    ) -> str:
        """分解用プロンプトを構築"""

        metrics_text = "\n".join([
            f"  - {m.get('metric', '')}: 現在 {m.get('current', 'N/A')} → 目標 {m.get('target', 'N/A')}"
            for m in success_metrics
        ])

        scope_in_text = "\n".join([f"  - {s}" for s in scope_in])
        scope_out_text = "\n".join([f"  - {s}" for s in scope_out])

        context_section = ""
        if project_context:
            context_section = f"""
## プロジェクトコンテキスト
{project_context}
"""

        return f"""あなたはプロジェクト管理の専門家です。
以下のEpicを{max_features}個以内のFeatureに分解し、各Featureを{max_stories_per_feature}個以内のStoryに分解してください。

# Epic情報

## ゴール
{epic_goal}

## 背景
{epic_background}

## 成功指標
{metrics_text}

## スコープ（対象）
{scope_in_text}

## スコープ外（対象外）
{scope_out_text}
{context_section}

# 出力形式（JSON）

以下の形式で出力してください。コードブロックなしで、JSONのみを出力してください。

{{
  "features": [
    {{
      "id": "F1",
      "title": "具体的なFeature名（プロジェクト固有の内容を反映）",
      "description": "このFeatureの目的と範囲",
      "priority": "high",
      "milestone": "M1",
      "stories": [
        {{
          "id": "F1-S1",
          "title": "具体的なStory名",
          "description": "ユーザーストーリー形式の説明",
          "acceptance_criteria": [
            "具体的な受け入れ条件1",
            "具体的な受け入れ条件2",
            "具体的な受け入れ条件3"
          ],
          "estimate_hours": 8,
          "priority": "high",
          "depends_on": []
        }}
      ]
    }}
  ]
}}

# 注意事項
- Feature/Storyのタイトルは「基盤セットアップ」「主要機能実装」のような汎用的なものではなく、プロジェクト固有の具体的な内容にしてください
- スコープ内の項目をカバーするFeatureを作成してください
- 依存関係（depends_on）は同一Feature内のStoryIDのみ指定できます
- estimate_hoursは2〜16時間の範囲で設定してください
"""

    def _call_claude(self, prompt: str) -> str:
        """Claude APIを呼び出し"""
        try:
            import anthropic
            client = anthropic.Anthropic()

            message = client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    def _call_openai(self, prompt: str) -> str:
        """OpenAI APIを呼び出し"""
        try:
            import openai
            client = openai.OpenAI()

            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

    def _call_ollama(self, prompt: str) -> str:
        """Ollama（ローカルLLM）を呼び出し"""
        result = subprocess.run(
            ["ollama", "run", "llama3.2", prompt],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(f"Ollama failed: {result.stderr}")
        return result.stdout

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """LLMレスポンスをパース"""
        # JSON部分を抽出
        response = response.strip()

        # コードブロックを除去
        if response.startswith("```"):
            lines = response.split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.startswith("```json"):
                    in_json = True
                    continue
                elif line.startswith("```"):
                    in_json = False
                    continue
                if in_json or (not line.startswith("```")):
                    json_lines.append(line)
            response = "\n".join(json_lines)

        # JSONをパース
        try:
            data = json.loads(response)
            data["generation_method"] = "llm"
            return data
        except json.JSONDecodeError as e:
            print(f"[WARN] Failed to parse LLM response as JSON: {e}")
            raise

    def _fallback_template(
        self,
        epic_goal: str,
        scope_in: List[str],
        max_features: int
    ) -> Dict[str, Any]:
        """テンプレートベースのフォールバック"""
        features = []

        # スコープ項目をFeatureに変換
        for idx, scope_item in enumerate(scope_in[:max_features]):
            feature_id = f"F{idx + 1}"

            stories = [
                {
                    "id": f"{feature_id}-S1",
                    "title": f"{scope_item}の設計",
                    "description": f"{scope_item}の設計を行う",
                    "acceptance_criteria": [
                        "設計ドキュメントが作成されている",
                        "レビューが完了している"
                    ],
                    "estimate_hours": 4,
                    "priority": "high",
                    "depends_on": []
                },
                {
                    "id": f"{feature_id}-S2",
                    "title": f"{scope_item}の実装",
                    "description": f"{scope_item}を実装する",
                    "acceptance_criteria": [
                        "実装が完了している",
                        "テストが通過している",
                        "レビューが完了している"
                    ],
                    "estimate_hours": 8,
                    "priority": "high",
                    "depends_on": [f"{feature_id}-S1"]
                },
                {
                    "id": f"{feature_id}-S3",
                    "title": f"{scope_item}のテスト",
                    "description": f"{scope_item}のテストを作成・実行する",
                    "acceptance_criteria": [
                        "テストが作成されている",
                        "カバレッジ80%以上",
                        "全テストが通過している"
                    ],
                    "estimate_hours": 4,
                    "priority": "medium",
                    "depends_on": [f"{feature_id}-S2"]
                }
            ]

            features.append({
                "id": feature_id,
                "title": scope_item,
                "description": f"{scope_item}に関連する機能群",
                "priority": "high" if idx < 2 else "medium",
                "milestone": f"M{(idx // 2) + 1}",
                "stories": stories
            })

        return {
            "features": features,
            "generation_method": "template"
        }


# テスト用
if __name__ == "__main__":
    decomposer = LLMDecomposer(LLMConfig(provider="template"))

    result = decomposer.decompose_epic(
        epic_goal="リアルタイムエッジ検出システムのv2.0リリース",
        epic_background="YOLO v8ベースのエッジデバイス向け低遅延オブジェクト検出",
        scope_in=[
            "モデル軽量化・最適化",
            "新規デバイス対応（Jetson Orin, Apple M3）",
            "TensorRT統合強化",
            "ベンチマークスイート拡充"
        ],
        scope_out=["新しい検出アルゴリズム開発"],
        success_metrics=[
            {"metric": "推論速度", "current": "30 FPS", "target": "50+ FPS"},
            {"metric": "モデルサイズ", "current": "6MB", "target": "4MB以下"}
        ],
        max_features=4
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
