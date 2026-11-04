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

## Issue 6: 日本語形態素解析によるBM25キーワード検索精度の向上およびVectorDBインターフェース整合

**タイトル:** 日本語形態素解析によるBM25キーワード検索精度の向上およびVectorDBシグネチャの整合化

**内容:**
現在、`HybridRetriever` の BM25 キーワード検索 (`build_bm25_index` および `keyword_search`) では `re.findall(r'\w+', text.lower())` による簡易な正規表現トークナイズが行われています。この実装では、スペース区切りを持たない日本語テキストにおいて単語が適切に分かち書きされず、助詞や助動詞を含んだ長文が単一トークンと判定されたり、キーワード検索の適合率・再現率が著しく低下します。
EPIC 2 (Story 2.2: ハイブリッド検索エンジンの実装) の品質目標を満たすため、形態素解析ツール（SudachiPy や Janome など）を用いた形態素解析トークナイザーを導入し、言語に応じたトークン化を行えるようにする必要があります。

また、`VectorDB` 抽象基底クラス (`app/core/vectordb.py`) および `PineconeVectorDB.search` のメソッドシグネチャには `collection` 引数が定義されていないのに対し、`HybridRetriever.semantic_search` (`app/services/retrieval.py`) から `collection` パラメータが渡されています。このインターフェースの不整合により、Pinecone などの別実装を接続した際に `TypeError` が発生する潜在的なリスクがあるため、基底クラスおよび全VectorDB実装でシグネチャを整合化する必要があります。

**タスク:**
- [ ] `app/services/retrieval.py` のトークン分割処理において、日本語形態素解析トークナイザー（SudachiPy / Janome等）のサポートを追加する
- [ ] ドキュメント言語判定または設定パラメータに基づき、日本語と他言語でトークナイザーを適切に切り替えられるようにする
- [ ] `VectorDB` 基底クラスおよび `PineconeVectorDB` の `search` メソッドに `collection: Optional[str] = "default"` パラメータを追加し、インターフェースの整合性を担保する
- [ ] 日本語テキストに対するBM25インデックス生成・検索テストおよびVectorDBのシグネチャ整合テストを追加する
