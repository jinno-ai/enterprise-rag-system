"""
Streaming Response Service

This module provides Server-Sent Events (SSE) streaming functionality for RAG responses.
It enables real-time streaming of query results for better user experience.
"""

import json
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from dataclasses import dataclass

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

    def _build_metadata_chunk(
        self,
        retrieval_results: list,
        answer: str,
        tokens_used: int
    ) -> str:
        """Helper to build metadata chunk (DRY principle)"""
        return StreamChunk(
            type="metadata",
            data={
                "confidence": self.pipeline._calculate_confidence(
                    retrieval_results,
                    answer
                ),
                "tokens_used": tokens_used,
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
            # Note: compressor.compress() requires query as first argument
            context = self.pipeline.compressor.compress(
                self.query,  # Add query parameter
                retrieval_results
            )

            prompt = self.pipeline._build_prompt(self.query, context)

            # Stage 3: Generate answer (with or without token streaming)
            yield StreamChunk(
                type="status",
                content="Generating answer..."
            ).to_sse()

            if self.enable_token_streaming:
                # Use real streaming with OpenAI API
                async for chunk in self._stream_generation_real(prompt, retrieval_results):
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
                yield self._build_metadata_chunk(
                    retrieval_results,
                    response['answer'],
                    response['tokens_used']
                )

            # Stage 4: Done signal
            yield StreamChunk(type="done").to_sse()

        except Exception as e:
            logger.error(f"Error during streaming: {e}", exc_info=True)
            yield StreamChunk(
                type="error",
                content=str(e)
            ).to_sse()

    async def _stream_generation_real(
        self,
        prompt: str,
        retrieval_results: list
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM generation token by token using REAL OpenAI streaming

        This uses OpenAI's native streaming API (stream=True) to get
        tokens as they're generated, providing actual streaming benefit.
        """
        try:
            import openai

            # Run streaming LLM call in thread pool to avoid blocking event loop
            stream = await asyncio.to_thread(
                self._call_llm_streaming,
                prompt
            )

            full_answer = []
            tokens_used = 0

            # Process streaming response
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_answer.append(token)

                    # Stream each token immediately
                    yield StreamChunk(
                        type="generation",
                        content=token
                    ).to_sse()

            # Get token usage from final chunk
            if hasattr(stream, 'usage') and stream.usage:
                tokens_used = stream.usage.total_tokens

            # Send final metadata with complete answer
            yield self._build_metadata_chunk(
                retrieval_results,
                ''.join(full_answer),
                tokens_used
            ).to_sse()

        except Exception as e:
            logger.error(f"Error in LLM streaming: {e}", exc_info=True)
            yield StreamChunk(
                type="error",
                content=f"LLM streaming error: {str(e)}"
            ).to_sse()

    def _call_llm_streaming(self, prompt: str):
        """
        Call LLM with streaming enabled (runs in thread pool)

        This is a synchronous wrapper around OpenAI's streaming API
        that gets executed in a thread pool to avoid blocking.
        """
        import openai

        try:
            stream = openai.chat.completions.create(
                model=self.pipeline.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that provides accurate answers based on given context."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.pipeline.temperature,
                max_tokens=self.pipeline.max_tokens,
                stream=True  # REAL STREAMING
            )

            return stream

        except Exception as e:
            raise RuntimeError(f"LLM streaming call failed: {e}")


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
