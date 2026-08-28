"""
Unit tests for API Documentation Generator Feature (Feature 44)

Tests the enhanced API documentation system including:
- Custom OpenAPI schema generation
- Markdown documentation export
- Endpoint summary and listing
- Documentation configuration
- Integration with FastAPI
- Error handling and edge cases
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient
from typing import Dict, Any

from app.api.docs import (
    APIDocumentationGenerator,
    DocumentationConfig,
    get_documentation_generator,
    router as docs_router
)


# ==================== Fixtures ====================

@pytest.fixture
def sample_fastapi_app():
    """Create a sample FastAPI application for testing"""
    app = FastAPI(
        title="Enterprise RAG System",
        version="2.0.0",
        description="Production-grade RAG pipeline for enterprise knowledge bases"
    )

    # Add a sample router
    sample_router = APIRouter(prefix="/api/v1", tags=["Test"])

    @sample_router.get("/test")
    async def test_endpoint():
        """A test endpoint"""
        return {"message": "test"}

    @sample_router.post("/query")
    async def query_endpoint(query: str):
        """Query endpoint"""
        return {"answer": f"Response to: {query}"}

    app.include_router(sample_router)
    app.include_router(docs_router)

    return app


@pytest.fixture
def documentation_config():
    """Create documentation configuration"""
    return DocumentationConfig(
        include_examples=True,
        include_response_schemas=True,
        include_auth_docs=True,
        include_rate_limiting=True,
        contact_email="test@example.com",
        license_name="MIT"
    )


@pytest.fixture
def doc_generator(sample_fastapi_app, documentation_config):
    """Create documentation generator instance"""
    return APIDocumentationGenerator(sample_fastapi_app, documentation_config)


@pytest.fixture
def client(sample_fastapi_app):
    """Create test client"""
    return TestClient(sample_fastapi_app)


# ==================== Test DocumentationConfig ====================

class TestDocumentationConfig:
    """Test suite for DocumentationConfig"""

    def test_default_configuration(self):
        """Test documentation config with default values"""
        config = DocumentationConfig()

        assert config.include_examples is True
        assert config.include_response_schemas is True
        assert config.include_auth_docs is True
        assert config.include_rate_limiting is True
        assert config.custom_tags == []
        assert config.contact_email == "support@example.com"
        assert config.license_name == "MIT"

    def test_custom_configuration(self):
        """Test documentation config with custom values"""
        config = DocumentationConfig(
            include_examples=False,
            include_response_schemas=False,
            include_auth_docs=False,
            include_rate_limiting=False,
            custom_tags=["Custom1", "Custom2"],
            contact_email="custom@example.com",
            license_name="Apache-2.0"
        )

        assert config.include_examples is False
        assert config.include_response_schemas is False
        assert config.include_auth_docs is False
        assert config.include_rate_limiting is False
        assert config.custom_tags == ["Custom1", "Custom2"]
        assert config.contact_email == "custom@example.com"
        assert config.license_name == "Apache-2.0"


# ==================== Test APIDocumentationGenerator ====================

class TestAPIDocumentationGenerator:
    """Test suite for APIDocumentationGenerator"""

    def test_initialization(self, sample_fastapi_app, documentation_config):
        """Test documentation generator initialization"""
        doc_gen = APIDocumentationGenerator(sample_fastapi_app, documentation_config)

        assert doc_gen.app == sample_fastapi_app
        assert doc_gen.config == documentation_config
        # Note: openapi_schema is set lazily on first access
        # Access it to trigger generation
        schema = doc_gen.app.openapi()
        assert schema is not None

    def test_initialization_with_default_config(self, sample_fastapi_app):
        """Test documentation generator initialization with default config"""
        doc_gen = APIDocumentationGenerator(sample_fastapi_app)

        assert doc_gen.app == sample_fastapi_app
        assert isinstance(doc_gen.config, DocumentationConfig)

    def test_custom_openapi_schema_generation(self, doc_generator):
        """Test custom OpenAPI schema generation"""
        openapi_schema = doc_generator.app.openapi()

        assert openapi_schema is not None
        assert "openapi" in openapi_schema
        assert "info" in openapi_schema
        assert "paths" in openapi_schema
        assert "tags" in openapi_schema
        assert "components" in openapi_schema

    def test_openapi_info_section(self, doc_generator):
        """Test OpenAPI info section contains required fields"""
        openapi_schema = doc_generator.app.openapi()

        info = openapi_schema["info"]
        assert "title" in info
        assert "version" in info
        assert "description" in info
        assert info["title"] == "Enterprise RAG System"
        assert info["version"] == "2.0.0"
        assert "contact" in info
        assert "license" in info

    def test_openapi_contact_info(self, doc_generator, documentation_config):
        """Test OpenAPI contact information"""
        openapi_schema = doc_generator.app.openapi()

        contact = openapi_schema["info"]["contact"]
        assert contact["email"] == documentation_config.contact_email
        assert contact["name"] == "API Support"

    def test_openapi_license_info(self, doc_generator, documentation_config):
        """Test OpenAPI license information"""
        openapi_schema = doc_generator.app.openapi()

        license_info = openapi_schema["info"]["license"]
        assert license_info["name"] == documentation_config.license_name
        assert "url" in license_info

    def test_tags_documentation(self, doc_generator):
        """Test tags documentation is present"""
        openapi_schema = doc_generator.app.openapi()

        tags = openapi_schema["tags"]
        assert isinstance(tags, list)
        assert len(tags) > 0

        # Check tag structure
        for tag in tags:
            assert "name" in tag
            assert "description" in tag

    def test_components_schemas(self, doc_generator):
        """Test component schemas are defined"""
        openapi_schema = doc_generator.app.openapi()

        components = openapi_schema["components"]
        assert "schemas" in components

        schemas = components["schemas"]
        assert "ErrorResponse" in schemas
        assert "SuccessResponse" in schemas

    def test_security_schemes_when_auth_enabled(self, doc_generator):
        """Test security schemes are defined when auth docs are enabled"""
        openapi_schema = doc_generator.app.openapi()

        security_schemes = openapi_schema["components"]["securitySchemes"]
        assert "ApiKeyAuth" in security_schemes
        assert "BearerAuth" in security_schemes

        # Check ApiKeyAuth structure
        api_key_auth = security_schemes["ApiKeyAuth"]
        assert api_key_auth["type"] == "apiKey"
        assert api_key_auth["in"] == "header"
        assert api_key_auth["name"] == "X-API-Key"

        # Check BearerAuth structure
        bearer_auth = security_schemes["BearerAuth"]
        assert bearer_auth["type"] == "http"
        assert bearer_auth["scheme"] == "bearer"

    def test_security_schemes_when_auth_disabled(self, sample_fastapi_app):
        """Test security schemes are not defined when auth docs are disabled"""
        config = DocumentationConfig(include_auth_docs=False)
        doc_gen = APIDocumentationGenerator(sample_fastapi_app, config)

        openapi_schema = doc_gen.app.openapi()
        components = openapi_schema.get("components", {})

        # Security schemes should not be present
        assert "securitySchemes" not in components or \
               "ApiKeyAuth" not in components.get("securitySchemes", {})

    def test_enhanced_description_generation(self, doc_generator):
        """Test enhanced API description generation"""
        description = doc_generator._get_enhanced_description()

        assert "Enterprise RAG System" in description
        assert "Features" in description
        assert "Authentication" in description
        assert "Rate Limiting" in description
        assert "Response Format" in description
        assert "Versioning" in description
        assert "Swagger UI" in description

    def test_get_endpoint_summary(self, doc_generator):
        """Test endpoint summary generation"""
        summary = doc_generator.get_endpoint_summary()

        assert "total_endpoints" in summary
        assert "by_tag" in summary
        assert "by_method" in summary
        assert "endpoints" in summary

        # Should have endpoints from our test app
        assert summary["total_endpoints"] > 0

        # Check endpoint structure
        for endpoint in summary["endpoints"]:
            assert "path" in endpoint
            assert "method" in endpoint
            assert "tags" in endpoint
            assert "operation_id" in endpoint

    def test_markdown_documentation_generation(self, doc_generator):
        """Test markdown documentation generation"""
        markdown = doc_generator.generate_markdown_documentation()

        assert markdown.startswith("# API Documentation")
        assert "**Version**" in markdown
        assert "**Base URL**" in markdown
        assert "## Authentication" in markdown
        assert "## Rate Limiting" in markdown
        assert "## Endpoints" in markdown
        assert "## Response Codes" in markdown
        assert "## Examples" in markdown

    def test_markdown_includes_table_of_contents(self, doc_generator):
        """Test markdown documentation includes table of contents"""
        markdown = doc_generator.generate_markdown_documentation()

        assert "## Table of Contents" in markdown
        assert "- [Authentication](#authentication)" in markdown
        assert "- [Rate Limiting](#rate-limiting)" in markdown
        assert "- [Endpoints](#endpoints)" in markdown

    def test_markdown_includes_examples(self, doc_generator):
        """Test markdown documentation includes usage examples"""
        markdown = doc_generator.generate_markdown_documentation()

        assert "### Query Example" in markdown
        assert "curl" in markdown
        assert "X-API-Key" in markdown
        assert "/api/v1/query/" in markdown

    def test_markdown_includes_response_codes_table(self, doc_generator):
        """Test markdown documentation includes response codes table"""
        markdown = doc_generator.generate_markdown_documentation()

        assert "| Code | Description |" in markdown
        assert "| 200  | Success |" in markdown
        assert "| 400  | Bad Request |" in markdown
        assert "| 401  | Unauthorized |" in markdown

    def test_export_openapi_json(self, doc_generator):
        """Test exporting OpenAPI schema to JSON file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            filepath = f.name

        try:
            doc_generator.export_openapi_json(filepath)

            # Verify file exists and is valid JSON
            assert os.path.exists(filepath)

            with open(filepath, 'r') as f:
                exported_schema = json.load(f)

            assert "openapi" in exported_schema
            assert "info" in exported_schema
            assert "paths" in exported_schema

        finally:
            # Cleanup
            if os.path.exists(filepath):
                os.remove(filepath)

    def test_export_markdown_docs(self, doc_generator):
        """Test exporting markdown documentation to file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            filepath = f.name

        try:
            doc_generator.export_markdown_docs(filepath)

            # Verify file exists and contains markdown
            assert os.path.exists(filepath)

            with open(filepath, 'r') as f:
                content = f.read()

            assert content.startswith("# API Documentation")
            assert "## Authentication" in content

        finally:
            # Cleanup
            if os.path.exists(filepath):
                os.remove(filepath)


# ==================== Test Documentation API Endpoints ====================

class TestDocumentationAPIEndpoints:
    """Test suite for documentation API endpoints"""

    def test_docs_health_check_endpoint(self, client):
        """Test documentation health check endpoint"""
        response = client.get("/docs-api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "API Documentation Generator"

    def test_get_api_summary_endpoint(self, client):
        """Test get API summary endpoint"""
        response = client.get("/docs-api/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data

        summary = data["data"]
        assert "total_endpoints" in summary
        assert "by_tag" in summary
        assert "by_method" in summary
        assert "endpoints" in summary

    def test_get_markdown_docs_endpoint(self, client):
        """Test get markdown documentation endpoint"""
        response = client.get("/docs-api/markdown")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["format"] == "markdown"
        assert "documentation" in data

        # Verify markdown content
        markdown = data["documentation"]
        assert markdown.startswith("# API Documentation")

    def test_get_openapi_schema_endpoint(self, client):
        """Test get OpenAPI schema endpoint"""
        response = client.get("/docs-api/openapi-schema")

        assert response.status_code == 200
        schema = response.json()

        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

    def test_list_endpoints_endpoint(self, client):
        """Test list endpoints endpoint"""
        response = client.get("/docs-api/endpoints")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "total" in data
        assert "endpoints" in data

        # Verify endpoint structure
        for endpoint in data["endpoints"]:
            assert "path" in endpoint
            assert "method" in endpoint
            assert "tags" in endpoint

    def test_endpoints_include_docs_api_endpoints(self, client):
        """Test that documentation API endpoints are included in the list"""
        response = client.get("/docs-api/endpoints")

        assert response.status_code == 200
        data = response.json()

        # Find documentation endpoints
        docs_endpoints = [
            ep for ep in data["endpoints"]
            if "/docs-api/" in ep["path"]
        ]

        assert len(docs_endpoints) > 0

        # Check for specific docs endpoints
        endpoint_paths = [ep["path"] for ep in docs_endpoints]
        assert "/docs-api/health" in endpoint_paths
        assert "/docs-api/summary" in endpoint_paths
        assert "/docs-api/markdown" in endpoint_paths


# ==================== Test Singleton Pattern ====================

class TestDocumentationGeneratorSingleton:
    """Test suite for documentation generator singleton"""

    def test_get_documentation_generator_creates_instance(self, sample_fastapi_app):
        """Test that get_documentation_generator creates instance on first call"""
        # Reset singleton
        import app.api.docs
        app.api.docs._doc_generator = None

        doc_gen = get_documentation_generator(sample_fastapi_app)

        assert isinstance(doc_gen, APIDocumentationGenerator)
        assert doc_gen.app == sample_fastapi_app

    def test_get_documentation_generator_returns_singleton(self, sample_fastapi_app):
        """Test that get_documentation_generator returns same instance on subsequent calls"""
        # Reset singleton
        import app.api.docs
        app.api.docs._doc_generator = None

        doc_gen1 = get_documentation_generator(sample_fastapi_app)
        doc_gen2 = get_documentation_generator()

        assert doc_gen1 is doc_gen2

    def test_get_documentation_generator_without_app_raises_error(self):
        """Test that get_documentation_generator raises error when called without app"""
        # Reset singleton
        import app.api.docs
        app.api.docs._doc_generator = None

        with pytest.raises(RuntimeError) as exc_info:
            get_documentation_generator()

        assert "Documentation generator not initialized" in str(exc_info.value)


# ==================== Test Error Handling ====================

class TestDocumentationErrorHandling:
    """Test suite for error handling"""

    def test_export_openapi_json_invalid_path(self, doc_generator):
        """Test exporting to invalid path handles error gracefully"""
        invalid_path = "/nonexistent/directory/schema.json"

        # Should raise an error or handle it gracefully
        with pytest.raises(Exception):
            doc_generator.export_openapi_json(invalid_path)

    def test_export_markdown_docs_invalid_path(self, doc_generator):
        """Test exporting markdown to invalid path handles error gracefully"""
        invalid_path = "/nonexistent/directory/docs.md"

        # Should raise an error or handle it gracefully
        with pytest.raises(Exception):
            doc_generator.export_markdown_docs(invalid_path)

    def test_endpoint_summary_with_no_routes(self):
        """Test endpoint summary with app that has no routes"""
        app = FastAPI(title="Empty App")
        doc_gen = APIDocumentationGenerator(app)

        summary = doc_gen.get_endpoint_summary()

        assert summary["total_endpoints"] == 0
        assert summary["endpoints"] == []
        assert summary["by_method"] == {}
        assert summary["by_tag"] == {}

    def test_markdown_generation_with_empty_app(self):
        """Test markdown generation with empty app"""
        app = FastAPI(title="Empty App")
        doc_gen = APIDocumentationGenerator(app)

        markdown = doc_gen.generate_markdown_documentation()

        # Should still generate valid markdown
        assert markdown.startswith("# API Documentation")
        assert "## Authentication" in markdown


# ==================== Test Edge Cases ====================

class TestDocumentationEdgeCases:
    """Test suite for edge cases"""

    def test_special_characters_in_description(self, sample_fastapi_app):
        """Test handling of special characters in descriptions"""
        app = FastAPI(
            title="Test App <>&\"",
            description="Description with **markdown** and `code`"
        )
        doc_gen = APIDocumentationGenerator(app)

        openapi_schema = doc_gen.app.openapi()

        # Special characters should be preserved
        assert "Test App" in openapi_schema["info"]["title"]

    def test_very_long_endpoint_path(self, sample_fastapi_app):
        """Test handling of very long endpoint paths"""
        app = FastAPI(title="Test App")
        router = APIRouter()

        long_path = "/a" * 100  # Very long path

        @router.get(long_path)
        async def long_endpoint():
            return {"message": "long path"}

        app.include_router(router)
        doc_gen = APIDocumentationGenerator(app)

        # Should handle long paths without error
        summary = doc_gen.get_endpoint_summary()
        assert summary["total_endpoints"] > 0

    def test_unicode_in_documentation(self, sample_fastapi_app):
        """Test handling of Unicode characters in documentation"""
        app = FastAPI(
            title="测试应用",
            description="应用描述 with emoji 🚀"
        )
        doc_gen = APIDocumentationGenerator(app)

        openapi_schema = doc_gen.app.openapi()

        # Unicode should be preserved
        assert "测试应用" in openapi_schema["info"]["title"]

    def test_multiple_tags_on_endpoint(self, sample_fastapi_app):
        """Test endpoint with multiple tags"""
        app = FastAPI(title="Test App")
        router = APIRouter()

        @router.get("/multi-tag", tags=["Tag1", "Tag2", "Tag3"])
        async def multi_tag_endpoint():
            return {"message": "multi"}

        app.include_router(router)
        doc_gen = APIDocumentationGenerator(app)

        summary = doc_gen.get_endpoint_summary()

        # Endpoint should have all tags
        multi_tag_ep = next(ep for ep in summary["endpoints"] if ep["path"] == "/multi-tag")
        assert len(multi_tag_ep["tags"]) == 3
        assert "Tag1" in multi_tag_ep["tags"]
        assert "Tag2" in multi_tag_ep["tags"]
        assert "Tag3" in multi_tag_ep["tags"]


# ==================== Integration Tests ====================

class TestDocumentationIntegration:
    """Integration tests for documentation system"""

    def test_full_documentation_workflow(self, sample_fastapi_app):
        """Test complete documentation generation workflow"""
        # Create documentation generator
        config = DocumentationConfig(
            contact_email="integration@example.com"
        )
        doc_gen = APIDocumentationGenerator(sample_fastapi_app, config)

        # Generate OpenAPI schema
        openapi_schema = doc_gen.app.openapi()
        assert openapi_schema is not None

        # Get endpoint summary
        summary = doc_gen.get_endpoint_summary()
        assert summary["total_endpoints"] > 0

        # Generate markdown documentation
        markdown = doc_gen.generate_markdown_documentation()
        assert "# API Documentation" in markdown

        # Export to files
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "openapi.json")
            md_path = os.path.join(tmpdir, "docs.md")

            doc_gen.export_openapi_json(json_path)
            doc_gen.export_markdown_docs(md_path)

            assert os.path.exists(json_path)
            assert os.path.exists(md_path)

            # Verify exported files
            with open(json_path) as f:
                exported_json = json.load(f)
            assert "openapi" in exported_json

            with open(md_path) as f:
                exported_md = f.read()
            assert "# API Documentation" in exported_md

    def test_documentation_api_router_integration(self, sample_fastapi_app):
        """Test documentation API router integration with FastAPI app"""
        # Include docs router
        sample_fastapi_app.include_router(docs_router)

        # Create client
        client = TestClient(sample_fastapi_app)

        # Test all documentation endpoints
        endpoints = [
            "/docs-api/health",
            "/docs-api/summary",
            "/docs-api/markdown",
            "/docs-api/openapi-schema",
            "/docs-api/endpoints"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200, f"Failed for {endpoint}"

    def test_openapi_schema_available_at_standard_path(self, sample_fastapi_app):
        """Test that OpenAPI schema is available at standard /openapi.json path"""
        client = TestClient(sample_fastapi_app)

        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
