# Issue 6: 設定管理の強化: ベクターデータベース設定のハードコード排除

**タイトル:** 設定管理の強化: ベクターデータベース設定のハードコード排除

**内容:**
`app/main.py` の `lifespan` 関数内で、ベクターデータベースの初期化に関する設定 (`db_type` と `index_path`) がハードコードされています。これにより、設定の変更が困難になり、異なる環境へのデプロイ時にコードの修正が必要となります。

**現在のコード:**
```python
# app/main.py

...
        vector_db = get_vector_db(
            db_type="faiss",
            index_path="./data/faiss_index.bin"
        )
...
```

**課題:**
- **柔軟性の欠如:** FAISS以外のベクターデータベース（例: Pinecone, Weaviate）に切り替える際や、インデックスファイルの場所を変更する際に、コードの直接的な編集が必要になる。
- **ポータビリティの低下:** Docker環境や他のマシンで実行する際に、パスの不整合が発生する可能性がある。
- **設定の一元管理違反:** 他の設定は `app/core/config.py` で管理されているにもかかわらず、この部分だけがコード内に埋め込まれている。

**提案:**
これらの設定値を `app/core/config.py` に移動し、環境変数から読み込めるように修正すべきです。

**タスク:**
- [ ] `app/core/config.py` の `Settings` クラスに `vector_db_type` と `vector_db_path` を追加する。
- [ ] `.env.example` に対応する環境変数を追加する。
- [ ] `app/main.py` の `lifespan` 関数内で、ハードコードされた値を `settings` オブジェクトから読み込むように修正する。
