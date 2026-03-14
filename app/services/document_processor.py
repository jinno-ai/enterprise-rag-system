"""
Async Document Processing with Background Task Queue

This module provides asynchronous document ingestion with a background task queue
for improved performance and scalability in production environments.
"""

import asyncio
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging
from pathlib import Path

from app.services.document_loader import DocumentLoader, TextSplitter, Document


logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status of a processing task"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingTask:
    """Represents a document processing task"""
    task_id: str
    source_path: str
    collection: Optional[str] = None
    chunk_size: int = 1000
    chunk_overlap: int = 200
    status: TaskStatus = TaskStatus.PENDING
    documents_processed: int = 0
    chunks_created: int = 0
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary"""
        return {
            "task_id": self.task_id,
            "source_path": self.source_path,
            "collection": self.collection,
            "status": self.status.value,
            "documents_processed": self.documents_processed,
            "chunks_created": self.chunks_created,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class ProcessingResult:
    """Result of a document processing task"""
    success: bool
    task_id: str
    documents_processed: int
    chunks_created: int
    collection: str
    message: str
    error: Optional[str] = None
    processing_time_ms: float = 0


class BackgroundTaskProcessor:
    """
    Async background task processor for document ingestion.

    This processor manages a queue of document processing tasks and executes
    them asynchronously in the background, allowing the API to return immediately
    while processing continues.
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 3,
        max_queue_size: int = 100
    ):
        """
        Initialize the background task processor.

        Args:
            max_concurrent_tasks: Maximum number of tasks to process concurrently
            max_queue_size: Maximum number of tasks to keep in the queue
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.max_queue_size = max_queue_size
        self._task_queue: asyncio.Queue[ProcessingTask] = asyncio.Queue(maxsize=max_queue_size)
        self._tasks: Dict[str, ProcessingTask] = {}
        self._processing = False
        self._workers: List[asyncio.Task] = []
        self._callbacks: List[Callable[[ProcessingResult], None]] = []

    async def start(self) -> None:
        """Start the background processor and worker tasks"""
        if self._processing:
            logger.warning("Background processor already running")
            return

        self._processing = True
        logger.info(f"Starting background task processor with {self.max_concurrent_tasks} workers")

        # Start worker tasks
        for i in range(self.max_concurrent_tasks):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)

        logger.info(f"Started {len(self._workers)} worker tasks")

    async def stop(self) -> None:
        """Stop the background processor gracefully"""
        if not self._processing:
            return

        logger.info("Stopping background task processor...")
        self._processing = False

        # Cancel all workers
        for worker in self._workers:
            worker.cancel()

        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        logger.info("Background task processor stopped")

    async def submit_task(
        self,
        source_path: str,
        collection: Optional[str] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> str:
        """
        Submit a document processing task to the queue.

        Args:
            source_path: Path to documents to process
            collection: Collection name for the documents
            chunk_size: Chunk size for splitting
            chunk_overlap: Chunk overlap

        Returns:
            Task ID for tracking

        Raises:
            asyncio.QueueFull: If the queue is full
        """
        import uuid

        task_id = str(uuid.uuid4())
        task = ProcessingTask(
            task_id=task_id,
            source_path=source_path,
            collection=collection,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        # Store task
        self._tasks[task_id] = task

        # Add to queue
        await self._task_queue.put(task)

        logger.info(f"Task {task_id} submitted for processing")
        return task_id

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a processing task.

        Args:
            task_id: Task ID to check

        Returns:
            Task status dictionary or None if task not found
        """
        task = self._tasks.get(task_id)
        if not task:
            return None

        return task.to_dict()

    def get_task_status_sync(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Synchronous version of get_task_status.

        Args:
            task_id: Task ID to check

        Returns:
            Task status dictionary or None if task not found
        """
        task = self._tasks.get(task_id)
        if not task:
            return None

        return task.to_dict()

    async def list_tasks(
        self,
        status_filter: Optional[TaskStatus] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List all tasks, optionally filtered by status.

        Args:
            status_filter: Optional status filter
            limit: Maximum number of tasks to return

        Returns:
            List of task dictionaries
        """
        tasks = list(self._tasks.values())

        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]

        # Sort by created_at (newest first)
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        # Apply limit
        tasks = tasks[:limit]

        return [task.to_dict() for task in tasks]

    def register_callback(self, callback: Callable[[ProcessingResult], None]) -> None:
        """
        Register a callback to be called when a task completes.

        Args:
            callback: Function to call with processing result
        """
        self._callbacks.append(callback)

    async def _worker(self, worker_name: str) -> None:
        """
        Worker task that processes documents from the queue.

        Args:
            worker_name: Name of the worker for logging
        """
        logger.info(f"Worker {worker_name} started")

        while self._processing:
            try:
                # Get task from queue with timeout
                task = await asyncio.wait_for(
                    self._task_queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            logger.info(f"{worker_name}: Processing task {task.task_id}")

            # Process the task
            result = await self._process_task(task)

            # Update task status
            self._tasks[task.task_id] = task

            # Call callbacks
            for callback in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")

            # Mark queue task as done
            self._task_queue.task_done()

            logger.info(f"{worker_name}: Task {task.task_id} completed with status: {result.success}")

        logger.info(f"Worker {worker_name} stopped")

    async def _process_task(self, task: ProcessingTask) -> ProcessingResult:
        """
        Process a single document ingestion task.

        Args:
            task: Task to process

        Returns:
            Processing result
        """
        import time

        start_time = time.time()
        task.status = TaskStatus.PROCESSING
        task.started_at = datetime.utcnow()

        try:
            # Import here to avoid circular imports
            from app.core.embeddings import get_embedding_model
            from app.core.vectordb import get_vector_db

            # Load documents
            logger.info(f"Loading documents from: {task.source_path}")
            documents = DocumentLoader.load_directory(task.source_path)

            if not documents:
                raise ValueError("No documents found in the specified path")

            # Split documents
            splitter = TextSplitter(
                chunk_size=task.chunk_size,
                chunk_overlap=task.chunk_overlap
            )
            chunks = splitter.split_documents(documents)

            # Generate embeddings
            logger.info(f"Generating embeddings for {len(chunks)} chunks")
            embedding_model = get_embedding_model()
            texts = [chunk.content for chunk in chunks]
            embeddings = embedding_model.embed_texts(texts)

            # Store in vector database
            vector_db = get_vector_db(
                db_type="faiss",
                index_path="./data/faiss_index.bin"
            )

            if vector_db.index is None:
                vector_db.create_index(dimension=embedding_model.dimension)

            ids = [chunk.doc_id for chunk in chunks]
            metadata = [chunk.metadata for chunk in chunks]

            vector_db.upsert(vectors=embeddings, ids=ids, metadata=metadata)

            # Save index
            if hasattr(vector_db, 'save'):
                vector_db.save("./data/faiss_index.bin")

            # Update task
            task.status = TaskStatus.COMPLETED
            task.documents_processed = len(documents)
            task.chunks_created = len(chunks)
            task.completed_at = datetime.utcnow()

            processing_time = (time.time() - start_time) * 1000

            result = ProcessingResult(
                success=True,
                task_id=task.task_id,
                documents_processed=len(documents),
                chunks_created=len(chunks),
                collection=task.collection or "default",
                message=f"Successfully processed {len(documents)} documents",
                processing_time_ms=processing_time
            )

            logger.info(f"Task {task.task_id} completed successfully")
            return result

        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")

            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.utcnow()

            processing_time = (time.time() - start_time) * 1000

            return ProcessingResult(
                success=False,
                task_id=task.task_id,
                documents_processed=task.documents_processed,
                chunks_created=task.chunks_created,
                collection=task.collection or "default",
                message=f"Processing failed: {str(e)}",
                error=str(e),
                processing_time_ms=processing_time
            )

    async def get_queue_size(self) -> int:
        """Get the current queue size"""
        return self._task_queue.qsize()

    def get_queue_size_sync(self) -> int:
        """Synchronous version of get_queue_size"""
        return self._task_queue.qsize()

    async def get_active_tasks_count(self) -> int:
        """Get the number of currently processing tasks"""
        return sum(
            1 for task in self._tasks.values()
            if task.status == TaskStatus.PROCESSING
        )


# Global processor instance
_processor: Optional[BackgroundTaskProcessor] = None


def get_processor() -> BackgroundTaskProcessor:
    """
    Get the global background task processor instance.

    Returns:
        BackgroundTaskProcessor instance
    """
    global _processor
    if _processor is None:
        _processor = BackgroundTaskProcessor()
    return _processor


async def start_processor() -> None:
    """Start the global background task processor"""
    processor = get_processor()
    await processor.start()


async def stop_processor() -> None:
    """Stop the global background task processor"""
    global _processor
    if _processor is not None:
        await _processor.stop()
        _processor = None
