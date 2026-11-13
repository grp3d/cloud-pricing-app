"""The agent routes and stream events are in the OpenAPI schema (023, contracts/agent-api.md;
constitution Principle IV): the frontend's types are generated from it."""

from __future__ import annotations

from src.main import app


def test_agent_routes_are_documented():
    paths = app.openapi()["paths"]
    for path, method in [
        ("/api/v1/agent/status", "get"),
        ("/api/v1/agent/session", "post"),
        ("/api/v1/agent/session", "get"),
        ("/api/v1/agent/session/messages", "post"),
        ("/api/v1/agent/session/messages/{message_id}/retry", "post"),
        ("/api/v1/agent/session/operations", "get"),
    ]:
        assert method in paths[path], (method, path)


def test_stream_events_are_typed_in_the_schema():
    schema = app.openapi()
    stream = schema["paths"]["/api/v1/agent/session/messages"]["post"]["responses"]
    assert stream["200"]["content"]["text/event-stream"]["schema"]["$ref"].endswith(
        "/AgentStreamEnvelope"
    )
    assert stream["423"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/AgentRefusalOut"
    )
    components = schema["components"]["schemas"]
    for name in ("AgentAcceptedEvent", "AgentStatusEvent", "AgentTextEvent",
                 "AgentOperationEvent", "AgentDoneEvent", "AgentErrorEvent"):
        assert name in components, name
    envelope = components["AgentStreamEnvelope"]["properties"]["data"]
    assert envelope["discriminator"]["propertyName"] == "event"
