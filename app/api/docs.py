"""
API Documentation Generator Module

This module provides enhanced API documentation capabilities for the Enterprise RAG System.
It extends FastAPI's built-in OpenAPI documentation with additional features:
- Custom OpenAPI schema customization
- Markdown documentation generation
- API usage examples
- Response schema documentation
- Authentication/authorization documentation
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
import json
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


class DocumentationConfig(BaseModel):
    """Configuration for API documentation generation"""

    include_examples: bool = True
    include_response_schemas: bool = True
    include_auth_docs: bool = True
    include_rate_limiting: bool = True
    custom_tags: List[str] = []
    contact_email: str = "support@example.com"
    license_name: str = "MIT"


class APIDocumentationGenerator:
    """
    Enhanced API Documentation Generator

    Generates comprehensive API documentation including:
    - OpenAPI/Swagger schema customization
    - Markdown documentation
    - Usage examples
    - Response examples
    """

    def __init__(self, app: FastAPI, config: Optional[DocumentationConfig] = None):
        """
        Initialize the documentation generator

        Args:
            app: FastAPI application instance
            config: Documentation configuration
        """
        self.app = app
        self.config = config or DocumentationConfig()
        self._setup_custom_openapi()

    def _setup_custom_openapi(self):
        """Setup custom OpenAPI schema with enhanced documentation"""

        def custom_openapi():
            """Generate custom OpenAPI schema"""
            if self.app.openapi_schema:
                return self.app.openapi_schema

            openapi_schema = get_openapi(
                title=self.app.title,
                version=self.app.version,
                description=self._get_enhanced_description(),
                routes=self.app.routes,
                servers=[
                    {"url": "http://localhost:8000", "description": "Local development server"},
                    {"url": "https://api.example.com", "description": "Production server"},
                ],
            )

            # Add custom contact and license info
            openapi_schema["info"]["contact"] = {
                "name": "API Support",
                "email": self.config.contact_email,
            }
            openapi_schema["info"]["license"] = {
                "name": self.config.license_name,
                "url": "https://opensource.org/licenses/MIT",
            }

            # Add tags documentation
            openapi_schema["tags"] = self._get_tags_documentation()

            # Add components for common schemas.
            # Merge rather than replace: get_openapi() already populated
            # components.schemas from the routes' request/response models,
            # and overwriting it would leave every $ref dangling.
            components = openapi_schema.setdefault("components", {})
            for key, value in self._get_components_schemas().items():
                components.setdefault(key, {}).update(value)

            # Add security schemes
            if self.config.include_auth_docs:
                openapi_schema["components"]["securitySchemes"] = {
                    "ApiKeyAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-API-Key",
                        "description": "API key for authentication"
                    },
                    "BearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                        "description": "JWT token for authentication"
                    }
                }

            self.app.openapi_schema = openapi_schema
            return openapi_schema

        self.app.openapi = custom_openapi

    def _get_enhanced_description(self) -> str:
        """Get enhanced API description with markdown formatting"""
        return f"""
# {self.app.title}

{self.app.description or ''}

## Features

- **Multi-Format Document Support**: PDF, Markdown, Docx, HTML, Confluence, Notion
- **Hybrid Search Engine**: Semantic search + BM25 keyword search
- **Advanced RAG Techniques**: Query expansion, context compression, re-ranking
- **Streaming Responses**: Real-time query results with Server-Sent Events (SSE)
- **Metadata Filtering**: Advanced filtering with comparison and logical operators
- **Query Suggestions**: Intelligent query completion based on history and trends
- **Analytics Dashboard**: Real-time system metrics and usage analytics

## Authentication

This API supports multiple authentication methods:

1. **API Key**: Include your API key in the `X-API-Key` header
2. **Bearer Token**: Include your JWT token in the `Authorization: Bearer <token>` header

## Rate Limiting

API requests are rate limited to ensure fair usage:
- Default: 100 requests per minute
- Burst: Up to 200 requests in short bursts

Rate limit headers are included in all responses:
- `X-RateLimit-Limit`: Request limit per window
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when the limit resets

## Response Format

All API responses follow a consistent format:

**Success Response**:
```json
{{
  "answer": "Response text",
  "sources": [...],
  "confidence": 0.95,
  "latency_ms": 150
}}
```

**Error Response**:
```json
{{
  "detail": "Error message description"
}}
```

## Versioning

This API supports versioning through URL paths:
- `/api/v1/`: Version 1 (stable, backward compatible)
- `/api/v2/`: Version 2 (latest features, may have breaking changes)

## Documentation

- **Swagger UI**: `/docs` - Interactive API documentation
- **ReDoc**: `/redoc` - Alternative documentation viewer
- **OpenAPI JSON**: `/openapi.json` - Raw OpenAPI schema

Generated at: {datetime.now(timezone.utc).isoformat()}
"""

    def _get_tags_documentation(self) -> List[Dict[str, Any]]:
        """Get tag documentation for API endpoints"""
        tags = [
            {
                "name": "Query",
                "description": "Query endpoints for asking questions and retrieving information from the RAG system",
                "externalDocs": {
                    "description": "Query usage guide",
                    "url": "https://docs.example.com/query-guide"
                }
            },
            {
                "name": "Ingest",
                "description": "Document ingestion endpoints for adding and processing documents",
                "externalDocs": {
                    "description": "Ingestion guide",
                    "url": "https://docs.example.com/ingestion-guide"
                }
            },
            {
                "name": "Documents",
                "description": "Document management endpoints for listing, deleting, and managing documents",
            },
            {
                "name": "Health",
                "description": "Health check and monitoring endpoints",
            },
            {
                "name": "Analytics",
                "description": "System analytics and metrics endpoints",
            },
            {
                "name": "Documentation",
                "description": "API documentation and schema endpoints",
            },
        ]
        return tags

    def _get_components_schemas(self) -> Dict[str, Any]:
        """Get common component schemas for documentation"""
        return {
            "schemas": {
                "ErrorResponse": {
                    "type": "object",
                    "properties": {
                        "detail": {
                            "type": "string",
                            "description": "Human-readable error message"
                        },
                        "error_code": {
                            "type": "string",
                            "description": "Machine-readable error code"
                        },
                        "status_code": {
                            "type": "integer",
                            "description": "HTTP status code"
                        }
                    },
                    "required": ["detail"]
                },
                "SuccessResponse": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Success message"
                        },
                        "data": {
                            "type": "object",
                            "description": "Response data"
                        }
                    }
                }
            }
        }

    def generate_markdown_documentation(self) -> str:
        """
        Generate comprehensive markdown documentation for all API endpoints

        Returns:
            Markdown formatted documentation string
        """
        md_lines = [
            "# API Documentation",
            "",
            f"**Version**: {self.app.version}",
            f"**Base URL**: `http://localhost:8000`",
            "",
            "## Table of Contents",
            "",
            "- [Authentication](#authentication)",
            "- [Rate Limiting](#rate-limiting)",
            "- [Endpoints](#endpoints)",
            "- [Response Codes](#response-codes)",
            "- [Examples](#examples)",
            "",
            "## Authentication",
            "",
            "This API uses API key authentication. Include your API key in the request header:",
            "",
            "```http",
            "X-API-Key: your-api-key-here",
            "```",
            "",
            "## Rate Limiting",
            "",
            "- **100 requests per minute** per API key",
            "- Rate limit headers are included in all responses",
            "",
            "## Endpoints",
            "",
        ]

        # Add endpoint documentation
        openapi_schema = self.app.openapi()
        if openapi_schema and "paths" in openapi_schema:
            for path, methods in openapi_schema["paths"].items():
                for method, details in methods.items():
                    if method.lower() in ["get", "post", "put", "delete"]:
                        md_lines.extend(self._format_endpoint_doc(path, method, details))

        # Add response codes section
        md_lines.extend([
            "",
            "## Response Codes",
            "",
            "| Code | Description |",
            "|------|-------------|",
            "| 200  | Success |",
            "| 201  | Created |",
            "| 400  | Bad Request |",
            "| 401  | Unauthorized |",
            "| 429  | Rate Limit Exceeded |",
            "| 500  | Internal Server Error |",
            "",
            "## Examples",
            "",
            "### Query Example",
            "",
            "```bash",
            'curl -X POST "http://localhost:8000/api/v1/query/" \\',
            '  -H "Content-Type: application/json" \\',
            '  -H "X-API-Key: your-key" \\',
            '  -d \'{"query": "What is the company policy?"}\'',
            "```",
            "",
            "### Streaming Query Example",
            "",
            "```bash",
            'curl -X POST "http://localhost:8000/api/v1/query/stream" \\',
            '  -H "Content-Type: application/json" \\',
            '  -d \'{"query": "Tell me about benefits"}\'',
            "```",
            "",
            "---",
            "",
            f"*Generated at {datetime.now(timezone.utc).isoformat()}*",
        ])

        return "\n".join(md_lines)

    def _format_endpoint_doc(self, path: str, method: str, details: Dict[str, Any]) -> List[str]:
        """Format a single endpoint documentation section"""
        lines = [
            f"### {method.upper()} {path}",
            "",
        ]

        if "summary" in details:
            lines.append(f"**Summary**: {details['summary']}")

        if "description" in details:
            lines.append(f"**Description**: {details['description']}")

        lines.append("")

        # Add parameters
        if "parameters" in details and details["parameters"]:
            lines.append("**Parameters**:")
            lines.append("")
            for param in details["parameters"]:
                required = " (required)" if param.get("required", False) else " (optional)"
                lines.append(
                    f"- `{param['name']}` ({param.get('in', 'query')}){required}: "
                    f"{param.get('description', 'No description')}"
                )
            lines.append("")

        # Add request body
        if "requestBody" in details:
            lines.append("**Request Body**:")
            content = details["requestBody"].get("content", {})
            if "application/json" in content:
                schema = content["application/json"].get("schema", {})
                lines.append("```json")
                lines.append(self._format_schema(schema))
                lines.append("```")
            lines.append("")

        # Add responses
        if "responses" in details:
            lines.append("**Responses**:")
            for code, response in details["responses"].items():
                lines.append(f"- **{code}**: {response.get('description', 'No description')}")
            lines.append("")

        return lines

    def _format_schema(self, schema: Dict[str, Any], indent: int = 0) -> str:
        """Format a schema for markdown display"""
        # Simplified schema formatter
        if "$ref" in schema:
            return schema["$ref"].split("/")[-1]
        if "properties" in schema:
            lines = ["{"]
            for name, prop in schema["properties"].items():
                prop_type = prop.get("type", "unknown")
                required = ""  # Check if required
                lines.append(f"  {indent * '  '}\"{name}\": {prop_type}{required}")
            lines.append(f"{indent * '  '}}}")
            return "\n".join(lines)
        return str(schema)

    def get_endpoint_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all API endpoints

        Returns:
            Dictionary with endpoint statistics and information
        """
        openapi_schema = self.app.openapi()
        summary = {
            "total_endpoints": 0,
            "by_tag": {},
            "by_method": {},
            "endpoints": []
        }

        if openapi_schema and "paths" in openapi_schema:
            for path, methods in openapi_schema["paths"].items():
                for method, details in methods.items():
                    if method.lower() in ["get", "post", "put", "delete", "patch"]:
                        summary["total_endpoints"] += 1

                        # Count by method
                        method_upper = method.upper()
                        summary["by_method"][method_upper] = summary["by_method"].get(method_upper, 0) + 1

                        # Get tags
                        tags = details.get("tags", ["default"])
                        for tag in tags:
                            summary["by_tag"][tag] = summary["by_tag"].get(tag, 0) + 1

                        # Add endpoint details
                        summary["endpoints"].append({
                            "path": path,
                            "method": method_upper,
                            "summary": details.get("summary", ""),
                            "tags": tags,
                            "operation_id": details.get("operationId", "")
                        })

        return summary

    def export_openapi_json(self, filepath: str) -> None:
        """
        Export OpenAPI schema to JSON file

        Args:
            filepath: Path to save the JSON file
        """
        openapi_schema = self.app.openapi()

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(openapi_schema, f, indent=2, ensure_ascii=False)

        logger.info(f"OpenAPI schema exported to {filepath}")

    def export_markdown_docs(self, filepath: str) -> None:
        """
        Export markdown documentation to file

        Args:
            filepath: Path to save the markdown file
        """
        markdown = self.generate_markdown_documentation()

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown)

        logger.info(f"Markdown documentation exported to {filepath}")


# Singleton instance
_doc_generator: Optional[APIDocumentationGenerator] = None


def get_documentation_generator(app: Optional[FastAPI] = None) -> APIDocumentationGenerator:
    """
    Get or create the documentation generator singleton

    Args:
        app: FastAPI application instance (required on first call)

    Returns:
        APIDocumentationGenerator instance
    """
    global _doc_generator

    if _doc_generator is None:
        if app is None:
            raise RuntimeError(
                "Documentation generator not initialized. "
                "Pass FastAPI app on first call."
            )
        _doc_generator = APIDocumentationGenerator(app)

    return _doc_generator


# FastAPI router for documentation endpoints
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/docs-api", tags=["Documentation"])


class DocumentationExportRequest(BaseModel):
    """Request model for documentation export"""
    format: str = "markdown"  # markdown or json
    include_examples: bool = True


@router.get("/summary")
async def get_api_summary():
    """
    Get API endpoint summary

    Returns statistics and information about all API endpoints.
    """
    try:
        from app.main import app

        doc_gen = get_documentation_generator(app)
        summary = doc_gen.get_endpoint_summary()

        return {
            "status": "success",
            "data": summary
        }

    except Exception as e:
        logger.error(f"Failed to get API summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate API summary: {str(e)}"
        )


@router.get("/markdown")
async def get_markdown_docs():
    """
    Get API documentation in Markdown format

    Returns comprehensive API documentation formatted as Markdown.
    """
    try:
        from app.main import app

        doc_gen = get_documentation_generator(app)
        markdown = doc_gen.generate_markdown_documentation()

        return {
            "status": "success",
            "format": "markdown",
            "documentation": markdown
        }

    except Exception as e:
        logger.error(f"Failed to generate markdown docs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate documentation: {str(e)}"
        )


@router.get("/openapi-schema")
async def get_openapi_schema():
    """
    Get the raw OpenAPI schema

    Returns the complete OpenAPI 3.0.x schema as JSON.
    """
    try:
        from app.main import app

        return app.openapi()

    except Exception as e:
        logger.error(f"Failed to get OpenAPI schema: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve OpenAPI schema: {str(e)}"
        )


@router.get("/endpoints")
async def list_endpoints():
    """
    List all available API endpoints

    Returns a structured list of all endpoints with methods, paths, and descriptions.
    """
    try:
        from app.main import app

        doc_gen = get_documentation_generator(app)
        summary = doc_gen.get_endpoint_summary()

        return {
            "status": "success",
            "total": summary["total_endpoints"],
            "endpoints": summary["endpoints"]
        }

    except Exception as e:
        logger.error(f"Failed to list endpoints: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list endpoints: {str(e)}"
        )


@router.get("/health", status_code=200)
async def docs_health_check():
    """Health check for documentation API"""
    return {
        "status": "healthy",
        "service": "API Documentation Generator"
    }
