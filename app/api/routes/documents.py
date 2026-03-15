"""
Document Management API Routes

This module defines API endpoints for document ingestion and management.
Supports both synchronous and asynchronous processing modes.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from pathlib import Path
import tempfile
import os
import asyncio
import logging

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


def validate_path_safety(file_path: str) -> None:
    """
    Validate that a path doesn't contain path traversal attempts.

    Args:
        file_path: The path to validate

    Raises:
        HTTPException: If path contains traversal attempts
    """
    if ".." in file_path:
        raise HTTPException(
            status_code=400,
            detail="Invalid path: path traversal detected"
        )


class DocumentIngestRequest(BaseModel):
    """Request model for document ingestion"""
    source_path: str = Field(..., description="Path to documents to ingest")
    collection: Optional[str] = Field(None, description="Collection name")
    chunk_size: int = Field(1000, description="Chunk size for splitting")
    chunk_overlap: int = Field(200, description="Chunk overlap")
    enable_deduplication: bool = Field(False, description="Enable document deduplication")
    deduplication_strategy: str = Field("exact", description="Deduplication strategy: exact or similarity")
    # Audio transcription settings
    transcribe_audio: bool = Field(False, description="Enable automatic transcription of audio files")
    audio_model_size: str = Field("base", description="Whisper model size for audio transcription")
    audio_language: Optional[str] = Field(None, description="Language code for audio transcription (e.g., 'en', 'ja'). Auto-detect if not specified")


class DocumentIngestResponse(BaseModel):
    """Response model for document ingestion"""
    success: bool
    documents_processed: int
    chunks_created: int
    collection: str
    message: str


class DocumentStats(BaseModel):
    """Document statistics"""
    total_documents: int
    total_chunks: int
    collections: List[str]


@router.post("/ingest", response_model=DocumentIngestResponse)
async def ingest_documents(request: DocumentIngestRequest) -> DocumentIngestResponse:
    """
    Ingest documents from a directory
    
    Args:
        request: Ingestion request with source path and parameters
    
    Returns:
        DocumentIngestResponse with ingestion statistics
    """
    try:
        from app.services.document_loader import DocumentLoader, TextSplitter
        from app.services.preview import PreviewGenerator, get_preview_cache
        from app.core.embeddings import get_embedding_model
        from app.core.vectordb import get_vector_db
        from app.core.config import get_settings

        settings = get_settings()

        # Validate path safety before loading
        validate_path_safety(request.source_path)

        # Load documents
        logger.info(f"Loading documents from: {request.source_path}")
        documents = DocumentLoader.load_directory(
            request.source_path,
            transcribe_audio=request.transcribe_audio,
            audio_model_size=request.audio_model_size
        )

        if not documents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No documents found in the specified path"
            )

        # Apply deduplication if enabled
        if request.enable_deduplication:
            logger.info(f"Deduplication enabled with strategy: {request.deduplication_strategy}")
            from app.services.deduplication import get_deduplicator

            deduplicator = get_deduplicator(strategy=request.deduplication_strategy)
            documents, dedup_result = deduplicator.deduplicate(documents)

            logger.info(
                f"Deduplication complete: {dedup_result.unique_documents}/{dedup_result.total_documents} "
                f"unique documents ({dedup_result.duplicates_removed} duplicates removed)"
            )

        # Generate previews for all documents
        logger.info(f"Generating previews for {len(documents)} documents")
        preview_generator = PreviewGenerator(max_preview_length=300)
        preview_cache = get_preview_cache()

        preview_count = 0
        for doc in documents:
            try:
                preview = preview_generator.generate_preview(doc)
                preview_cache.set(preview)
                preview_count += 1
            except Exception as e:
                logger.warning(f"Failed to generate preview for {doc.doc_id}: {e}")

        logger.info(f"Successfully generated {preview_count}/{len(documents)} previews")

        # Split documents into chunks
        splitter = TextSplitter(
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap
        )
        chunks = splitter.split_documents(documents)
        
        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        embedding_model = get_embedding_model()
        texts = [chunk.content for chunk in chunks]
        embeddings = embedding_model.embed_texts(texts)
        
        # Store in vector database
        vector_db = get_vector_db(db_type="faiss", index_path="./data/faiss_index.bin")
        
        if vector_db.index is None:
            vector_db.create_index(dimension=embedding_model.dimension)
        
        ids = [chunk.doc_id for chunk in chunks]
        metadata = [chunk.metadata for chunk in chunks]
        
        vector_db.upsert(vectors=embeddings, ids=ids, metadata=metadata)
        
        # Save index
        if hasattr(vector_db, 'save'):
            vector_db.save("./data/faiss_index.bin")
        
        # Build message with deduplication info if applicable
        base_msg = f"Successfully ingested {len(documents)} documents"
        if request.enable_deduplication:
            base_msg += f" ({dedup_result.duplicates_removed} duplicates removed)"
        base_msg += f" with {preview_count} previews"

        return DocumentIngestResponse(
            success=True,
            documents_processed=len(documents),
            chunks_created=len(chunks),
            collection=request.collection or "default",
            message=base_msg
        )
    
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}"
        )


@router.post("/upload", response_model=DocumentIngestResponse)
async def upload_document(
    file: UploadFile = File(...),
    collection: Optional[str] = Form(None),
    chunk_size: int = Form(1000),
    chunk_overlap: int = Form(200),
    enable_deduplication: bool = Form(False),
    deduplication_strategy: str = Form("exact")
) -> DocumentIngestResponse:
    """
    Upload and ingest a single document

    Args:
        file: Uploaded file
        collection: Collection name
        chunk_size: Chunk size for splitting
        chunk_overlap: Chunk overlap
        enable_deduplication: Enable document deduplication against existing docs
        deduplication_strategy: Deduplication strategy (exact or similarity)

    Returns:
        DocumentIngestResponse with ingestion statistics
    """
    try:
        from app.services.document_loader import DocumentLoader, TextSplitter
        from app.core.embeddings import get_embedding_model
        from app.core.vectordb import get_vector_db
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        try:
            # Load document
            file_ext = Path(file.filename).suffix.lower()
            
            if file_ext == '.pdf':
                documents = DocumentLoader.load_pdf(tmp_path)
            elif file_ext == '.md':
                documents = [DocumentLoader.load_markdown(tmp_path)]
            elif file_ext == '.txt':
                documents = [DocumentLoader.load_text_file(tmp_path)]
            elif file_ext in {'.mp3', '.wav', '.mp4', '.m4a', '.webm', '.mpga', '.mpeg'}:
                # Audio file - transcribe it
                try:
                    documents = [DocumentLoader.load_audio(
                        tmp_path,
                        model_size="base",
                        language=None  # Auto-detect
                    )]
                except ImportError as e:
                    raise HTTPException(
                        status_code=status.HTTP_501_NOT_IMPLEMENTED,
                        detail="Audio transcription requires openai-whisper. Install with: pip install openai-whisper"
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Audio transcription failed: {str(e)}"
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file type: {file_ext}. Supported: pdf, md, txt, mp3, wav, m4a, webm, mp4"
                )

            # Apply deduplication if enabled
            if enable_deduplication:
                logger.info(f"Deduplication enabled with strategy: {deduplication_strategy}")
                from app.services.deduplication import get_deduplicator

                deduplicator = get_deduplicator(strategy=deduplication_strategy)
                documents, dedup_result = deduplicator.deduplicate(documents)

                if len(documents) == 0:
                    # All documents were duplicates
                    os.remove(tmp_path)
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Document is a duplicate and was not ingested"
                    )

                logger.info(
                    f"Deduplication complete: {dedup_result.unique_documents}/{dedup_result.total_documents} "
                    f"unique documents ({dedup_result.duplicates_removed} duplicates removed)"
                )

            # Split and embed
            splitter = TextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            chunks = splitter.split_documents(documents)
            
            embedding_model = get_embedding_model()
            texts = [chunk.content for chunk in chunks]
            embeddings = embedding_model.embed_texts(texts)
            
            # Store in vector database
            vector_db = get_vector_db(db_type="faiss", index_path="./data/faiss_index.bin")
            
            if vector_db.index is None:
                vector_db.create_index(dimension=embedding_model.dimension)
            
            ids = [chunk.doc_id for chunk in chunks]
            metadata = [chunk.metadata for chunk in chunks]
            
            vector_db.upsert(vectors=embeddings, ids=ids, metadata=metadata)
            
            if hasattr(vector_db, 'save'):
                vector_db.save("./data/faiss_index.bin")

            # Build message with deduplication info if applicable
            base_msg = f"Successfully uploaded and ingested {file.filename}"
            if enable_deduplication:
                base_msg += f" ({dedup_result.duplicates_removed} duplicate pages removed)"

            return DocumentIngestResponse(
                success=True,
                documents_processed=len(documents),
                chunks_created=len(chunks),
                collection=collection or "default",
                message=base_msg
            )
        
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )


@router.get("/stats", response_model=DocumentStats)
async def get_stats() -> DocumentStats:
    """Get statistics about ingested documents"""
    try:
        from app.core.vectordb import get_vector_db

        vector_db = get_vector_db(db_type="faiss", index_path="./data/faiss_index.bin")
        vector_db.connect()

        stats = vector_db.get_stats()

        return DocumentStats(
            total_documents=stats.get('total_vectors', 0),
            total_chunks=stats.get('total_vectors', 0),
            collections=["default"]  # TODO: Implement multi-collection support
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.post(
    "/batch",
    response_model=BatchIngestResponse,
    summary="Batch Ingest Documents / ドキュメント一括インジェスト",
    description="Submit multiple documents for asynchronous batch processing / 複数のドキュメントを非同期バッチ処理として送信します",
    response_description="Task ID for tracking progress / 進捗追跡用のタスクID",
    responses={
        202: {"description": "Task accepted and processing started / タスク受理、処理開始"},
        400: {"description": "Invalid request parameters / 不正なリクエストパラメータ"},
        500: {"description": "Failed to queue task / タスクキュー追加失敗"}
    },
    tags=["Documents"]
)
async def ingest_documents_batch(
    request: BatchIngestRequest,
    background_tasks: BackgroundTasks = None
) -> BatchIngestResponse:
    """
    Submit documents for batch processing / ドキュメントをバッチ処理に送信します

    ## Features / 機能

    - **Asynchronous Processing**: Tasks run in background using Celery / Celeryを使用した非同期処理
    - **Large Batches**: Process up to 1000 documents in one request / 1リクエストで最大1000ドキュメント処理
    - **Progress Tracking**: Monitor processing status with task ID / タスクIDで進捗をモニタリング
    - **Error Isolation**: Failed documents don't affect others / 失敗ドキュメントは他に影響しない

    ## Process / 処理フロー

    1. **Submit**: Send document list to API / APIにドキュメントリストを送信
    2. **Queue**: Task added to Celery queue / Celeryキューにタスク追加
    3. **Process**: Worker processes in background / ワーカーがバックグラウンドで処理
    4. **Track**: Check status with task_id / task_idでステータス確認

    ## Parameters / パラメータ

    - **documents**: List of documents (max 1000) / ドキュメントリスト（最大1000件）
      - **id**: Unique identifier / 一意識別子
      - **content**: Text content / テキスト内容
      - **metadata**: Optional metadata / オプションのメタデータ
    - **collection**: Collection name (default: "default") / コレクション名
    - **chunk_size**: Chunk size (100-4000, default: 1000) / チャンクサイズ
    - **chunk_overlap**: Chunk overlap (0-500, default: 200) / チャンクオーバーラップ

    ## Example Request / リクエスト例

    ```json
    {
      "documents": [
        {
          "id": "doc1",
          "content": "This is the first document...",
          "metadata": {"source": "hr-policies", "category": "benefits"}
        },
        {
          "id": "doc2",
          "content": "This is the second document...",
          "metadata": {"source": "hr-policies", "category": "leave"}
        }
      ],
      "collection": "hr-policies",
      "chunk_size": 1000,
      "chunk_overlap": 200
    }
    ```

    ## Example Response / レスポンス例

    ```json
    {
      "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "status": "PROCESSING",
      "total_documents": 2,
      "collection": "hr-policies"
    }
    ```

    ## Check Status / ステータス確認

    Use the returned `task_id` with GET `/documents/batch/{task_id}/status`

    Args:
        request: Batch ingestion request
        background_tasks: FastAPI background tasks (not used, kept for compatibility)

    Returns:
        BatchIngestResponse with task ID for tracking
    """
    try:
        from app.tasks.batch_tasks import process_document_batch

        # Validate request size
        if len(request.documents) > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch size exceeds maximum of 1000 documents"
            )

        # Validate document IDs are unique
        doc_ids = [doc.id for doc in request.documents]
        if len(doc_ids) != len(set(doc_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document IDs must be unique"
            )

        # Generate task ID
        task_id = str(uuid.uuid4())

        # Prepare documents for Celery (convert Pydantic models to dicts)
        documents_data = [
            {
                "id": doc.id,
                "content": doc.content,
                "metadata": doc.metadata
            }
            for doc in request.documents
        ]

        # Submit task to Celery
        task = process_document_batch.apply_async(
            args=[documents_data, request.collection, request.chunk_size, request.chunk_overlap],
            task_id=task_id
        )

        logger.info(
            f"Submitted batch task {task_id}: "
            f"{len(request.documents)} documents to collection '{request.collection}'"
        )

        return BatchIngestResponse(
            task_id=task_id,
            status="PROCESSING",
            total_documents=len(request.documents),
            collection=request.collection
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit batch task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue batch task: {str(e)}"
        )


@router.get(
    "/batch/{task_id}/status",
    response_model=BatchStatusResponse,
    summary="Get Batch Processing Status / バッチ処理ステータス取得",
    description="Check the progress and results of a batch processing task / バッチ処理タスクの進捗と結果を確認します",
    response_description="Task status and results if complete / タスクステータスと完了時の結果",
    responses={
        200: {"description": "Status retrieved successfully / ステータス取得成功"},
        404: {"description": "Task not found / タスクが見つからない"},
        500: {"description": "Failed to retrieve status / ステータス取得失敗"}
    },
    tags=["Documents"]
)
async def get_batch_status(task_id: str) -> BatchStatusResponse:
    """
    Get batch processing status / バッチ処理のステータスを取得します

    ## Status Values / ステータス値

    - **PENDING**: Task waiting to be processed / 処理待ち
    - **PROGRESS**: Task currently processing / 処理中
    - **SUCCESS**: Task completed successfully / 処理成功
    - **FAILURE**: Task failed / 処理失敗

    ## Result Structure / 結果構造（成功時）

    ```json
    {
      "total": 100,
      "success": 98,
      "failed": 2,
      "errors": [
        {
          "doc_id": "doc45",
          "error": "Invalid content",
          "error_type": "ValueError"
        }
      ],
      "chunks_created": 1250
    }
    ```

    ## Example / 例

    ```bash
    # Check status
    curl "http://localhost:8000/documents/batch/a1b2c3d4-e5f6-7890-abcd-ef1234567890/status"
    ```

    Args:
        task_id: Celery task ID from batch submission

    Returns:
        BatchStatusResponse with current status and results
    """
    try:
        from app.tasks.batch_tasks import process_document_batch
        from celery.result import AsyncResult

        # Get task result
        task = AsyncResult(task_id, app=process_document_batch.app)

        response_data = {
            "task_id": task_id,
            "status": task.state,
            "result": None,
            "error": None
        }

        # Handle different task states
        if task.state == 'PENDING':
            response_data["status"] = "PENDING"
        elif task.state == 'PROGRESS':
            response_data["status"] = "PROGRESS"
            response_data["result"] = task.info
        elif task.state == 'SUCCESS':
            response_data["status"] = "SUCCESS"
            response_data["result"] = task.result
        elif task.state == 'FAILURE':
            response_data["status"] = "FAILURE"
            response_data["error"] = str(task.info)
        else:
            # Handle other Celery states
            response_data["status"] = task.state

        return BatchStatusResponse(**response_data)

    except Exception as e:
        logger.error(f"Failed to get batch task status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve task status: {str(e)}"
        )


@router.get("/preview/{doc_id}")
async def get_document_preview(doc_id: str) -> Dict[str, Any]:
    """
    Get cached preview for a document.

    Args:
        doc_id: Document identifier

    Returns:
        Document preview with metadata
    """
    try:
        from app.services.preview import get_preview_cache

        cache = get_preview_cache()
        preview = cache.get(doc_id)

        if not preview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preview not found for document: {doc_id}"
            )

        return {
            "doc_id": preview.doc_id,
            "preview_text": preview.preview_text,
            "preview_length": preview.preview_length,
            "original_length": preview.original_length,
            "compression_ratio": round(preview.compression_ratio, 3),
            "key_sentences": preview.key_sentences,
            "metadata": preview.metadata,
            "generated_at": preview.generated_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get preview: {str(e)}"
        )


@router.delete("/preview/{doc_id}")
async def invalidate_document_preview(doc_id: str) -> Dict[str, Any]:
    """
    Invalidate cached preview for a document.

    Args:
        doc_id: Document identifier

    Returns:
        Status of invalidation
    """
    try:
        from app.services.preview import get_preview_cache

        cache = get_preview_cache()
        success = cache.invalidate(doc_id) if hasattr(cache, 'invalidate') else False

        return {
            "success": success,
            "doc_id": doc_id,
            "message": f"Preview for {doc_id} {'invalidated' if success else 'not found in cache'}"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invalidate preview: {str(e)}"
        )


# Async processing endpoints

class AsyncIngestRequest(BaseModel):
    """Request model for async document ingestion"""
    source_path: str = Field(..., description="Path to documents to ingest")
    collection: Optional[str] = Field(None, description="Collection name")
    chunk_size: int = Field(1000, description="Chunk size for splitting")
    chunk_overlap: int = Field(200, description="Chunk overlap")


class AsyncIngestResponse(BaseModel):
    """Response model for async document ingestion"""
    success: bool
    task_id: str
    message: str
    queue_position: Optional[int] = None


class TaskStatusResponse(BaseModel):
    """Response model for task status"""
    task_id: str
    status: str
    documents_processed: int
    chunks_created: int
    error_message: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


class TaskListResponse(BaseModel):
    """Response model for task list"""
    tasks: List[Dict[str, Any]]
    total_count: int
    queue_size: int
    active_tasks: int


@router.post("/ingest/async", response_model=AsyncIngestResponse)
async def ingest_documents_async(request: AsyncIngestRequest) -> AsyncIngestResponse:
    """
    Submit document ingestion for asynchronous background processing.

    This endpoint returns immediately with a task ID, allowing large document
    collections to be processed in the background without blocking the API.

    Args:
        request: Ingestion request with source path and parameters

    Returns:
        AsyncIngestResponse with task_id for tracking
    """
    try:
        from app.services.document_processor import get_processor

        # Validate path safety before submitting
        validate_path_safety(request.source_path)

        # Get processor and submit task
        processor = get_processor()
        task_id = await processor.submit_task(
            source_path=request.source_path,
            collection=request.collection,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap
        )

        queue_size = await processor.get_queue_size()

        return AsyncIngestResponse(
            success=True,
            task_id=task_id,
            message="Document ingestion submitted for background processing",
            queue_position=queue_size
        )

    except asyncio.QueueFull:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task queue is full. Please try again later."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit task: {str(e)}"
        )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Get the status of an async document processing task.

    Args:
        task_id: Task ID to check

    Returns:
        TaskStatusResponse with current task status
    """
    try:
        from app.services.document_processor import get_processor

        processor = get_processor()
        task_dict = await processor.get_task_status(task_id)

        if not task_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )

        return TaskStatusResponse(**task_dict)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {str(e)}"
        )


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 50
) -> TaskListResponse:
    """
    List all document processing tasks, optionally filtered by status.

    Args:
        status: Optional status filter (pending, processing, completed, failed)
        limit: Maximum number of tasks to return

    Returns:
        TaskListResponse with list of tasks
    """
    try:
        from app.services.document_processor import get_processor, TaskStatus

        processor = get_processor()

        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = TaskStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status: {status}. Must be one of: pending, processing, completed, failed"
                )

        # Get tasks
        tasks = await processor.list_tasks(status_filter=status_filter, limit=limit)

        # Get stats
        queue_size = await processor.get_queue_size()
        active_tasks = await processor.get_active_tasks_count()

        return TaskListResponse(
            tasks=tasks,
            total_count=len(tasks),
            queue_size=queue_size,
            active_tasks=active_tasks
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tasks: {str(e)}"
        )


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str) -> Dict[str, Any]:
    """
    Cancel a pending or processing task.

    Note: This is a placeholder for future implementation.
    Currently, tasks cannot be cancelled once started.

    Args:
        task_id: Task ID to cancel

    Returns:
        Cancellation confirmation
    """
    # TODO: Implement task cancellation
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Task cancellation not yet implemented"
    )


# Export endpoints

class ExportRequest(BaseModel):
    """Request model for document export"""
    content: str = Field(..., description="Document content to export")
    filename: str = Field(..., description="Output filename (without extension)")
    format: str = Field(..., description="Export format: pdf, docx, or txt")
    title: Optional[str] = Field(None, description="Optional document title")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")


class ExportResponse(BaseModel):
    """Response model for document export"""
    success: bool
    format: str
    file_size: int
    duration_ms: float
    file_path: Optional[str] = None
    error_message: Optional[str] = None


class BatchExportRequest(BaseModel):
    """Request model for batch document export"""
    documents: List[Dict[str, Any]] = Field(..., description="List of documents to export")
    format: str = Field(..., description="Export format: pdf, docx, or txt")


class SupportedFormatsResponse(BaseModel):
    """Response model for supported export formats"""
    formats: List[str]
    count: int


@router.post("/export", response_model=ExportResponse)
async def export_document(request: ExportRequest) -> ExportResponse:
    """
    Export a document to the specified format.

    Supports PDF, DOCX, and TXT export with formatting and metadata preservation.

    Args:
        request: Export request with content, filename, format, and optional metadata

    Returns:
        ExportResponse with operation status and file details

    Raises:
        HTTPException: If export format is not supported or libraries not available
    """
    try:
        from app.services.export import DocumentExporter, ExportFormat

        # Validate format
        try:
            export_format = ExportFormat(request.format.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported export format: {request.format}. Supported: pdf, docx, txt"
            )

        # Create exporter
        exporter = DocumentExporter(output_dir="./exports")

        # Export document
        result = exporter.export_document(
            content=request.content,
            filename=request.filename,
            export_format=export_format,
            metadata=request.metadata,
            title=request.title
        )

        if not result.success:
            # Distinguish validation errors from system errors
            error_detail = result.error_message or "Unknown error"
            error_lower = error_detail.lower()

            if any(keyword in error_lower for keyword in
                   ['invalid', 'unsupported', 'must be', 'required', 'content must be', 'filename must be']):
                # Client error - bad input
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_detail
                )
            else:
                # Server error - system failure
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_detail
                )

        return ExportResponse(
            success=result.success,
            format=result.format.value,
            file_size=result.file_size,
            duration_ms=result.duration_ms,
            file_path=result.file_path
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.post("/export/batch")
async def export_documents_batch(request: BatchExportRequest) -> Dict[str, Any]:
    """
    Export multiple documents in batch.

    Args:
        request: Batch export request with documents list and format

    Returns:
        Summary with results for each document

    Raises:
        HTTPException: If export format is not supported
    """
    try:
        from app.services.export import DocumentExporter, ExportFormat

        # Validate format
        try:
            export_format = ExportFormat(request.format.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported export format: {request.format}. Supported: pdf, docx, txt"
            )

        # Create exporter
        exporter = DocumentExporter(output_dir="./exports")

        # Export batch
        results = exporter.export_batch(
            documents=request.documents,
            export_format=export_format
        )

        # Summarize results
        success_count = sum(1 for r in results if r.success)
        total_size = sum(r.file_size for r in results if r.success)

        return {
            "total_documents": len(results),
            "successful": success_count,
            "failed": len(results) - success_count,
            "total_size_bytes": total_size,
            "format": request.format,
            "results": [
                {
                    "filename": r.file_path.split('/')[-1] if r.file_path else "unknown",
                    "success": r.success,
                    "error": r.error_message
                }
                for r in results
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch export failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch export failed: {str(e)}"
        )


@router.get("/export/{filename}", response_class=FileResponse)
async def download_exported_file(filename: str) -> FileResponse:
    """
    Download a previously exported document.

    Args:
        filename: Name of the file to download

    Returns:
        FileResponse with the exported file

    Raises:
        HTTPException: If file not found
    """
    try:
        file_path = Path("./exports") / filename

        # Validate path safety
        if ".." in filename or not file_path.resolve().is_relative_to(Path("./exports").resolve()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename"
            )

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Exported file not found: {filename}"
            )

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='application/octet-stream'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {str(e)}"
        )


@router.get("/export/formats", response_model=SupportedFormatsResponse)
async def get_supported_formats() -> SupportedFormatsResponse:
    """
    Get list of supported export formats.

    Returns:
        SupportedFormatsResponse with available formats
    """
    try:
        from app.services.export import DocumentExporter

        exporter = DocumentExporter()
        formats = exporter.get_supported_formats()

        return SupportedFormatsResponse(
            formats=formats,
            count=len(formats)
        )

    except Exception as e:
        logger.error(f"Failed to get supported formats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get supported formats: {str(e)}"
        )


# Deduplication endpoints

class DeduplicationStatsResponse(BaseModel):
    """Response model for deduplication statistics"""
    total_runs: int
    total_documents_processed: int
    total_duplicates_removed: int
    average_processing_time_ms: float
    last_run: Optional[Dict[str, Any]] = None


@router.get("/deduplication/stats", response_model=DeduplicationStatsResponse)
async def get_deduplication_stats() -> DeduplicationStatsResponse:
    """
    Get deduplication statistics from the current session.

    Returns statistics about documents processed and duplicates removed.

    Returns:
        DeduplicationStatsResponse with deduplication statistics
    """
    try:
        from app.services.deduplication import get_deduplicator

        # Get a deduplicator instance to retrieve stats
        deduplicator = get_deduplicator()
        stats = deduplicator.get_statistics()

        return DeduplicationStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Failed to get deduplication stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get deduplication stats: {str(e)}"
        )


@router.post("/deduplication/clear-history")
async def clear_deduplication_history() -> Dict[str, Any]:
    """
    Clear deduplication history.

    Returns:
        Status of history clearing
    """
    try:
        from app.services.deduplication import get_deduplicator

        deduplicator = get_deduplicator()
        deduplicator.clear_history()

        return {
            "success": True,
            "message": "Deduplication history cleared successfully"
        }

    except Exception as e:
        logger.error(f"Failed to clear deduplication history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear deduplication history: {str(e)}"
        )


@router.post("/deduplication/reset")
async def reset_deduplication() -> Dict[str, Any]:
    """
    Reset the deduplication system completely.

    Clears all history, hash caches, and creates a fresh deduplicator instance.
    Useful for starting a new ingestion session.

    Returns:
        Status of reset operation
    """
    try:
        from app.services.deduplication import reset_deduplicator

        reset_deduplicator()

        return {
            "success": True,
            "message": "Deduplication system reset successfully"
        }

    except Exception as e:
        logger.error(f"Failed to reset deduplication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset deduplication: {str(e)}"
        )
