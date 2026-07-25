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

## Issue 6: 検索精度の向上（日本語対応・再ランク付け）とAPI統合の完成

**タイトル:** 日本語RAG検索精度の向上とドキュメント管理APIの正式統合

**内容:**
本システムは現在、英語の検索を前提とした単純な正規表現トークナイズ（`re.findall`）をBM25で使用しており、日本語の検索クエリやドキュメントに対して正確なキーワードマッチングが行えません。また、ドキュメント管理・一括インジェストを行うための高性能なAPIエンドポイント（`app/api/routes/documents.py`）が用意されているにもかかわらず、現在 `app/main.py` にはモックである `ingest.py` のルーターがマウントされています。

本Issueでは、日本語の分かち書きトークナイズを導入し、Cross-Encoderによる再ランク付けを実稼働させ、さらにドキュメント管理APIの正式マウントとFAISSVectorDBのドキュメント削除機能を完成させることで、エンタープライズ品質の検索機能とAPI構造を統合・完成させます。

**タスク:**
- [ ] **日本語トークナイズの導入:**
  - `TextSplitter`（`app/services/document_loader.py`）および `HybridRetriever` の BM25 トークナイズ処理（`app/services/retrieval.py`）に形態素解析ライブラリ（JanomeやSudachi等）または日本語対応の切り替えをサポートする。
- [ ] **Rerankerの統合:**
  - `ContextCompressor`（`app/services/retrieval.py`）の `_rerank_and_truncate` メソッドにおいて、`Reranker`（`app/services/reranker.py`）を呼び出して Cross-Encoder 再ランク付けを適用する。
- [ ] **APIの正式マウントとインジェストルーターの統合:**
  - `app/main.py` においてモックの `ingest.router` のマウントを廃止し、`app/api/routes/documents.py` を正式にインポート・マウントして各種エンドポイント（`/documents/ingest`, `/documents/upload`, `/documents/stats`, `/documents/batch`等）を有効化する。
- [ ] **FAISSVectorDBの削除・検索機能の修正:**
  - `FAISSVectorDB.delete`（`app/core/vectordb.py`）がプレースホルダー（警告出力のみ）となっているため、インデックスを再構築して実際にベクトルとメタデータを削除できる機能を実装する。
  - `FAISSVectorDB.search` で `filter_dict` 引数を正しく解釈し、メタデータフィルタリング（コレクションやファイルタイプ等による絞り込み）が動作するようにロジックを修正する。
