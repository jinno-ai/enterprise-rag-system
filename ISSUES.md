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
`app/main.py` で `_rag_pipeline` というグローバル変数が使用されています。これはテスト時のモック化を困難にし、アプリケーションのステート管理を複雑にします。FastAPI of Dependency Injectionシステムを活用すべきです。

**タスク:**
- [ ] `get_rag_pipeline` を `Depends` で使用できる形にリファクタリングする
- [ ] グローバル変数を廃止し、`lifespan` 内で初期化したインスタンスを適切に管理する (例: `request.state` やシングルトンプロバイダの使用)

---

## Issue 6: ベクトルデータベースの移植性とインターフェース一貫性の向上

**タイトル:** VectorDBインターフェース仕様の乖離とハードコードされた依存関係の解消

**内容:**
現在、アプリケーション内で使用しているベクトルデータベースの抽象基盤（`VectorDB` 抽象クラス）およびその実装クラス群、そしてドキュメント管理API（`app/api/routes/documents.py`）の間で、設計上の仕様の乖離とハードコーディングによる技術的負債が存在します。これにより、ベクトルデータベースの容易な差し替え（ポータビリティ）という当初の設計方針が妨げられています。

具体的には、以下の課題が存在します。
1. **メソッドシグネチャの不一致:**
   - `FAISSVectorDB.search` メソッドは複数コレクション（マルチテナントなど）のサポートとして `collection` パラメータ（デフォルト `"default"`）を受け取りますが、抽象クラス `VectorDB` および `PineconeVectorDB.search` のシグネチャには `collection` パラメータが定義されていません。
   - `HybridRetriever.semantic_search` 内で `self.vector_db.search` を呼び出す際、`collection` パラメータを渡しているため、もし設定により `PineconeVectorDB` が読み込まれた場合、`TypeError`（想定外のキーワード引数）が発生しシステムがクラッシュします。
2. **APIルートでの特定のデータベース実装へのハードコード依存:**
   - ドキュメント管理API (`app/api/routes/documents.py`) 内の `/ingest`, `/upload`, `/stats` エンドポイントにおいて、ベクトルDBインスタンスを取得する際に `get_vector_db(db_type="faiss", ...)` とDBタイプが `"faiss"` にハードコードされています。
   - 本来は環境変数や `settings.vector_db_type` などの構成設定から動的にDBタイプを判定して、適切な実装インスタンスを取得すべきです。

**タスク:**
- [ ] 抽象クラス `VectorDB` および `PineconeVectorDB` の `search`, `upsert`, `delete` などのメソッドに、`collection: str = "default"` を追加し、シグネチャの完全な一致と一貫性を確保する。
- [ ] `config.py` または `Settings` クラスにベクトルデータベースの種別を指定する `vector_db_type: str = Field("faiss", env="VECTOR_DB_TYPE")` 設定を追加する。
- [ ] `app/api/routes/documents.py` 内の `get_vector_db(db_type="faiss")` の呼び出し箇所を、`settings.vector_db_type` を参照して動的に適用するように修正する。
- [ ] `PineconeVectorDB` や、将来実装予定の他のデータベース用にコレクション（名前空間）のハンドリングを実装またはプレースホルダー化し、検索エンジンの共通利用における安全な統合を検証するテストコードを実装する。
