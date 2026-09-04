"""Contract test for GET /providers (spec FR-003)."""

import pytest


@pytest.mark.asyncio
async def test_aws_active_gcp_azure_disabled(client, auth_headers):
    resp = await client.get("/api/v1/providers", headers=auth_headers)
    assert resp.status_code == 200
    by_code = {p["code"]: p for p in resp.json()}
    assert by_code["aws"]["active"] is True
    assert by_code["gcp"]["active"] is False
    assert by_code["azure"]["active"] is False
