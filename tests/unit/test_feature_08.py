"""
Unit tests for Webhook Notifications (Feature 08)

Tests webhook notification system for document processing events.
Ensures webhooks are delivered reliably with proper retry logic and error handling.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone
from typing import Dict, Any

from app.services.webhook import (
    WebhookEventType,
    WebhookEvent,
    WebhookConfig,
    WebhookService,
    WebhookDeliveryResult,
    get_webhook_service,
    start_webhook_service,
    stop_webhook_service
)


@pytest.fixture
def reset_webhook_service():
    """Reset global webhook service before/after each test"""
    # Stop any existing service
    import app.services.webhook as webhook_module
    webhook_module._webhook_service = None
    yield
    # Cleanup after test
    webhook_module._webhook_service = None


@pytest.fixture
async def webhook_service(reset_webhook_service):
    """Create and start a webhook service for testing"""
    service = WebhookService(
        timeout_seconds=5,
        max_retries=2,
        retry_delay_seconds=0.1  # Short delay for tests
    )
    await service.start()
    yield service
    await service.stop()


@pytest.fixture
def sample_webhook_config():
    """Sample webhook configuration"""
    return WebhookConfig(
        url="https://example.com/webhook",
        secret="test_secret",
        events=[WebhookEventType.DOCUMENT_PROCESSING_COMPLETED],
        timeout_seconds=5,
        max_retries=2
    )


@pytest.fixture
def sample_event():
    """Sample webhook event"""
    return WebhookEvent(
        event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
        task_id="test-task-123",
        timestamp=datetime.now(timezone.utc),
        data={
            "documents_processed": 10,
            "chunks_created": 50,
            "collection": "test-collection"
        },
        collection="test-collection"
    )


class TestWebhookEvent:
    """Test suite for WebhookEvent dataclass"""

    def test_webhook_event_creation(self):
        """Test creating a webhook event"""
        event = WebhookEvent(
            event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
            task_id="task-123",
            timestamp=datetime.now(timezone.utc),
            data={"test": "data"}
        )

        assert event.task_id == "task-123"
        assert event.event_type == WebhookEventType.DOCUMENT_PROCESSING_COMPLETED
        assert event.retry_count == 0

    def test_webhook_event_to_dict(self, sample_event):
        """Test converting event to dictionary"""
        event_dict = sample_event.to_dict()

        assert event_dict["task_id"] == "test-task-123"
        assert event_dict["event_type"] == "document_processing_completed"
        assert "timestamp" in event_dict
        assert event_dict["data"]["documents_processed"] == 10

    def test_webhook_event_generate_signature(self, sample_event):
        """Test signature generation"""
        signature = sample_event.generate_signature("test_secret")

        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 produces 64 hex characters

        # Same input should produce same signature
        signature2 = sample_event.generate_signature("test_secret")
        assert signature == signature2

        # Different secret should produce different signature
        signature3 = sample_event.generate_signature("different_secret")
        assert signature != signature3


class TestWebhookConfig:
    """Test suite for WebhookConfig validation"""

    def test_valid_webhook_config(self):
        """Test creating valid webhook configuration"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            secret="secret",
            events=[WebhookEventType.DOCUMENT_PROCESSING_COMPLETED]
        )

        assert config.url == "https://example.com/webhook"
        assert config.secret == "secret"
        assert len(config.events) == 1
        assert config.enabled is True

    def test_webhook_config_defaults(self):
        """Test webhook configuration defaults"""
        config = WebhookConfig(url="https://example.com/webhook")

        assert config.enabled is True
        assert config.timeout_seconds == 10
        assert config.max_retries == 3
        assert config.retry_delay_seconds == 60
        assert len(config.events) > 0  # Should have all event types

    def test_webhook_config_invalid_url(self):
        """Test that invalid URL is rejected"""
        with pytest.raises(ValueError, match="must start with http:// or https://"):
            WebhookConfig(url="invalid-url")

    def test_webhook_config_http_url(self):
        """Test that HTTP URLs are accepted (though HTTPS is recommended)"""
        config = WebhookConfig(url="http://example.com/webhook")
        assert config.url == "http://example.com/webhook"


class TestWebhookServiceBasics:
    """Test suite for basic WebhookService functionality"""

    @pytest.mark.asyncio
    async def test_webhook_service_initialization(self, reset_webhook_service):
        """Test webhook service initialization"""
        service = WebhookService()
        assert service._webhooks == {}
        assert service._processing is False

    @pytest.mark.asyncio
    async def test_webhook_service_start_stop(self, webhook_service):
        """Test starting and stopping webhook service"""
        assert webhook_service._processing is True
        assert webhook_service._client is not None
        assert webhook_service._worker_task is not None

        await webhook_service.stop()
        assert webhook_service._processing is False

    @pytest.mark.asyncio
    async def test_register_webhook(self, webhook_service, sample_webhook_config):
        """Test registering a webhook"""
        webhook_service.register_webhook("webhook-1", sample_webhook_config)

        retrieved = webhook_service.get_webhook("webhook-1")
        assert retrieved is not None
        assert retrieved.url == "https://example.com/webhook"

    @pytest.mark.asyncio
    async def test_unregister_webhook(self, webhook_service, sample_webhook_config):
        """Test unregistering a webhook"""
        webhook_service.register_webhook("webhook-1", sample_webhook_config)
        assert webhook_service.get_webhook("webhook-1") is not None

        webhook_service.unregister_webhook("webhook-1")
        assert webhook_service.get_webhook("webhook-1") is None

    @pytest.mark.asyncio
    async def test_list_webhooks(self, webhook_service, sample_webhook_config):
        """Test listing all registered webhooks"""
        webhook_service.register_webhook("webhook-1", sample_webhook_config)

        config2 = WebhookConfig(url="https://example.com/webhook2")
        webhook_service.register_webhook("webhook-2", config2)

        webhooks = webhook_service.list_webhooks()
        assert len(webhooks) == 2
        assert "webhook-1" in webhooks
        assert "webhook-2" in webhooks

    @pytest.mark.asyncio
    async def test_get_nonexistent_webhook(self, webhook_service):
        """Test getting a webhook that doesn't exist"""
        result = webhook_service.get_webhook("nonexistent")
        assert result is None


class TestWebhookDelivery:
    """Test suite for webhook delivery functionality"""

    @pytest.mark.asyncio
    async def test_send_event_queues_event(self, webhook_service):
        """Test that sending an event queues it"""
        await webhook_service.send_event(
            event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
            task_id="task-123",
            data={"test": "data"}
        )

        # Event should be in queue
        assert not webhook_service._delivery_queue.empty()

    @pytest.mark.asyncio
    async def test_successful_webhook_delivery(self, webhook_service, sample_webhook_config):
        """Test successful webhook delivery"""
        webhook_service.register_webhook("webhook-1", sample_webhook_config)

        # Mock HTTP client to return success
        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"}
            )

            # Wait for queue processing
            await asyncio.sleep(0.2)

            # Verify POST was called
            assert mock_post.called
            call_args = mock_post.call_args
            assert call_args[1]["json"]["task_id"] == "task-123"
            assert call_args[1]["headers"]["X-Webhook-ID"] == "webhook-1"

    @pytest.mark.asyncio
    async def test_webhook_delivery_with_signature(self, webhook_service):
        """Test webhook delivery with signature"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            secret="test_secret"
        )
        webhook_service.register_webhook("webhook-1", config)

        # Mock HTTP client
        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"}
            )

            await asyncio.sleep(0.2)

            # Verify signature header is present
            call_args = mock_post.call_args
            assert "X-Webhook-Signature" in call_args[1]["headers"]

    @pytest.mark.asyncio
    async def test_disabled_webhook_not_called(self, webhook_service):
        """Test that disabled webhooks are not called"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            enabled=False
        )
        webhook_service.register_webhook("webhook-1", config)

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"}
            )

            await asyncio.sleep(0.2)

            # Verify POST was NOT called
            assert not mock_post.called

    @pytest.mark.asyncio
    async def test_event_type_filtering(self, webhook_service):
        """Test that webhooks only receive registered event types"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            events=[WebhookEventType.DOCUMENT_PROCESSING_COMPLETED]
        )
        webhook_service.register_webhook("webhook-1", config)

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            # Send event type that's NOT registered
            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_FAILED,
                task_id="task-123",
                data={"test": "data"}
            )

            await asyncio.sleep(0.2)

            # Verify POST was NOT called (event type not registered)
            assert not mock_post.called


class TestWebhookRetryLogic:
    """Test suite for webhook retry logic"""

    @pytest.mark.asyncio
    async def test_webhook_retry_on_timeout(self, webhook_service):
        """Test that webhooks retry on timeout"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            max_retries=2,
            retry_delay_seconds=1
        )
        webhook_service.register_webhook("webhook-1", config)

        from httpx import TimeoutException

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            # First call times out, second succeeds
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.side_effect = [TimeoutException("Timeout"), mock_response]

            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"}
            )

            # Wait for retry (retry_delay_seconds + processing time)
            await asyncio.sleep(2)

            # Should have been called twice (initial + 1 retry)
            assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_webhook_retry_on_non_2xx_status(self, webhook_service):
        """Test that webhooks retry on non-2xx status codes"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            max_retries=2,
            retry_delay_seconds=1
        )
        webhook_service.register_webhook("webhook-1", config)

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            # First call returns 500, second returns 200
            response_500 = Mock()
            response_500.status_code = 500
            response_200 = Mock()
            response_200.status_code = 200
            mock_post.side_effect = [response_500, response_200]

            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"}
            )

            # Wait for retry (retry_delay_seconds + processing time)
            await asyncio.sleep(2)

            # Should have been called twice
            assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_webhook_max_retries_exceeded(self, webhook_service):
        """Test that webhook stops after max retries"""
        config = WebhookConfig(
            url="https://example.com/webhook",
            max_retries=2,
            retry_delay_seconds=1
        )
        webhook_service.register_webhook("webhook-1", config)

        from httpx import RequestError

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            # All calls fail
            mock_post.side_effect = RequestError("Connection error")

            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"}
            )

            # Wait for all retries (2 retries * 1 second delay + processing time)
            await asyncio.sleep(3)

            # Should have been called max_retries times
            assert mock_post.call_count == 2


class TestWebhookDeliveryResult:
    """Test suite for WebhookDeliveryResult"""

    def test_successful_result(self):
        """Test successful delivery result"""
        result = WebhookDeliveryResult(
            success=True,
            webhook_url="https://example.com/webhook",
            status_code=200
        )

        assert result.success is True
        assert result.status_code == 200
        assert result.error_message is None

    def test_failed_result(self):
        """Test failed delivery result"""
        result = WebhookDeliveryResult(
            success=False,
            webhook_url="https://example.com/webhook",
            error_message="Connection timeout"
        )

        assert result.success is False
        assert result.error_message == "Connection timeout"
        assert result.status_code is None

    def test_result_to_dict(self):
        """Test converting result to dictionary"""
        result = WebhookDeliveryResult(
            success=True,
            webhook_url="https://example.com/webhook",
            status_code=200
        )

        result_dict = result.to_dict()
        assert result_dict["success"] is True
        assert result_dict["webhook_url"] == "https://example.com/webhook"
        assert result_dict["status_code"] == 200


class TestGlobalWebhookService:
    """Test suite for global webhook service functions"""

    @pytest.mark.asyncio
    async def test_start_webhook_service(self, reset_webhook_service):
        """Test starting global webhook service"""
        service = await start_webhook_service()

        assert service is not None
        assert service._processing is True

        await stop_webhook_service()

    @pytest.mark.asyncio
    async def test_get_webhook_service(self, reset_webhook_service):
        """Test getting global webhook service"""
        with pytest.raises(RuntimeError, match="Webhook service not initialized"):
            get_webhook_service()

        await start_webhook_service()
        service = get_webhook_service()

        assert service is not None
        assert isinstance(service, WebhookService)

        await stop_webhook_service()

    @pytest.mark.asyncio
    async def test_stop_webhook_service(self, reset_webhook_service):
        """Test stopping global webhook service"""
        await start_webhook_service()
        assert get_webhook_service() is not None

        await stop_webhook_service()

        with pytest.raises(RuntimeError, match="Webhook service not initialized"):
            get_webhook_service()


class TestWebhookEventTypes:
    """Test suite for webhook event types"""

    def test_all_event_types_defined(self):
        """Test that all expected event types are defined"""
        expected_types = [
            "document_processing_completed",
            "document_processing_failed",
            "task_completed",
            "task_failed"
        ]

        for expected in expected_types:
            assert hasattr(WebhookEventType, expected.replace("_processing_", "_processing_").upper())

    def test_event_type_values(self):
        """Test event type enum values"""
        assert WebhookEventType.DOCUMENT_PROCESSING_COMPLETED.value == "document_processing_completed"
        assert WebhookEventType.DOCUMENT_PROCESSING_FAILED.value == "document_processing_failed"
        assert WebhookEventType.TASK_COMPLETED.value == "task_completed"
        assert WebhookEventType.TASK_FAILED.value == "task_failed"


class TestWebhookIntegrationScenarios:
    """Test suite for integration scenarios"""

    @pytest.mark.asyncio
    async def test_multiple_webhooks_same_event(self, webhook_service):
        """Test delivering event to multiple webhooks"""
        config1 = WebhookConfig(url="https://webhook1.example.com")
        config2 = WebhookConfig(url="https://webhook2.example.com")

        webhook_service.register_webhook("webhook-1", config1)
        webhook_service.register_webhook("webhook-2", config2)

        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"}
            )

            await asyncio.sleep(0.2)

            # Both webhooks should have been called
            assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_webhook_with_collection(self, webhook_service):
        """Test webhook event includes collection"""
        config = WebhookConfig(url="https://example.com/webhook")
        webhook_service.register_webhook("webhook-1", config)

        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"},
                collection="my-collection"
            )

            await asyncio.sleep(0.2)

            # Verify collection is in payload
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            assert payload["collection"] == "my-collection"

    @pytest.mark.asyncio
    async def test_webhook_headers(self, webhook_service):
        """Test webhook request headers"""
        config = WebhookConfig(url="https://example.com/webhook")
        webhook_service.register_webhook("webhook-1", config)

        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(webhook_service._client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await webhook_service.send_event(
                event_type=WebhookEventType.DOCUMENT_PROCESSING_COMPLETED,
                task_id="task-123",
                data={"test": "data"}
            )

            await asyncio.sleep(0.2)

            # Verify headers
            call_args = mock_post.call_args
            headers = call_args[1]["headers"]
            assert headers["Content-Type"] == "application/json"
            assert headers["X-Webhook-ID"] == "webhook-1"
            assert headers["X-Event-Type"] == "document_processing_completed"
            assert headers["X-Task-ID"] == "task-123"
            assert "X-Timestamp" in headers
