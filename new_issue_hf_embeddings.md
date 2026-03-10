RAG システムにおいて、OpenAI などの外部 API に依存せず、マルチリンガル E5 (multilingual-e5) などのオープンソースモデルをローカル環境で実行可能にするため、HuggingFace (Sentence-Transformers) をベースとした埋め込みモデルの実装を提案します。

**背景:**
現在、`requirements.txt` には `sentence-transformers` が含まれていますが、`app/core/embeddings.py` には `OpenAIEmbeddings` と `CohereEmbeddings` の実装しかなく、ローカルモデルを利用するためのインターフェースが不足しています。

**機能要件:**
- `HuggingFaceEmbeddingModel` (または `SentenceTransformerEmbeddingModel`) クラスの追加
- `EmbeddingModel` 抽象基底クラスの要件（`embed_texts`, `embed_query`, `dimension`）を継承・実装
- GPU 利用可否の自動検知と対応 (`device='cuda'` or `'cpu'`)
- `get_embedding_model` ファクトリ関数でのローカルモデルのサポート
- モデルのキャッシュディレクトリ設定の追加 (`config.py`)

**タスク:**
- [ ] `app/core/embeddings.py` へのクラス実装
- [ ] ユニットテストの追加
- [ ] 動作確認用スクリプトの作成
