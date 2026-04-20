# Feature Idea: FastAPI MCP Server Wrapper for LinkedIn SSI Booster

## Overview
Wrap the main CLI logic of LinkedIn SSI Booster in a FastAPI-based Model Context Protocol (MCP) server, enabling programmatic, real-time, and multi-client access to all core automation, curation, and explainability features via HTTP endpoints.

## Problem Statement (Project Context)
- Current tool is CLI-only, limiting integration with other systems, UIs, and automation workflows.
- No standard API for triggering content generation, curation, or retrieving learning/explainability reports.
- Modern agent and orchestration stacks (e.g., LangChain, FastMCP, Azure AI Studio) expect HTTP/JSON interfaces for tool integration.

## Proposed Solution
- Implement a FastAPI server that exposes the main.py CLI entrypoints as RESTful endpoints, following the MCP (Model Context Protocol) conventions for tool/agent interoperability.
- Each CLI function (generate, curate, explain, report, schedule) becomes an HTTP endpoint.
- Use Pydantic models for request/response validation and OpenAPI schema generation.
- Add a /health and /version endpoint for ops.
- Optionally, support streaming responses for long-running tasks (generation, curation).

## Expected Benefits (Project User Impact)
- Enables integration with agent frameworks, web UIs, and external schedulers.
- Allows real-time triggering and monitoring of content workflows from any client.
- Makes the system composable in larger AI pipelines (e.g., RAG, workflow orchestration, human-in-the-loop review).
- Opens the door to cloud deployment, multi-user access, and SaaS scenarios.

## Technical Considerations (Project Integration)
- Use FastAPI (Python 3.11+) for async HTTP server, Pydantic for models.
- Wrap main.py logic in callable functions; avoid code duplication.
- Ensure all API calls are stateless and idempotent where possible.
- Use absolute imports and maintain config/env loading conventions.
- Secure endpoints with API key or OAuth2 (future phase).
- Add CORS support for web UI integration.
- Ensure all external API calls (Buffer, Anthropic) respect --dry-run and error handling conventions.

## Project System Integration
- main.py: Refactor CLI logic into importable functions for API reuse.
- services/: Expose core service methods as internal API for FastAPI layer.
- requirements.txt: Add fastapi, uvicorn, pydantic.
- tests/: Add API endpoint tests for all new routes.
- docs/: Document all endpoints and usage patterns.

## Initial Scope
- /generate, /curate, /explain, /report, /schedule endpoints
- /health, /version endpoints
- Pydantic models for all request/response types
- CLI and API must remain in sync (no feature drift)

## Success Criteria
- All CLI features are accessible via HTTP API with matching behavior
- OpenAPI docs auto-generated and accurate
- API passes unit/integration tests for all endpoints
- No regression in CLI or scheduling workflows
- Documentation updated for API usage and deployment
