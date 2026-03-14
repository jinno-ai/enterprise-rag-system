"""
Streaming Response Service

This module provides Server-Sent Events (SSE) streaming functionality for RAG responses.
It enables real-time streaming of query results for better user experience.
"""

import json
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from dataclasses import dataclass, asdict
import logging

from app.services.rag_pipeline import RAGPipeline, RAGResponse, RetrievalResult


logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """A single chunk of streaming data"""
    type: str  # 'retrieval', 'generation', 'metadata', 'error', 'done'
    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def to_sse(self) -> str:
        """Convert to SSE format"""
        chunk_data = {
            "type": self.type,
            "content": self.content,
            "data": self.data
        }
        # Remove None values
        chunk_data = {k: v for k, v in chunk_data.items() if v is not None}
        return f"data: {json.dumps(chunk_data)}\n\n"


class StreamingResponseGenerator:
    """
    Generates streaming responses for RAG queries

    Streams response in multiple stages:
    1. Retrieval progress - shows which documents are being retrieved
    2. Generation progress - streams the generated answer token by token
    3. Metadata - final metadata (confidence, latency, tokens)
    """

    def __init__(
        self,
        pipeline: RAGPipeline,
        query: str,
        top_k: int = 5,
        use_hybrid: bool = True,
        filter_dict: Optional[Dict[str, Any]] = None,
        enable_token_streaming: bool = True
    ):
        self.pipeline = pipeline
        self.query = query
        self.top_k = top_k
        self.use_hybrid = use_hybrid
        self.filter_dict = filter_dict
        self.enable_token_streaming = enable_token_streaming

    async def stream_response(self) -> AsyncGenerator[str, None]:
        """
        Stream the complete RAG response

        Yields:
            SSE-formatted response chunks
        """
        try:
            # Stage 1: Retrieval
            logger.info(f"Starting retrieval for query: {self.query}")
            yield StreamChunk(
                type="status",
                content="Retrieving relevant documents..."
            ).to_sse()

            retrieval_results = self.pipeline.retriever.retrieve(
                query=self.query,
                top_k=self.top_k,
                use_hybrid=self.use_hybrid,
                filter_dict=self.filter_dict
            )

            # Send retrieval results as metadata
            yield StreamChunk(
                type="retrieval",
                data={
                    "count": len(retrieval_results),
                    "sources": [
                        {
                            "document": r.document[:100] + "..." if len(r.document) > 100 else r.document,
                            "score": r.score,
                            "metadata": r.metadata
                        }
                        for r in retrieval_results[:3]  # Send top 3
                    ]
                }
            ).to_sse()

            # Stage 2: Build context and prompt
            context = self.pipeline.compressor.compress(
                retrieval_results,
                max_tokens=4000
            )

            prompt = self.pipeline._build_prompt(self.query, context)

            # Stage 3: Generate answer (with or without token streaming)
            yield StreamChunk(
                type="status",
                content="Generating answer..."
            ).to_sse()

            if self.enable_token_streaming:
                # Stream generation token by token (simulated for standard OpenAI API)
                async for chunk in self._stream_generation(prompt, retrieval_results):
                    yield chunk
            else:
                # Non-streaming generation (fallback)
                response = await asyncio.to_thread(
                    self.pipeline._call_llm,
                    prompt
                )
                yield StreamChunk(
                    type="generation",
                    content=response['answer']
                ).to_sse()

                # Send final metadata
                yield StreamChunk(
                    type="metadata",
                    data={
                        "confidence": self.pipeline._calculate_confidence(
                            retrieval_results,
                            response['answer']
                        ),
                        "tokens_used": response['tokens_used'],
                        "sources": [
                            {
                                "document": r.document,
                                "score": r.score,
                                "metadata": r.metadata
                            }
                            for r in retrieval_results
                        ]
                    }
                ).to_sse()

            # Stage 4: Done signal
            yield StreamChunk(type="done").to_sse()

        except Exception as e:
            logger.error(f"Error during streaming: {e}", exc_info=True)
            yield StreamChunk(
                type="error",
                content=str(e)
            ).to_sse()

    async def _stream_generation(
        self,
        prompt: str,
        retrieval_results: list
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM generation token by token

        Note: This is a simulated streaming for standard OpenAI API.
        For true token streaming, you would use the streaming=True parameter
        in the OpenAI API call.
        """
        # Run LLM call in thread pool to avoid blocking
        response = await asyncio.to_thread(
            self.pipeline._call_llm,
            prompt
        )

        answer = response['answer']

        # Simulate token streaming by sending chunks
        chunk_size = 20  # characters per chunk
        for i in range(0, len(answer), chunk_size):
            chunk = answer[i:i + chunk_size]
            yield StreamChunk(
                type="generation",
                content=chunk
            ).to_sse()
            # Small delay to simulate streaming
            await asyncio.sleep(0.01)

        # Send final metadata
        yield StreamChunk(
            type="metadata",
            data={
                "confidence": self.pipeline._calculate_confidence(
                    retrieval_results,
                    answer
                ),
                "tokens_used": response['tokens_used'],
                "sources": [
                    {
                        "document": r.document,
                        "score": r.score,
                        "metadata": r.metadata
                    }
                    for r in retrieval_results
                ]
            }
        ).to_sse()


async def create_streaming_response(
    pipeline: RAGPipeline,
    query: str,
    top_k: int = 5,
    use_hybrid: bool = True,
    filter_dict: Optional[Dict[str, Any]] = None,
    enable_token_streaming: bool = True
) -> AsyncGenerator[str, None]:
    """
    Factory function to create a streaming response

    Args:
        pipeline: RAG pipeline instance
        query: User query
        top_k: Number of documents to retrieve
        use_hybrid: Whether to use hybrid search
        filter_dict: Optional metadata filters
        enable_token_streaming: Whether to stream token by token

    Yields:
        SSE-formatted response chunks
    """
    generator = StreamingResponseGenerator(
        pipeline=pipeline,
        query=query,
        top_k=top_k,
        use_hybrid=use_hybrid,
        filter_dict=filter_dict,
        enable_token_streaming=enable_token_streaming
    )

    async for chunk in generator.stream_response():
        yield chunk
