"""
Integration tests for Enterprise RAG System

These tests verify end-to-end functionality of the RAG pipeline with robust mocking.
"""

import pytest
import tempfile
import os
from unittest.mock import patch, Mock
from app.services.retrieval import RetrievalResult, HybridRetriever
from app.services.rag_pipeline import RAGPipeline, RAGResponse


@pytest.fixture
def temp_vector_db():
    """Create temporary vector database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "test_index.bin")
        yield index_path


@pytest.fixture
def sample_documents():
    """Sample documents for testing"""
    return [
        {
            "text": "Machine learning is a subset of artificial intelligence.",
            "metadata": {"source": "doc1.pdf", "page": 1}
        },
        {
            "text": "Deep learning uses neural networks.",
            "metadata": {"source": "doc2.pdf", "page": 1}
        }
    ]


def test_rag_pipeline_end_to_end(temp_vector_db, sample_documents, mocker):
    """Test complete RAG pipeline with mocks"""
    from app.core.vectordb import get_vector_db
    from app.core.embeddings import get_embedding_model

    # Mock OpenAI
    mock_embed = mocker.patch('app.core.embeddings.openai.embeddings.create')
    mock_chat = mocker.patch('app.services.rag_pipeline.openai.chat.completions.create')

    mock_embed.return_value.data = [Mock(embedding=[0.1] * 1536)]
    mock_chat.return_value.choices = [Mock(message=Mock(content="Machine learning is AI."))]
    mock_chat.return_value.usage.total_tokens = 50

    # Initialize components
    vector_db = get_vector_db(db_type="faiss", index_path=temp_vector_db)
    vector_db.connect()

    embedding_model = get_embedding_model()
    if vector_db.index is None:
        vector_db.create_index(dimension=1536)

    # Ingest
    vector_db.upsert(
        vectors=[[0.1]*1536, [0.2]*1536],
        ids=["doc1", "doc2"],
        metadata=[doc["metadata"] for doc in sample_documents]
    )

    retriever = HybridRetriever(vector_db=vector_db, embedding_model=embedding_model)
    pipeline = RAGPipeline(retriever=retriever, llm_model="gpt-4")

    # Execute
    response = pipeline.query("What is machine learning?")

    assert isinstance(response, RAGResponse)
    assert "Machine learning" in response.answer
    assert response.latency_ms > 0


def test_vector_db_operations(temp_vector_db, sample_documents, mocker):
    """Test vector database operations"""
    from app.core.vectordb import get_vector_db
    from app.core.embeddings import get_embedding_model

    # Mock embedding
    mock_embed = mocker.patch('app.core.embeddings.openai.embeddings.create')
    mock_embed.return_value.data = [Mock(embedding=[0.1] * 1536) for _ in sample_documents]

    vector_db = get_vector_db(db_type="faiss", index_path=temp_vector_db)
    vector_db.connect()
    if vector_db.index is None:
        vector_db.create_index(dimension=1536)

    # Test add documents
    texts = [doc["text"] for doc in sample_documents]
    embeddings = [[0.1]*1536 for _ in texts]
    vector_db.add_documents(
        documents=texts,
        embeddings=embeddings,
        metadatas=[doc["metadata"] for doc in sample_documents]
    )

    # Test search
    mock_embed.return_value.data = [Mock(embedding=[0.1] * 1536)]
    query_embedding = [0.1] * 1536
    results = vector_db.search(query_embedding, top_k=1)

    assert len(results) == 1
    assert results[0].text in texts


def test_hybrid_retrieval(temp_vector_db, sample_documents, mocker):
    """Test hybrid retrieval"""
    from app.core.vectordb import get_vector_db
    from app.core.embeddings import get_embedding_model

    mocker.patch('app.core.embeddings.openai.embeddings.create')

    vector_db = get_vector_db(db_type="faiss", index_path=temp_vector_db)
    vector_db.connect()
    if vector_db.index is None:
        vector_db.create_index(dimension=1536)

    # Manual upsert
    vector_db.upsert(
        vectors=[[0.1]*1536],
        ids=["id1"],
        metadata=[{"text": "Sample text", "source": "s1"}]
    )

    embedding_model = get_embedding_model()
    retriever = HybridRetriever(vector_db=vector_db, embedding_model=embedding_model)

    # Mock embed_query for search
    mocker.patch.object(embedding_model, 'embed_query', return_value=[0.1]*1536)

    results = retriever.retrieve("test", top_k=1)
    assert len(results) == 1


def test_context_compression():
    """Test context compression"""
    from app.services.retrieval import ContextCompressor
    compressor = ContextCompressor(max_tokens=50)

    results = [
        RetrievalResult(document="Long text " * 100, score=0.9, metadata={"filename": "doc.pdf"})
    ]
    compressed = compressor.compress("query", results)
    assert len(compressed) < len(results[0].document)


def test_batch_query(mocker):
    """Test batch query"""
    from app.core.vectordb import get_vector_db

    vector_db = get_vector_db(db_type="faiss")
    vector_db.create_index(dimension=1536)
    vector_db.upsert([[0.1]*1536], ["id1"], [{"text": "text", "source": "s1"}])

    mock_retriever = Mock(spec=HybridRetriever)
    mock_retriever.retrieve.return_value = [
        RetrievalResult(document="text", score=0.9, metadata={"source": "s1"})
    ]

    mocker.patch('app.services.rag_pipeline.openai.chat.completions.create')
    pipeline = RAGPipeline(retriever=mock_retriever)

    responses = pipeline.batch_query(["q1", "q2"])
    assert len(responses) == 2


def test_retrieval_with_filters(temp_vector_db, mocker):
    """Test retrieval with metadata filters"""
    from app.core.vectordb import get_vector_db

    vector_db = get_vector_db(db_type="faiss", index_path=temp_vector_db)
    vector_db.create_index(dimension=1536)

    # Add two docs, one with tech, one with business
    vector_db.upsert(
        vectors=[[0.1]*1536, [0.2]*1536],
        ids=["id1", "id2"],
        metadata=[
            {"category": "tech", "text": "tech text"},
            {"category": "business", "text": "biz text"}
        ]
    )

    # Search for tech
    results = vector_db.search(query_vector=[0.1]*1536, top_k=10, filter_dict={"category": "tech"})
    assert len(results) == 1
    assert results[0].metadata["category"] == "tech"


def test_confidence_calculation():
    """Test confidence calculation"""
    pipeline = RAGPipeline(retriever=Mock())
    results = [RetrievalResult(document="text", score=0.9, metadata={})]
    confidence = pipeline._calculate_confidence(results, "Long answer text " * 20)
    assert confidence > 0.5
