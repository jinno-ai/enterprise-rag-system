"""
Webhook notification service for document processing events

This module provides webhook notification functionality for document processing
completion events, allowing external systems to receive real-time notifications.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import hashlib

import httpx
from pydantic import BaseModel, HttpUrl, Field, field_validator


logger = logging.getLogger(__name__)


class WebhookEventType(str, Enum):
    """Types of webhook events"""
    DOCUMENT_PROCESSING_COMPLETED = "document_processing_completed"
    DOCUMENT_PROCESSING_FAILED = "document_processing_failed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


@dataclass
class WebhookEvent:
    """Represents a webhook event"""
    event_type: WebhookEventType
    task_id: str
    timestamp: datetime
    data: Dict[str, Any]
    collection: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for JSON serialization"""
        return {
            "event_type": self.event_type.value,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "collection": self.collection,
            "data": self.data,
            "retry_count": self.retry_count
        }

    def generate_signature(self, secret: str) -> str:
        """
        Generate HMAC signature for webhook payload verification

        Args:
            secret: Webhook secret key

        Returns:
            Hexadecimal signature string
        """
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256((secret + payload).encode()).hexdigest()


class WebhookConfig(BaseModel):
    """Configuration for a webhook endpoint"""
    url: str
    secret: Optional[str] = None
    events: List[WebhookEventType] = Field(default_factory=lambda: list(WebhookEventType))
    enabled: bool = True
    timeout_seconds: int = 10
    max_retries: int = 3
    retry_delay_seconds: int = 60

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        """Validate webhook URL"""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must start with http:// or https://")
        return v


class WebhookDeliveryResult:
    """Result of a webhook delivery attempt"""
    def __init__(
        self,
        success: bool,
        webhook_url: str,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None
    ):
        self.success = success
        self.webhook_url = webhook_url
        self.status_code = status_code
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            "success": self.success,
            "webhook_url": self.webhook_url,
            "status_code": self.status_code,
            "error_message": self.error_message
        }


class WebhookService:
    """
    Service for managing and delivering webhook notifications

    This service handles registration of webhook endpoints and delivery
    of events to those endpoints with retry logic and error handling.
    """

    def __init__(
        self,
        timeout_seconds: int = 10,
        max_retries: int = 3,
        retry_delay_seconds: int = 60
    ):
        """
        Initialize the webhook service

        Args:
            timeout_seconds: HTTP request timeout
            max_retries: Maximum number of retry attempts
            retry_delay_seconds: Delay between retries
        """
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self._webhooks: Dict[str, WebhookConfig] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._delivery_queue: asyncio.Queue[WebhookEvent] = asyncio.Queue()
        self._processing = False
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the webhook service background worker"""
        if self._processing:
            logger.warning("Webhook service already running")
            return

        self._processing = True
        self._client = httpx.AsyncClient(timeout=self.timeout_seconds)

        # Start background worker
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("Webhook service started")

    async def stop(self) -> None:
        """Stop the webhook service gracefully"""
        if not self._processing:
            return

        logger.info("Stopping webhook service...")
        self._processing = False

        # Cancel worker task
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        # Close HTTP client
        if self._client:
            await self._client.aclose()

        logger.info("Webhook service stopped")

    def register_webhook(
        self,
        webhook_id: str,
        config: WebhookConfig
    ) -> None:
        """
        Register a webhook endpoint

        Args:
            webhook_id: Unique identifier for the webhook
            config: Webhook configuration
        """
        self._webhooks[webhook_id] = config
        logger.info(f"Registered webhook: {webhook_id} -> {config.url}")

    def unregister_webhook(self, webhook_id: str) -> None:
        """
        Unregister a webhook endpoint

        Args:
            webhook_id: Webhook identifier to remove
        """
        if webhook_id in self._webhooks:
            del self._webhooks[webhook_id]
            logger.info(f"Unregistered webhook: {webhook_id}")

    def get_webhook(self, webhook_id: str) -> Optional[WebhookConfig]:
        """
        Get webhook configuration by ID

        Args:
            webhook_id: Webhook identifier

        Returns:
            Webhook configuration or None if not found
        """
        return self._webhooks.get(webhook_id)

    def list_webhooks(self) -> Dict[str, WebhookConfig]:
        """Get all registered webhooks"""
        return self._webhooks.copy()

    async def send_event(
        self,
        event_type: WebhookEventType,
        task_id: str,
        data: Dict[str, Any],
        collection: Optional[str] = None
    ) -> None:
        """
        Queue a webhook event for delivery

        Args:
            event_type: Type of event
            task_id: Associated task ID
            data: Event payload data
            collection: Optional collection name
        """
        event = WebhookEvent(
            event_type=event_type,
            task_id=task_id,
            timestamp=datetime.now(timezone.utc),
            data=data,
            collection=collection
        )

        await self._delivery_queue.put(event)
        logger.info(f"Queued webhook event: {event_type.value} for task {task_id}")

    async def _process_queue(self) -> None:
        """Background worker to process webhook delivery queue"""
        while self._processing:
            try:
                # Wait for events with timeout to allow checking _processing flag
                event = await asyncio.wait_for(
                    self._delivery_queue.get(),
                    timeout=1.0
                )

                # Deliver event to all registered webhooks
                await self._deliver_event(event)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in webhook queue processor: {e}", exc_info=True)

    async def _deliver_event(self, event: WebhookEvent) -> None:
        """
        Deliver event to all registered webhooks

        Args:
            event: Event to deliver
        """
        results = []

        for webhook_id, config in self._webhooks.items():
            # Skip disabled webhooks
            if not config.enabled:
                continue

            # Check if webhook is interested in this event type
            if event.event_type not in config.events:
                continue

            # Deliver to webhook
            result = await self._deliver_to_webhook(webhook_id, config, event)
            results.append(result)

            # Log result
            if result.success:
                logger.info(
                    f"Webhook delivered successfully: {webhook_id} "
                    f"(status: {result.status_code})"
                )
            else:
                logger.error(
                    f"Webhook delivery failed: {webhook_id} "
                    f"(error: {result.error_message})"
                )

    async def _deliver_to_webhook(
        self,
        webhook_id: str,
        config: WebhookConfig,
        event: WebhookEvent
    ) -> WebhookDeliveryResult:
        """
        Deliver event to a single webhook with retry logic

        Args:
            webhook_id: Webhook identifier
            config: Webhook configuration
            event: Event to deliver

        Returns:
            Delivery result
        """
        if not self._client:
            return WebhookDeliveryResult(
                success=False,
                webhook_url=config.url,
                error_message="HTTP client not initialized"
            )

        # Prepare payload
        payload = event.to_dict()

        # Add signature if secret is configured
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-ID": webhook_id,
            "X-Event-Type": event.event_type.value,
            "X-Task-ID": event.task_id,
            "X-Timestamp": event.timestamp.isoformat()
        }

        if config.secret:
            signature = event.generate_signature(config.secret)
            headers["X-Webhook-Signature"] = signature

        # Attempt delivery with retries
        for attempt in range(config.max_retries):
            try:
                response = await self._client.post(
                    config.url,
                    json=payload,
                    headers=headers,
                    timeout=config.timeout_seconds
                )

                # Consider 2xx status codes as success
                if 200 <= response.status_code < 300:
                    return WebhookDeliveryResult(
                        success=True,
                        webhook_url=config.url,
                        status_code=response.status_code
                    )
                else:
                    # Non-2xx response - log and retry
                    logger.warning(
                        f"Webhook returned non-2xx status: {response.status_code} "
                        f"(attempt {attempt + 1}/{config.max_retries})"
                    )

            except httpx.TimeoutException:
                logger.warning(
                    f"Webhook timeout (attempt {attempt + 1}/{config.max_retries})"
                )
            except httpx.RequestError as e:
                logger.warning(
                    f"Webhook request error: {e} "
                    f"(attempt {attempt + 1}/{config.max_retries})"
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error delivering webhook: {e}",
                    exc_info=True
                )
                return WebhookDeliveryResult(
                    success=False,
                    webhook_url=config.url,
                    error_message=str(e)
                )

            # Wait before retry (except on last attempt)
            if attempt < config.max_retries - 1:
                await asyncio.sleep(config.retry_delay_seconds)

        # All retries exhausted
        return WebhookDeliveryResult(
            success=False,
            webhook_url=config.url,
            error_message=f"Failed after {config.max_retries} attempts"
        )


# Global webhook service instance
_webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> WebhookService:
    """
    Get the global webhook service instance

    Returns:
        Webhook service instance

    Raises:
        RuntimeError: If service has not been initialized
    """
    global _webhook_service
    if _webhook_service is None:
        raise RuntimeError("Webhook service not initialized. Call start_webhook_service() first.")
    return _webhook_service


async def start_webhook_service(
    timeout_seconds: int = 10,
    max_retries: int = 3,
    retry_delay_seconds: int = 60
) -> WebhookService:
    """
    Start the global webhook service

    Args:
        timeout_seconds: HTTP request timeout
        max_retries: Maximum retry attempts
        retry_delay_seconds: Delay between retries

    Returns:
        Webhook service instance
    """
    global _webhook_service
    if _webhook_service is not None:
        logger.warning("Webhook service already running")
        return _webhook_service

    _webhook_service = WebhookService(
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds
    )

    await _webhook_service.start()
    return _webhook_service


async def stop_webhook_service() -> None:
    """Stop the global webhook service"""
    global _webhook_service
    if _webhook_service is not None:
        await _webhook_service.stop()
        _webhook_service = None
