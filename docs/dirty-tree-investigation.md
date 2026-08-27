# Working-tree停滞 (dirty 3.1日) の原因究明 — 2026-08-28

対象: 2026-08-27 の Investigate run「ワークツリーが3.1日 dirty のまま停滞している」に対する究明報告。
結論と再発防止のみを記録する（経緯の詳細は git 履歴参照）。

## 結論

13件の未コミット変更は **2026-03-15 14:59–15:20 に同一セッションで生成された Feature 36/44/49 の実装一式** であり、
そのセッションは最終検証 (`pytest --cov`) の実行直後にコミットstepまで到達せず終了した。
以降 2026-08-28 04:11 の復旧コミット (c6ac66b) まで **約5.5ヶ月間、本リポジトリに対する実行が一度も走らなかった** ため、
誰もこの dirty state を収束させなかった。

## 証拠 (実測)

| 証拠 | 値 |
|------|-----|
| 直前の連続コミット | 2026-03-15 11:48–14:57 (Feature 8/12/18/21 + 音声書き起こし) |
| 13ファイルの mtime | 2026-03-15 14:59:32 (docs/api.md) ～ 15:20:23 (.coverage) |
| 最古と最新の関係 | 最終書き込みが `.coverage` = セッション最後の処理がカバレッジ付きテスト実行だったことを示す |
| 次のコミット | 2026-08-28 04:11 c6ac66b (harness による leftover 回収) |
| 13エントリの内訳 | Feature 49: `app/api/docs.py`, `docs/api.md` / Feature 44: `app/core/encryption.py` / Feature 36: `app/services/ranking.py` + 3テストファイル + `README.md`, `requirements.txt`, `app/main.py`, `query.py`, `document_loader.py`, `.coverage` |

## 停滞を長引かせた構造要因

1. **生成物の git 追跡**: `.coverage` / `coverage.json` がテスト生成物であるにもかかわらず tracked だった
   (`.gitignore` にエントリなし)。`pytest.ini` の addopts が毎回 `--cov` を付けるため、
   テストを実行するたびに dirty が再発生する。
2. **共有ツリーでの実行**: 該当セッションは run 専用 worktree ではなくメインツリーで作業し、
   異常終了時に変更が残留した。
3. **収束トリガーの不在**: dirty が残っていても後続 run が動かなければ検出・回収される機会がない。

## 再発防止 (本コミットで実施)

- `.gitignore` に `.coverage`, `.coverage.*`, `coverage.json`, `htmlcov/` を追加し、
  `git rm --cached` で tracked から除去 → 今後テスト実行でツリーが汚れない。
- 併せて回収済み変更の品質問題を修正:
  - `app/core/encryption.py`: 到達不能な `encrypt` 本体の重複定義 (旧 L147–L184) を削除。
  - `app/api/routes/query.py`: ranking 統合の `zip(sources, retrieval_results)` が
    長さ不一致時に source を黙って切り捨てる問題を、index ベースの安全なペアリングに変更
    (回帰テスト `tests/unit/test_api_routes.py::TestQueryRankingIntegration` 追加)。
