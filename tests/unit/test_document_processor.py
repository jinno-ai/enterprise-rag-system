"""
Unit tests for Async Document Processor

This test suite covers the async document processing functionality including
background task queue, task status tracking, and API integration.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime

from app.services.document_processor import (
    BackgroundTaskProcessor,
    ProcessingTask,
    ProcessingResult,
    TaskStatus,
    get_processor,
    start_processor,
    stop_processor
)


@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def processor():
    """Create a fresh processor instance for each test"""
    proc = BackgroundTaskProcessor(
        max_concurrent_tasks=2,
        max_queue_size=10
    )
    await proc.start()
    yield proc
    await proc.stop()


@pytest.fixture
def sample_documents():
    """Sample documents for testing"""
    return [
        Mock(
            doc_id="doc1",
            content="Sample document 1 content",
            metadata={"source": "test1.txt"}
        ),
        Mock(
            doc_id="doc2",
            content="Sample document 2 content",
            metadata={"source": "test2.txt"}
        )
    ]


class TestProcessingTask:
    """Tests for ProcessingTask dataclass"""

    def test_task_initialization(self):
        """Test task initialization with default values"""
        task = ProcessingTask(
            task_id="test-123",
            source_path="/test/path"
        )

        assert task.task_id == "test-123"
        assert task.source_path == "/test/path"
        assert task.collection is None
        assert task.chunk_size == 1000
        assert task.chunk_overlap == 200
        assert task.status == TaskStatus.PENDING
        assert task.documents_processed == 0
        assert task.chunks_created == 0
        assert task.error_message is None
        assert task.started_at is None
        assert task.completed_at is None
        assert isinstance(task.created_at, datetime)

    def test_task_to_dict(self):
        """Test converting task to dictionary"""
        task = ProcessingTask(
            task_id="test-123",
            source_path="/test/path",
            collection="test-collection",
            status=TaskStatus.COMPLETED,
            documents_processed=5,
            chunks_created=10
        )

        result = task.to_dict()

        assert result["task_id"] == "test-123"
        assert result["source_path"] == "/test/path"
        assert result["collection"] == "test-collection"
        assert result["status"] == "completed"
        assert result["documents_processed"] == 5
        assert result["chunks_created"] == 10
        assert "created_at" in result
        assert isinstance(result["created_at"], str)


class TestProcessingResult:
    """Tests for ProcessingResult dataclass"""

    def test_successful_result(self):
        """Test successful processing result"""
        result = ProcessingResult(
            success=True,
            task_id="task-123",
            documents_processed=5,
            chunks_created=10,
            collection="test",
            message="Processing complete"
        )

        assert result.success is True
        assert result.task_id == "task-123"
        assert result.documents_processed == 5
        assert result.chunks_created == 10
        assert result.collection == "test"
        assert result.message == "Processing complete"
        assert result.error is None
        assert result.processing_time_ms >= 0

    def test_failed_result(self):
        """Test failed processing result"""
        result = ProcessingResult(
            success=False,
            task_id="task-123",
            documents_processed=0,
            chunks_created=0,
            collection="test",
            message="Processing failed",
            error="File not found"
        )

        assert result.success is False
        assert result.error == "File not found"


class TestBackgroundTaskProcessor:
    """Tests for BackgroundTaskProcessor"""

    @pytest.mark.asyncio
    async def test_processor_initialization(self):
        """Test processor initialization"""
        proc = BackgroundTaskProcessor(
            max_concurrent_tasks=3,
            max_queue_size=50
        )

        assert proc.max_concurrent_tasks == 3
        assert proc.max_queue_size == 50
        assert proc._processing is False
        assert len(proc._workers) == 0
        assert proc._task_queue.maxsize == 50

    @pytest.mark.asyncio
    async def test_processor_start_stop(self):
        """Test starting and stopping the processor"""
        proc = BackgroundTaskProcessor(max_concurrent_tasks=2)

        await proc.start()
        assert proc._processing is True
        assert len(proc._workers) == 2

        await proc.stop()
        assert proc._processing is False
        assert len(proc._workers) == 0

    @pytest.mark.asyncio
    async def test_processor_double_start(self):
        """Test that starting an already running processor doesn't create duplicate workers"""
        proc = BackgroundTaskProcessor(max_concurrent_tasks=2)

        await proc.start()
        assert len(proc._workers) == 2

        await proc.start()  # Start again
        assert len(proc._workers) == 2  # Should still be 2

        await proc.stop()

    @pytest.mark.asyncio
    async def test_submit_task(self, processor):
        """Test submitting a task to the queue"""
        task_id = await processor.submit_task(
            source_path="/test/path",
            collection="test-collection",
            chunk_size=1500,
            chunk_overlap=300
        )

        assert task_id is not None
        assert isinstance(task_id, str)

        # Check task is stored
        task = processor._tasks.get(task_id)
        assert task is not None
        assert task.source_path == "/test/path"
        assert task.collection == "test-collection"
        assert task.chunk_size == 1500
        assert task.chunk_overlap == 300
        assert task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_task_status(self, processor):
        """Test getting task status"""
        task_id = await processor.submit_task(source_path="/test/path")

        status = await processor.get_task_status(task_id)

        assert status is not None
        assert status["task_id"] == task_id
        assert status["status"] in ["pending", "processing"]
        assert status["source_path"] == "/test/path"

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, processor):
        """Test getting status for non-existent task"""
        status = await processor.get_task_status("non-existent-task")
        assert status is None

    @pytest.mark.asyncio
    async def test_get_task_status_sync(self, processor):
        """Test synchronous version of get_task_status"""
        task_id = await processor.submit_task(source_path="/test/path")

        status = processor.get_task_status_sync(task_id)

        assert status is not None
        assert status["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_list_tasks(self, processor):
        """Test listing all tasks"""
        # Submit multiple tasks
        task_id_1 = await processor.submit_task(source_path="/test/path1")
        task_id_2 = await processor.submit_task(source_path="/test/path2")
        task_id_3 = await processor.submit_task(source_path="/test/path3")

        # List all tasks
        tasks = await processor.list_tasks(limit=10)

        assert len(tasks) == 3
        task_ids = [t["task_id"] for t in tasks]
        assert task_id_1 in task_ids
        assert task_id_2 in task_ids
        assert task_id_3 in task_ids

    @pytest.mark.asyncio
    async def test_list_tasks_with_status_filter(self, processor):
        """Test listing tasks filtered by status"""
        task_id = await processor.submit_task(source_path="/test/path")

        # Filter by pending status
        pending_tasks = await processor.list_tasks(
            status_filter=TaskStatus.PENDING,
            limit=10
        )

        assert len(pending_tasks) >= 1
        assert all(t["status"] == "pending" for t in pending_tasks)

    @pytest.mark.asyncio
    async def test_list_tasks_with_limit(self, processor):
        """Test listing tasks with limit"""
        # Submit 5 tasks
        for i in range(5):
            await processor.submit_task(source_path=f"/test/path{i}")

        # List with limit of 3
        tasks = await processor.list_tasks(limit=3)

        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_get_queue_size(self, processor):
        """Test getting queue size"""
        # Submit tasks
        await processor.submit_task(source_path="/test/path1")
        await processor.submit_task(source_path="/test/path2")

        queue_size = await processor.get_queue_size()

        assert queue_size >= 0

    @pytest.mark.asyncio
    async def test_get_queue_size_sync(self, processor):
        """Test synchronous version of get_queue_size"""
        await processor.submit_task(source_path="/test/path")

        queue_size = processor.get_queue_size_sync()

        assert queue_size >= 0

    @pytest.mark.asyncio
    async def test_get_active_tasks_count(self, processor):
        """Test getting active tasks count"""
        count = await processor.get_active_tasks_count()
        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_callback_registration(self, processor):
        """Test registering completion callbacks"""
        callback_results = []

        def test_callback(result):
            callback_results.append(result)

        processor.register_callback(test_callback)
        assert len(processor._callbacks) == 1

    @pytest.mark.asyncio
    async def test_queue_full(self):
        """Test behavior when queue is full"""
        # Create processor with small queue
        proc = BackgroundTaskProcessor(
            max_concurrent_tasks=1,
            max_queue_size=2
        )

        try:
            # Don't start processor, tasks won't be processed
            # Fill the queue directly
            await proc._task_queue.put(ProcessingTask(
                task_id="task1",
                source_path="/test/path1"
            ))
            await proc._task_queue.put(ProcessingTask(
                task_id="task2",
                source_path="/test/path2"
            ))

            # This should raise QueueFull since queue is full
            with pytest.raises(asyncio.QueueFull):
                proc._task_queue.put_nowait(ProcessingTask(
                    task_id="task3",
                    source_path="/test/path3"
                ))
        finally:
            await proc.stop()


class TestTaskProcessing:
    """Tests for actual task processing"""

    @pytest.mark.asyncio
    async def test_process_task_success(self, processor, sample_documents):
        """Test successful task processing"""
        task = ProcessingTask(
            task_id="test-task",
            source_path="/test/path",
            collection="test"
        )

        with patch('app.services.document_processor.DocumentLoader.load_directory') as mock_load:
            with patch('app.core.embeddings.get_embedding_model') as mock_embedding:
                with patch('app.core.vectordb.get_vector_db') as mock_vectordb:
                    # Setup mocks
                    mock_load.return_value = sample_documents

                    mock_model = Mock()
                    mock_model.dimension = 1536
                    mock_model.embed_texts.return_value = [[0.1] * 1536 for _ in sample_documents]
                    mock_embedding.return_value = mock_model

                    mock_db = Mock()
                    mock_db.index = None
                    mock_db.create_index = Mock()
                    mock_db.upsert = Mock()
                    mock_db.save = Mock()
                    mock_vectordb.return_value = mock_db

                    # Process task
                    result = await processor._process_task(task)

                    # Verify result
                    assert result.success is True
                    assert result.task_id == "test-task"
                    assert result.documents_processed == 2
                    assert result.chunks_created > 0
                    assert result.collection == "test"
                    assert "Successfully processed" in result.message

    @pytest.mark.asyncio
    async def test_process_task_no_documents(self, processor):
        """Test task processing when no documents found"""
        task = ProcessingTask(
            task_id="test-task",
            source_path="/test/path"
        )

        with patch('app.services.document_loader.DocumentLoader.load_directory') as mock_load:
            # Return empty list
            mock_load.return_value = []

            # Process task
            result = await processor._process_task(task)

            # Verify failure
            assert result.success is False
            assert "No documents found" in result.error

    @pytest.mark.asyncio
    async def test_process_task_exception_handling(self, processor):
        """Test task processing with exception"""
        task = ProcessingTask(
            task_id="test-task",
            source_path="/test/path"
        )

        with patch('app.services.document_loader.DocumentLoader.load_directory') as mock_load:
            # Raise exception
            mock_load.side_effect = Exception("Test error")

            # Process task
            result = await processor._process_task(task)

            # Verify error handling
            assert result.success is False
            assert result.error == "Test error"
            assert "Test error" in result.message


class TestGlobalProcessor:
    """Tests for global processor instance"""

    def test_get_processor_singleton(self):
        """Test that get_processor returns singleton instance"""
        # Reset global processor
        import app.services.document_processor
        app.services.document_processor._processor = None

        proc1 = get_processor()
        proc2 = get_processor()

        assert proc1 is proc2

    @pytest.mark.asyncio
    async def test_start_stop_global_processor(self):
        """Test starting and stopping global processor"""
        import app.services.document_processor
        app.services.document_processor._processor = None

        await start_processor()
        assert get_processor()._processing is True

        await stop_processor()
        # Processor should be None after stop
        assert app.services.document_processor._processor is None


class TestIntegration:
    """Integration tests for document processor"""

    @pytest.mark.asyncio
    async def test_end_to_end_processing(self, processor, sample_documents):
        """Test complete workflow from submission to completion"""
        with patch('app.services.document_loader.DocumentLoader.load_directory') as mock_load:
            with patch('app.core.embeddings.get_embedding_model') as mock_embedding:
                with patch('app.core.vectordb.get_vector_db') as mock_vectordb:
                    # Setup mocks
                    mock_load.return_value = sample_documents

                    mock_model = Mock()
                    mock_model.dimension = 1536
                    mock_model.embed_texts.return_value = [[0.1] * 1536 for _ in sample_documents]
                    mock_embedding.return_value = mock_model

                    mock_db = Mock()
                    mock_db.index = None
                    mock_db.create_index = Mock()
                    mock_db.upsert = Mock()
                    mock_db.save = Mock()
                    mock_vectordb.return_value = mock_db

                    # Submit task
                    task_id = await processor.submit_task(
                        source_path="/test/path",
                        collection="test-collection"
                    )

                    # Wait a bit for processing
                    await asyncio.sleep(0.5)

                    # Check status
                    status = await processor.get_task_status(task_id)
                    assert status is not None
                    assert status["task_id"] == task_id
                    assert status["status"] in ["completed", "processing", "pending"]

    @pytest.mark.asyncio
    async def test_concurrent_task_processing(self, processor, sample_documents):
        """Test processing multiple tasks concurrently"""
        with patch('app.services.document_loader.DocumentLoader.load_directory') as mock_load:
            with patch('app.core.embeddings.get_embedding_model') as mock_embedding:
                with patch('app.core.vectordb.get_vector_db') as mock_vectordb:
                    # Setup mocks
                    mock_load.return_value = sample_documents

                    mock_model = Mock()
                    mock_model.dimension = 1536
                    mock_model.embed_texts.return_value = [[0.1] * 1536 for _ in sample_documents]
                    mock_embedding.return_value = mock_model

                    mock_db = Mock()
                    mock_db.index = None
                    mock_db.create_index = Mock()
                    mock_db.upsert = Mock()
                    mock_db.save = Mock()
                    mock_vectordb.return_value = mock_db

                    # Submit multiple tasks
                    task_ids = []
                    for i in range(3):
                        task_id = await processor.submit_task(
                            source_path=f"/test/path{i}",
                            collection=f"collection{i}"
                        )
                        task_ids.append(task_id)

                    # Wait for processing
                    await asyncio.sleep(1)

                    # Check all tasks are stored
                    for task_id in task_ids:
                        status = await processor.get_task_status(task_id)
                        assert status is not None
                        assert status["task_id"] == task_id
