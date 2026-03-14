"""
Query API Routes

This module defines API endpoints for querying the RAG system.
"""

import logging
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from app.services.rag_pipeline import RAGResponse, RAGPipeline
from app.api.dependencies import get_rag_pipeline
from app.core.rate_limit import limiter
from app.services.streaming import create_streaming_response
from app.services.metadata_search import MetadataSearchService, MetadataFilter, FilterOperator
from app.services.suggestion import QuerySuggestionService, SuggestionRequest, get_suggestion_service


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    """Request model for query endpoint"""
    query: str = Field(..., description="The question to ask", min_length=1)
    collection: Optional[str] = Field(None, description="Collection/namespace to search in")
    top_k: int = Field(5, description="Number of documents to retrieve", ge=1, le=20)
    use_hybrid: bool = Field(True, description="Use hybrid search (semantic + keyword)")
    rerank: bool = Field(True, description="Apply cross-encoder re-ranking for better accuracy")
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters")
    enable_autocorrect: bool = Field(False, description="Enable query spell correction")
    user_id: Optional[str] = Field(None, description="Optional user identifier for query tracking")


class QueryResponse(BaseModel):
    """Response model for query endpoint"""
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    latency_ms: int
    tokens_used: int


class BatchQueryRequest(BaseModel):
    """Request model for batch query endpoint"""
    queries: List[str] = Field(..., description="List of questions to ask")
    collection: Optional[str] = Field(None, description="Collection/namespace to search in")
    top_k: int = Field(5, description="Number of documents to retrieve", ge=1, le=20)
    use_hybrid: bool = Field(True, description="Use hybrid search (semantic + keyword)")
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters")
    user_id: Optional[str] = Field(None, description="Optional user identifier for query tracking")


@router.post(
    "/",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute RAG Query / RAGクエリ実行",
    description="Perform semantic search and retrieve relevant context, then generate answer using LLM / セマンティック検索を行い関連コンテキストを取得した後、LLMを使用して回答を生成します",
    response_description="Generated answer with retrieved context and metadata / 取得したコンテキストとメタデータを含む生成された回答",
    responses={
        200: {"description": "Successful query / クエリ成功"},
        400: {"description": "Invalid request parameters / 不正なリクエストパラメータ"},
        422: {"description": "Validation error / バリデーションエラー"},
        429: {"description": "Rate limit exceeded / レート制限超過"},
        500: {"description": "Internal server error / サーバー内部エラー"}
    },
    tags=["Query"]
)
@limiter.limit("60/minute")
async def query(
    request: Request,
    query_req: QueryRequest,
    pipeline: RAGPipeline = Depends(get_rag_pipeline)
) -> QueryResponse:
    """
    Query the RAG system with a question / RAGシステムに質問をクエリします

    ## Features / 機能

    - **Semantic Search**: Vector similarity search for relevant documents / セマンティック検索: 関連ドキュメントのベクトル類似度検索
    - **Hybrid Search**: Combines semantic and keyword search / ハイブリッド検索: セマンティック検索とキーワード検索の組み合わせ
    - **Re-ranking**: Cross-encoder re-ranking for better accuracy / 再ランク付け: より高い精度のためのクロスエンコーダーによる再ランク付け
    - **Multi-collection**: Search across different document collections / マルチコレクション: 異なるドキュメントコレクションの検索

    ## Parameters / パラメータ

    - **query**: Search query text (1-1000 characters) / 検索クエリテキスト (1-1000文字)
    - **collection**: Target collection name (default: "default") / 対象コレクション名 (デフォルト: "default")
    - **top_k**: Number of results to return (1-20) / 返却する結果数 (1-20)
    - **use_hybrid**: Enable hybrid search (default: true) / ハイブリッド検索を有効化 (デフォルト: true)
    - **rerank**: Apply re-ranking (default: true) / 再ランク付けを適用 (デフォルト: true)
    - **filters**: Optional metadata filters / オプションのメタデータフィルター

    ## Example / 例

    ```json
    {
      "query": "What is Retrieval-Augmented Generation?",
      "collection": "default",
      "top_k": 5,
      "use_hybrid": true,
      "rerank": true,
      "filters": null
    }
    ```

    Args:
        request: FastAPI Request object
        query_req: Query request with question and parameters
        pipeline: RAG pipeline injected via dependency injection

    Returns:
        QueryResponse with answer and sources
    """
    try:
        # Apply autocorrect if enabled
        from app.services.autocorrect import AutocorrectService
        from app.services.suggestion import get_suggestion_service

        suggestion_service = get_suggestion_service()

        query_to_process = query_req.query
        if query_req.enable_autocorrect:
            autocorrect_service = AutocorrectService()
            autocorrect_result = autocorrect_service.correct(query_req.query)
            query_to_process = autocorrect_result.corrected

            # Log corrections if any were made
            if autocorrect_result.was_corrected:
                logger.info(
                    f"Query autocorrected: '{query_req.query}' -> '{query_to_process}'",
                    extra={
                        "original": query_req.query,
                        "corrected": query_to_process,
                        "corrections": autocorrect_result.corrections
                    }
                )

        # Execute query
        result = await pipeline.query(
            question=query_to_process,
            top_k=query_req.top_k,
            use_hybrid=query_req.use_hybrid,
            filter_dict=query_req.filters,
            rerank=query_req.rerank,
            collection=query_req.collection or "default"
        )

        # Track query for future suggestions
        try:
            suggestion_service.track_query(query_req.query, query_req.user_id)
        except Exception as tracking_error:
            # Don't fail the query if tracking fails
            logger.warning(f"Query tracking failed: {tracking_error}")

        return QueryResponse(
            answer=result.answer,
            sources=result.sources,
            confidence=result.confidence,
            latency_ms=result.latency_ms,
            tokens_used=result.tokens_used
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {str(e)}"
        )


@router.post(
    "/batch",
    response_model=List[QueryResponse],
    summary="Execute Batch RAG Queries / バッチRAGクエリ実行",
    description="Query the RAG system with multiple questions in a single request / 単一のリクエストで複数の質問をRAGシステムにクエリします",
    response_description="List of generated answers with retrieved context / 取得したコンテキストを含む生成された回答のリスト",
    responses={
        200: {"description": "Successful batch query / バッチクエリ成功"},
        400: {"description": "Invalid request parameters / 不正なリクエストパラメータ"},
        422: {"description": "Validation error / バリデーションエラー"},
        429: {"description": "Rate limit exceeded / レート制限超過"},
        500: {"description": "Internal server error / サーバー内部エラー"}
    },
    tags=["Query"]
)
@limiter.limit("60/minute")
async def batch_query(
    request: Request,
    batch_req: BatchQueryRequest,
    pipeline: RAGPipeline = Depends(get_rag_pipeline)
) -> List[QueryResponse]:
    """
    Query the RAG system with multiple questions / 複数の質問をRAGシステムにクエリします

    ## Use Cases / 使用例

    - **Bulk Processing**: Process multiple questions efficiently / 一括処理: 複数の質問を効率的に処理
    - **Comparison**: Compare answers for similar questions / 比較: 類似した質問の回答を比較
    - **Testing**: Validate system behavior with multiple inputs / テスト: 複数の入力でシステムの動作を検証

    ## Parameters / パラメータ

    - **queries**: List of search query texts / 検索クエリテキストのリスト
    - **collection**: Target collection name / 対象コレクション名
    - **top_k**: Number of results per query / クエリごとの結果数

    ## Example / 例

    ```json
    {
      "queries": [
        "What is RAG?",
        "How does vector search work?",
        "Explain cross-encoder re-ranking"
      ],
      "collection": "default",
      "top_k": 5
    }
    ```

    Args:
        request: FastAPI Request object
        batch_req: Batch query request
        pipeline: RAG pipeline injected via dependency injection

    Returns:
        List of QueryResponse objects
    """
    try:
        from app.services.suggestion import get_suggestion_service

        suggestion_service = get_suggestion_service()


        # Execute batch query
        results = await pipeline.batch_query(
            questions=batch_req.queries,
            top_k=batch_req.top_k,
            collection=batch_req.collection or "default",
            use_hybrid=batch_req.use_hybrid,
            filter_dict=batch_req.filters
        )

        # Track all queries for future suggestions
        for query in batch_req.queries:
            try:
                suggestion_service.track_query(query, batch_req.user_id)
            except Exception as tracking_error:
                # Don't fail the batch if tracking fails
                logger.warning(f"Query tracking failed for batch query: {tracking_error}")


        responses = []
        for result in results:
            responses.append(QueryResponse(
                answer=result.answer,
                sources=result.sources,
                confidence=result.confidence,
                latency_ms=result.latency_ms,
                tokens_used=result.tokens_used
            ))

        return responses

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch query failed: {str(e)}"
        )


@router.post("/stream")
async def query_stream(request: QueryRequest):
    """
    Query the RAG system with streaming response using Server-Sent Events (SSE)

    This endpoint streams the query response in real-time, providing:
    - Retrieval status and results
    - Progressive answer generation (token-by-token using real OpenAI streaming)
    - Final metadata (confidence, tokens, sources)

    Args:
        request: Query request with question and parameters

    Returns:
        StreamingResponse with SSE format

    Example:
        ```python
        import requests

        response = requests.post(
            "http://localhost:8000/api/v1/query/stream",
            json={"query": "What is the company policy?", "top_k": 5},
            stream=True
        )

        for line in response.iter_lines():
            if line:
                print(line.decode('utf-8'))
        ```
    """
    try:
        from app.main import get_rag_pipeline
        from fastapi import Request

        pipeline = get_rag_pipeline()

        # Create streaming response with client disconnection handling
        async def generate():
            try:
                async for chunk in create_streaming_response(
                    pipeline=pipeline,
                    query=request.query,
                    top_k=request.top_k,
                    use_hybrid=request.use_hybrid,
                    filter_dict=request.filters,
                    enable_token_streaming=True
                ):
                    # Check if client disconnected (requires FastAPI Request object)
                    # For now, we'll catch GeneratorExit when client disconnects
                    yield chunk
            except GeneratorExit:
                # Client disconnected
                logger.info("Stream closed by client")
            except Exception as e:
                logger.error(f"Error in stream generation: {e}")
                # Yield error chunk before closing
                from app.services.streaming import StreamChunk
                yield StreamChunk(
                    type="error",
                    content=str(e)
                ).to_sse()

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Streaming query failed: {str(e)}"
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Query Service Health Check / クエリサービスヘルスチェック",
    description="Check the health status of the Query service / Queryサービスのヘルス状態を確認します",
    response_description="Service health status / サービスのヘルス状態",
    responses={
        200: {"description": "Service is healthy / サービスが正常"}
    },
    tags=["Query"]
)
async def health_check() -> Dict[str, str]:
    """Health check endpoint / ヘルスチェックエンドポイント"""
    return {
        "status": "healthy",
        "service": "RAG Query API"
    }


class MetadataSearchRequest(BaseModel):
    """Request model for metadata search endpoint"""
    query: str = Field(..., description="Search query", min_length=1)
    filters: Dict[str, Any] = Field(..., description="Metadata filters")
    top_k: int = Field(5, description="Number of results", ge=1, le=20)
    match_all: bool = Field(True, description="If True, all filters must match (AND). If False, any filter can match (OR)")
    use_semantic: bool = Field(True, description="Use semantic search")


class MetadataSearchResponse(BaseModel):
    """Response model for metadata search endpoint"""
    results: List[Dict[str, Any]]
    total_found: int
    query: str


@router.post("/metadata", response_model=MetadataSearchResponse, status_code=status.HTTP_200_OK)
async def search_by_metadata(request: MetadataSearchRequest) -> MetadataSearchResponse:
    """
    Search documents with advanced metadata filtering

    This endpoint provides flexible metadata filtering capabilities with support for:
    - Equality operators: eq, ne
    - Comparison operators: gt, gte, lt, lte
    - List operators: in, nin
    - String operators: contains, regex
    - Existence operator: exists

    Args:
        request: Metadata search request with query and filters

    Returns:
        MetadataSearchResponse with filtered results

    Examples:
        Simple equality filter:
        ```json
        {
            "query": "company policy",
            "filters": {"department": "HR"}
        }
        ```

        Complex filter with operators:
        ```json
        {
            "query": "remote work",
            "filters": {
                "department": {"operator": "eq", "value": "HR"},
                "year": {"operator": "gte", "value": 2023}
            }
        }
        ```

        OR logic (match any filter):
        ```json
        {
            "query": "benefits",
            "filters": {
                "category": "compensation"
            },
            "match_all": false
        }
        ```
    """
    try:
        from app.main import get_rag_pipeline

        pipeline = get_rag_pipeline()

        # Create metadata search service
        metadata_service = MetadataSearchService(
            vector_db=pipeline.retriever.vector_db,
            embedding_model=pipeline.embedding_model
        )

        # Build filters from dictionary
        filter_list = metadata_service.build_filter_from_dict(request.filters)

        if not filter_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid filters provided"
            )

        # Perform metadata search
        results = metadata_service.search_by_metadata(
            query=request.query,
            filters=filter_list,
            top_k=request.top_k,
            match_all=request.match_all,
            use_semantic=request.use_semantic
        )

        # Convert results to response format
        response_data = [
            {
                "id": r.id,
                "score": r.score,
                "metadata": r.metadata,
                "text": r.text,
                "matched_filters": r.matched_filters
            }
            for r in results
        ]

        return MetadataSearchResponse(
            results=response_data,
            total_found=len(response_data),
            query=request.query
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filter specification: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Metadata search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Metadata search failed: {str(e)}"
        )


class MetadataValuesRequest(BaseModel):
    """Request model for getting unique metadata values"""
    field: str = Field(..., description="Metadata field name")
    query: Optional[str] = Field(None, description="Optional query to filter results")
    top_k: int = Field(100, description="Number of documents to scan", ge=1, le=1000)


class MetadataValuesResponse(BaseModel):
    """Response model for unique metadata values"""
    field: str
    values: List[Any]
    total: int


@router.post("/metadata/values", response_model=MetadataValuesResponse, status_code=status.HTTP_200_OK)
async def get_metadata_values(request: MetadataValuesRequest) -> MetadataValuesResponse:
    """
    Get unique values for a metadata field

    This endpoint helps discover available metadata values for filtering.
    Useful for building filter UIs or understanding document metadata.

    Args:
        request: Request with field name and optional query

    Returns:
        List of unique values for the specified field

    Example:
        ```json
        {
            "field": "department",
            "query": "company policy"
        }
        ```
    """
    try:
        from app.main import get_rag_pipeline

        pipeline = get_rag_pipeline()

        # Create metadata search service
        metadata_service = MetadataSearchService(
            vector_db=pipeline.retriever.vector_db,
            embedding_model=pipeline.embedding_model
        )

        # Get unique values
        values = metadata_service.get_unique_metadata_values(
            field=request.field,
            query=request.query,
            top_k=request.top_k
        )

        return MetadataValuesResponse(
            field=request.field,
            values=values,
            total=len(values)
        )

    except Exception as e:
        logger.error(f"Failed to get metadata values: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get metadata values: {str(e)}"
        )


class SuggestionRequestModel(BaseModel):
    """Request model for query suggestion endpoint"""
    partial_query: str = Field("", description="Partial query string for completion", min_length=0)
    max_suggestions: int = Field(10, description="Maximum number of suggestions", ge=1, le=50)
    include_history: bool = Field(True, description="Include user's historical queries")
    include_trending: bool = Field(True, description="Include trending queries")
    user_id: Optional[str] = Field(None, description="Optional user identifier for personalization")


class SuggestionResponse(BaseModel):
    """Response model for query suggestion endpoint"""
    suggestions: List[Dict[str, Any]]
    total: int


@router.post("/suggestions", response_model=SuggestionResponse, status_code=status.HTTP_200_OK)
async def get_suggestions(request: SuggestionRequestModel) -> SuggestionResponse:
    """
    Get intelligent query suggestions

    This endpoint provides query suggestions based on:
    - Content analysis: Completions based on query templates
    - User history: Personalized suggestions from past queries
    - Trending: Popular queries across all users

    Args:
        request: Suggestion request with parameters

    Returns:
        List of query suggestions with metadata

    Examples:
        Get completions for partial query:
        ```json
        {
            "partial_query": "company policy",
            "max_suggestions": 10
        }
        ```

        Get personalized suggestions:
        ```json
        {
            "partial_query": "remote",
            "max_suggestions": 10,
            "include_history": true,
            "user_id": "user123"
        }
        ```

        Get trending queries:
        ```json
        {
            "max_suggestions": 10,
            "include_trending": true
        }
        ```
    """
    try:
        # Get suggestion service
        suggestion_service = get_suggestion_service()

        # Create suggestion request
        suggestion_request = SuggestionRequest(
            partial_query=request.partial_query,
            max_suggestions=request.max_suggestions,
            include_history=request.include_history,
            include_trending=request.include_trending,
            user_id=request.user_id
        )

        # Get suggestions
        suggestions = suggestion_service.get_suggestions(suggestion_request)

        logger.info(
            f"Generated {len(suggestions)} suggestions for query: {request.partial_query[:50]}..."
        )

        return SuggestionResponse(
            suggestions=suggestions,
            total=len(suggestions)
        )

    except Exception as e:
        logger.error(f"Failed to generate suggestions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate suggestions: {str(e)}"
        )
