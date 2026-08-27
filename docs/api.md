# API Documentation

This document provides comprehensive information about the Enterprise RAG System API documentation features.

## Overview

The Enterprise RAG System includes an enhanced API documentation generator that extends FastAPI's built-in OpenAPI/Swagger documentation with additional capabilities:

- **Custom OpenAPI Schema**: Enhanced OpenAPI 3.0.x schema with detailed descriptions
- **Markdown Documentation**: Automatically generated markdown documentation for all endpoints
- **Endpoint Summaries**: Structured summaries of all API endpoints with statistics
- **Documentation Export**: Export OpenAPI schemas and markdown docs to files
- **Interactive Documentation**: Swagger UI and ReDoc integration

## Features

### 1. Enhanced OpenAPI Schema

The system automatically generates a comprehensive OpenAPI 3.0.x schema that includes:

- **API Metadata**: Title, version, description, contact info, license
- **Tag Documentation**: Descriptive tags for organizing endpoints
- **Security Schemes**: API key and JWT bearer authentication
- **Component Schemas**: Reusable schemas for common responses
- **Server Configuration**: Development and production server URLs

#### Accessing OpenAPI Schema

```bash
# Get raw OpenAPI JSON schema
curl http://localhost:8000/openapi.json

# Get via documentation API
curl http://localhost:8000/docs-api/openapi-schema
```

### 2. Interactive Documentation

The system provides two interactive documentation interfaces:

#### Swagger UI
- **URL**: `http://localhost:8000/docs`
- **Features**:
  - Interactive API exploration
  - Try-out functionality for all endpoints
  - Request/response examples
  - Schema validation
  - Authentication support

#### ReDoc
- **URL**: `http://localhost:8000/redoc`
- **Features**:
  - Clean, responsive documentation layout
  - Three-panel design (navigation, content, schemas)
  - Searchable endpoint reference
  - Code samples

### 3. Documentation API Endpoints

The system provides dedicated endpoints for accessing API documentation:

#### Get API Summary

```bash
GET /docs-api/summary
```

Returns statistics and information about all API endpoints:

```json
{
  "status": "success",
  "data": {
    "total_endpoints": 25,
    "by_tag": {
      "Query": 8,
      "Ingest": 5,
      "Documents": 4,
      "Health": 2,
      "Analytics": 3,
      "Documentation": 3
    },
    "by_method": {
      "GET": 12,
      "POST": 10,
      "DELETE": 2,
      "PUT": 1
    },
    "endpoints": [
      {
        "path": "/api/v1/query/",
        "method": "POST",
        "summary": "Query the RAG system",
        "tags": ["Query"],
        "operation_id": "query"
      }
    ]
  }
}
```

#### Get Markdown Documentation

```bash
GET /docs-api/markdown
```

Returns comprehensive API documentation in Markdown format:

```json
{
  "status": "success",
  "format": "markdown",
  "documentation": "# API Documentation\n\n..."
}
```

#### List All Endpoints

```bash
GET /docs-api/endpoints
```

Returns a structured list of all available endpoints:

```json
{
  "status": "success",
  "total": 25,
  "endpoints": [
    {
      "path": "/api/v1/query/",
      "method": "POST",
      "tags": ["Query"],
      "summary": "Query the RAG system",
      "operation_id": "query_query"
    }
  ]
}
```

#### Health Check

```bash
GET /docs-api/health
```

Returns the health status of the documentation service:

```json
{
  "status": "healthy",
  "service": "API Documentation Generator"
}
```

## Usage Examples

### Example 1: Accessing Interactive Documentation

```bash
# Open Swagger UI in browser
xdg-open http://localhost:8000/docs

# Or open ReDoc
xdg-open http://localhost:8000/redoc
```

### Example 2: Exporting Documentation

Export OpenAPI schema and markdown documentation using Python:

```python
from app.main import app
from app.api.docs import APIDocumentationGenerator

# Create documentation generator
doc_gen = APIDocumentationGenerator(app)

# Export OpenAPI schema
doc_gen.export_openapi_json("openapi-schema.json")

# Export markdown documentation
doc_gen.export_markdown_docs("api-documentation.md")
```

### Example 3: Getting Endpoint Information

```bash
# Get summary of all endpoints
curl http://localhost:8000/docs-api/summary | jq

# Get specific endpoint count by tag
curl http://localhost:8000/docs-api/summary | jq '.data.by_tag.Query'

# List all POST endpoints
curl http://localhost:8000/docs-api/endpoints | jq '.endpoints[] | select(.method == "POST")'
```

### Example 4: Generating Custom Documentation

```python
from app.api.docs import APIDocumentationGenerator, DocumentationConfig
from app.main import app

# Create custom configuration
config = DocumentationConfig(
    include_examples=True,
    include_response_schemas=True,
    include_auth_docs=True,
    contact_email="support@yourcompany.com",
    license_name="Proprietary"
)

# Initialize with custom config
doc_gen = APIDocumentationGenerator(app, config)

# Get endpoint summary
summary = doc_gen.get_endpoint_summary()
print(f"Total endpoints: {summary['total_endpoints']}")

# Generate markdown
markdown = doc_gen.generate_markdown_documentation()
with open("custom-api-docs.md", "w") as f:
    f.write(markdown)
```

## Configuration

The documentation system can be configured using the `DocumentationConfig` class:

```python
from app.api.docs import DocumentationConfig

config = DocumentationConfig(
    include_examples=True,        # Include usage examples
    include_response_schemas=True, # Include response schema docs
    include_auth_docs=True,        # Include authentication docs
    include_rate_limiting=True,    # Include rate limiting info
    custom_tags=[],                # Additional custom tags
    contact_email="support@example.com",  # Contact email
    license_name="MIT"             # License name
)
```

## Response Format

### Success Response

All documentation endpoints return a consistent success response format:

```json
{
  "status": "success",
  "data": { ... }
}
```

### Error Response

Error responses follow this format:

```json
{
  "detail": "Error message description",
  "status_code": 500
}
```

## API Versioning

The Enterprise RAG System supports API versioning through URL paths:

- **v1 API**: `/api/v1/*` - Stable, backward compatible
- **v2 API**: `/api/v2/*` - Latest features, may have breaking changes

Documentation is automatically generated for all versions.

## Authentication

The API supports multiple authentication methods:

1. **API Key**: Include in `X-API-Key` header
   ```http
   X-API-Key: your-api-key-here
   ```

2. **Bearer Token**: Include JWT token in Authorization header
   ```http
   Authorization: Bearer your-jwt-token
   ```

## Rate Limiting

API requests are rate limited:
- **Default**: 100 requests per minute
- **Burst**: Up to 200 requests in short bursts

Rate limit headers are included in all responses:
- `X-RateLimit-Limit`: Request limit per window
- `X-RateLimit-Remaining`: Remaining requests
- `X-RateLimit-Reset`: Unix timestamp when limit resets

## Integration with FastAPI

The documentation system integrates seamlessly with FastAPI:

```python
from fastapi import FastAPI
from app.api.docs import router as docs_router

app = FastAPI(title="Your API")

# Include documentation router
app.include_router(docs_router)

# Custom OpenAPI schema is automatically configured
```

## Best Practices

1. **Keep Documentation Updated**: Add detailed docstrings to all endpoints
2. **Use Descriptive Tags**: Organize endpoints with meaningful tags
3. **Provide Examples**: Include usage examples in endpoint descriptions
4. **Document Responses**: Clearly document response formats and possible errors
5. **Version Consistency**: Ensure documentation matches API version

## Troubleshooting

### Documentation Not Loading

If interactive documentation doesn't load:
1. Check that the FastAPI app is running: `curl http://localhost:8000/`
2. Verify the docs router is included: Check `app.routes`
3. Check browser console for JavaScript errors

### OpenAPI Schema Missing Fields

If the OpenAPI schema is incomplete:
1. Ensure all endpoints have proper docstrings
2. Check that request/response models use Pydantic
3. Verify the custom OpenAPI function is properly configured

### Export Failures

If exporting documentation fails:
1. Check write permissions for the target directory
2. Ensure the file path is valid
3. Verify sufficient disk space

## Additional Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **OpenAPI Specification**: https://swagger.io/specification/
- **Swagger UI**: https://swagger.io/tools/swagger-ui/
- **ReDoc**: https://github.com/Redocly/redoc

## Support

For issues or questions about the API documentation system:
- Email: support@example.com
- GitHub Issues: [Repository Issues]
- Documentation: https://docs.example.com
