# リポジトリ統合・運用ノート

最終更新: 2026-06-13

このリポジトリの remote 構成と、計画ドキュメント群を `main` に統合した際の判断を記録する。
（旧 `CLAUDE_CODE_HANDOFF.md` / `RECOVER_AND_INTEGRATE.md` の恒久的に必要な情報のみを集約したもの。）

---

## 1. remote 構成

| remote | URL | 役割 |
|---|---|---|
| **origin** | `https://github.com/jinno-ai/enterprise-rag-system` | 本家。push 先。 |
| **nobu007** | `https://github.com/nobu007/enterprise-rag-system.git` | 旧 origin（fork）。機能実装の履歴を保持。 |

※ 以前は origin が nobu007 fork を指していたが、2026-06-13 に origin を本家 `jinno-ai` へ切り替え、旧 origin を `nobu007` として残した。重複していた `upstream` remote は削除済み。

---

## 2. `main` の現在の構成

`main` は次の 2 層で構成される。

1. **アプリ本体（nobu007 fork の 20 コミット分）**
   security hardening / caching / rate limit / cross-encoder re-ranking / 依存性注入(DI) / 構造化ログ / Prometheus メトリクス / Celery バッチ処理 / 非同期 OpenAI 呼び出し など。コードとして最も進んだ実装。
2. **計画・運用ドキュメント群（統合コミット 1 個で追加）**
   - 計画ドキュメント: `EPIC_PLANNING.md`, `FEATURES_AND_STORIES.md`, `PROJECT_SCHEDULE.md`
   - CI: `azure-pipelines.yml`
   - epic 駆動計画ツール一式: `instructions/epic_driven_planning/`
   - スケジュール用スクリプト: `scripts/auto_schedule.py`, `scripts/update_project_dates.sh`

---

## 3. 統合方針と判断理由

旧手引きは「`docs/add-project-schedule` ブランチを main に merge / rebase する」方式だったが、**そのまま実行するとアプリ本体が壊れる**ため、方式を変更した。

判明した問題:

- `docs/add-project-schedule` は本体の 20 コミットより**前の古いベース**で作られていた。merge / rebase すると本体コード（`app/core/cache.py`, `circuit_breaker.py`, `security.py`, `rate_limit.py`, `services/reranker.py`, `app/tasks/*`, `app/middleware/*`, テスト多数）が**削除**されてしまう。
- コミット `9cdae76`（"docs: ..." という名前）の実体は**リポジトリ全体の改行コード LF→CRLF 変換**で、これが全ファイル衝突の原因だった。Windows 由来の事故。
- `docs` ブランチ側の `tests/unit/test_rag_pipeline.py` 改変は**旧同期パイプライン前提**で、本体の async + Reranker 版とは非互換。適用するとテストが壊れる。

→ 採用した方式: **surgical-additive（外科的追加）**。本体（旧 origin/main = nobu007 の最新コード）を一切いじらず、`docs` ブランチにしか存在しない新規ファイルだけを追加した（全 40 ファイル、12,722 行追加・0 行削除）。

**意図的に除外したもの:**

- `app/config.py` … 本体が意図的に削除した旧 config。
- `tests/unit/test_rag_pipeline.py` の docs 側改変 … 上記のとおり非互換。
- 各ファイルの CRLF ノイズ・旧版。

---

## 4. 統合実施の記録（2026-06-13）

- 本体 `nobu007` の最新コードを土台に、上記の新規 40 ファイル + `.gitignore`（`.coverage` を ignore）を 1 コミットで追加。
- `jinno-ai/main`（当時 `8db9f32`、古い分岐状態）を、統合済み `main` で `--force-with-lease` 上書き。
  失われた中身は無し（消えたのは旧 `app/config.py` と各ファイルの旧版のみ。すべて新版で置換済み。`azure-pipelines.yml` は内容一致で保持）。

---

## 5. 補足

- 作業用ブランチ `docs/add-project-schedule`（ローカル）と、一過性の引継ぎメモ（`CLAUDE_CODE_HANDOFF.md` / `RECOVER_AND_INTEGRATE.md`）、テスト生成物 `.coverage` は統合後に削除した。
- リモート（`nobu007` / `jinno-ai`）にも `docs/add-project-schedule` ブランチが残っている。不要なら別途削除する。
