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


def test_proposal_routes_and_events_are_documented():
    """025 (contracts/agent-api.md): the user's decisions on proposals, proposals in the session
    detail, and the two new stream events."""
    schema = app.openapi()
    paths = schema["paths"]
    for action in ("accept", "reject", "undo", "redo"):
        route = paths[f"/api/v1/agent/proposals/{{proposal_id}}/{action}"]["post"]
        assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] \
            .endswith("/ProposalActionOut"), action
    components = schema["components"]["schemas"]
    assert "proposals" in components["AgentSessionDetailOut"]["properties"]
    assert "proposal_ids" in components["AgentMessageOut"]["properties"]
    for name in ("AgentProposalEvent", "AgentOpenArchitectureEvent", "AgentProposalOut",
                 "ProposalCostOut", "ProposalUndoOut"):
        assert name in components, name
