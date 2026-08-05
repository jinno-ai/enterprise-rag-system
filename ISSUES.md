# 改善提案 (GitHub Issues)

以下の改善提案をGitHub Issueとして登録することを推奨します。

> **✅ ステータス (2026-06-13 時点): Issue 1〜5 はすべて実装済み（E-01 完了）。**
> 本ドキュメントは記録として残します。検証結果の要約:
> - **Issue 1 (テスト/CI):** ユニットテスト 278 本がグリーン。CI を実ゲート化
>   （`continue-on-error` 撤廃、`requirements-test.txt` 導入、unit を必須ジョブ化、
>   integration は外部依存のため情報ジョブ化）。→ `.github/workflows/test.yml`
> - **Issue 2 (構造化ロギング):** `app/core/logging_config.py` を導入、`print` は廃止済み。
> - **Issue 3 (AsyncIO):** `AsyncOpenAI` 採用、`RAGPipeline` は `async`、ルートは `await`。
> - **Issue 4 (セキュリティ/構成):** CORS は `settings.ALLOWED_ORIGINS`、パス等は環境変数化。
> - **Issue 5 (DI):** グローバル変数を廃止し、`app.state` + `Depends(get_rag_pipeline)` に移行。
>
> 備考: `requirements.txt` の NumPy を `>=1.24,<2` に固定（faiss-cpu 1.7.4 の ABI 対応）。

---

## Issue 1: テスト戦略の確立と実装

**タイトル:** テストカバレッジの向上とCIパイプラインの整備

**内容:**
現在、`tests/` ディレクトリが存在しますが、中身が不足しており、自動テストが機能していません。エンタープライズ品質を担保するために、以下のテストを実装する必要があります。

- **Unit Tests:** 各コンポーネント（Retriever, RAGPipeline等）の単体テスト
- **Integration Tests:** データベースやAPIを含めた結合テスト
- **CI Configuration:** GitHub Actions等での自動テスト実行設定

**タスク:**
- [ ] `pytest` の設定ファイル (`pytest.ini`) を作成する
- [ ] `app/services/rag_pipeline.py` の単体テストを作成する
- [ ] `app/api/routes/query.py` のAPIテストを作成する
- [ ] テスト実行用のドキュメントを更新する

---

## Issue 2: オブザーバビリティの向上 (構造化ロギング)

**タイトル:** `print()` 文の廃止と構造化ロギングの導入

**内容:**
現在、アプリケーションのログ出力に `print()` が多用されています。これは本番環境での監視やデバッグに適していません。標準の `logging` モジュールまたは `structlog` を導入し、JSON形式などでログを出力できるようにすべきです。

**タスク:**
- [ ] ロギング設定を行うユーティリティモジュールを作成する
- [ ] `app/main.py` および各サービス内の `print()` をロガー呼び出しに置換する
- [ ] リクエストID等をログに含め、トレーサビリティを向上させる

---

## Issue 3: 非同期処理の最適化 (AsyncIO)

**タイトル:** OpenAI API呼び出しの非同期化によるスループット向上

**内容:**
FastAPIの `async def` エンドポイント内で、同期的な `openai.chat.completions.create` メソッドが使用されています。これはイベントループをブロックし、同時リクエスト時のパフォーマンスを著しく低下させます。

**タスク:**
- [ ] `openai` クライアントを `AsyncOpenAI` に変更する
- [ ] `RAGPipeline` クラスのメソッドを `async def` にリファクタリングする
- [ ] 関連する呼び出し元（APIルート）を `await` を使用するように修正する

---

## Issue 4: セキュリティと構成管理の強化

**タイトル:** ハードコードされた設定の排除とCORS制限

**内容:**
`app/main.py` 内でCORS設定が `allow_origins=["*"]` となっています。また、ファイルパスなどが一部ハードコードされている箇所が見受けられます。これらを環境変数や設定ファイルから制御できるように修正する必要があります。

**タスク:**
- [ ] `config.py` に `ALLOWED_ORIGINS` 設定を追加する
- [ ] `app/main.py` のCORS設定を修正する
- [ ] コード内のハードコードされたパス（例: `./data/faiss_index.bin`）を設定ファイル経由で参照するように変更する

---

## Issue 5: 依存性の注入 (Dependency Injection) の適正化

**タイトル:** グローバル変数の廃止とDependency Injectionの導入

**内容:**
`app/main.py` で `_rag_pipeline` というグローバル変数が使用されています。これはテスト時のモック化を困難にし、アプリケーションのステート管理を複雑にします。FastAPIのDependency Injectionシステムを活用すべきです。

**タスク:**
- [ ] `get_rag_pipeline` を `Depends` で使用できる形にリファクタリングする
- [ ] グローバル変数を廃止し、`lifespan` 内で初期化したインスタンスを適切に管理する (例: `request.state` やシングルトンプロバイダの使用)

---

## Issue 6: 本格的なドキュメント管理APIの統合、FAISSVectorDBの削除処理実装、および設定変数への適応

**タイトル:** 動作可能なドキュメント管理APIの統合と、FAISSでのドキュメント削除対応、およびDB種類のポータビリティ強化

**内容:**
現在、`app/main.py` ではモック実装の `ingest.router` (エンドポイント `/api/v1/ingest`) がマウントされており、実際に各種ドキュメント（PDF, MD, TXT）のインジェスト、個別アップロード、バッチ処理、統計取得をこなすリッチな機能を提供する `app/api/routes/documents.py` (エンドポイント `/documents/*`) がマウントされていません。

また、`app/api/routes/documents.py` は、ベクトルデータベースを取得する際に `"faiss"` を直書き（ハードコード）しており、環境設定 (`settings.vector_db_type`) が考慮されないため、将来的に Pinecone 等の他 DB に移行する際のポータビリティが損なわれています。さらに、ローカル開発などで使われる `FAISSVectorDB` の `delete` メソッドは現在プレースホルダー（警告ログを出力するのみ）であり、実質的なドキュメント（チャンク）削除が不可能です。

本課題では、これらの問題を解消し、エンタープライズ品質のドキュメントライフサイクル管理（登録・統計・削除）を完全に実機能として統合します。

**タスク:**
- [ ] `app/main.py` にて、モックの `ingest.router` に代わり、本物のドキュメント管理APIである `app/api/routes/documents.py` の `router` をマウントする（マウントパスは整合性を保つよう適切に設定する）。
- [ ] `app/api/routes/documents.py` 内でベクトルDBインスタンスを取得する際、`db_type="faiss"` の直書きを廃止し、設定ファイルから取得する `settings.vector_db_type` を使用するように修正する。
- [ ] `app/core/vectordb.py` 内の `FAISSVectorDB.delete` メソッドを実装し、指定されたIDリストに合致するドキュメント（およびそのベクトルデータやメタデータ）を `indices` や `metadata_stores` 等から正しく削除（または再構成して削除）できるようにする。
- [ ] 削除処理の動作を検証するための単体テストを `tests/unit/` 以下に追加する。
