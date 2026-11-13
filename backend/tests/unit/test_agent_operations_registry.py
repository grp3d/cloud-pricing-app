"""The operations registry (023, research R9, contracts/agent-internals.md)."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel

from src.agent.figures import FigureBook
from src.agent.operations import OperationContext, OperationResult, Registry, ToolError


class EchoArgs(BaseModel):
    text: str
    times: int = 1


class PriceArgs(BaseModel):
    duration: Literal["1_day", "1_month", "1_year"] = "1_month"


def _registry() -> Registry:
    registry = Registry()

    @registry.operation("echo", "Repeat some text.", EchoArgs)
    async def echo(ctx: OperationContext, args: EchoArgs) -> OperationResult:
        return OperationResult(data={"text": args.text * args.times}, summary={"n": args.times})

    @registry.operation("price", "Price it.", PriceArgs)
    async def price(ctx: OperationContext, args: PriceArgs) -> OperationResult:
        raise ToolError("nothing is open")

    return registry


def _ctx() -> OperationContext:
    return OperationContext(session=None, user=None, open_architecture_id=None,
                            figures=FigureBook())


def test_tool_specs_come_from_the_input_models():
    specs = {s.name: s for s in _registry().tool_specs()}
    assert set(specs) == {"echo", "price"}
    assert specs["echo"].description == "Repeat some text."
    schema = specs["echo"].input_schema
    assert schema["type"] == "object"
    assert schema["required"] == ["text"]
    assert set(schema["properties"]) == {"text", "times"}
    assert specs["price"].input_schema["properties"]["duration"]["enum"] == [
        "1_day", "1_month", "1_year"
    ]


async def test_runs_with_validated_arguments():
    result = await _registry().run(_ctx(), "echo", {"text": "ab", "times": 2})
    assert result.data == {"text": "abab"}


async def test_unknown_operation_is_a_tool_error():
    with pytest.raises(ToolError, match="unknown operation"):
        await _registry().run(_ctx(), "delete_everything", {})


async def test_invalid_arguments_are_a_tool_error():
    with pytest.raises(ToolError, match="invalid arguments"):
        await _registry().run(_ctx(), "echo", {"times": "many"})


async def test_an_operation_can_refuse_with_a_tool_error():
    with pytest.raises(ToolError, match="nothing is open"):
        await _registry().run(_ctx(), "price", {})
