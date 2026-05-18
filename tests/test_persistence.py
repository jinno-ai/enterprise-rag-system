
import os
import shutil
import tempfile
import numpy as np
from app.core.vectordb import FAISSVectorDB

def test_faiss_persistence_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "test_faiss.bin")
        db = FAISSVectorDB(index_path=index_path)

        # Setup and save
        vectors = [[0.1, 0.2, 0.3]]
        ids = ["doc1"]
        metadata = [{"text": "Hello world", "source": "test"}]
        db.upsert(vectors, ids, metadata)
        db.save(index_path)

        # Verify files exist
        assert os.path.exists(index_path)
        assert os.path.exists(index_path + ".metadata.json")

        # Load and verify
        db2 = FAISSVectorDB(index_path=index_path)
        db2.connect()

        assert db2.index.ntotal == 1
        assert db2.metadata_store["doc1"]["text"] == "Hello world"
        assert db2.idx_to_id[0] == "doc1"
        assert db2.id_to_idx["doc1"] == 0

def test_faiss_persistence_pickle_compat():
    import pickle
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "test_faiss_pkl.bin")
        db = FAISSVectorDB(index_path=index_path)

        # Manually create a pickle metadata file
        import faiss
        db.create_index(dimension=3)
        vectors = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
        db.index.add(vectors)
        faiss.write_index(db.index, index_path)

        metadata_pkl = {
            'metadata_store': {"doc1": {"text": "Legacy data"}},
            'id_to_idx': {"doc1": 0},
            'idx_to_id': {0: "doc1"}
        }
        with open(index_path + ".metadata.pkl", 'wb') as f:
            pickle.dump(metadata_pkl, f)

        # Load and verify compat
        db2 = FAISSVectorDB(index_path=index_path)
        db2.connect()

        assert db2.index.ntotal == 1
        assert db2.metadata_store["doc1"]["text"] == "Legacy data"
        assert db2.idx_to_id[0] == "doc1"

if __name__ == "__main__":
    try:
        test_faiss_persistence_json()
        print("✅ JSON persistence test passed")
        test_faiss_persistence_pickle_compat()
        print("✅ Pickle compatibility test passed")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
