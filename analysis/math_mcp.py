"""Client for the Mathematics MCP server (https://mathematics.fastmcp.app/mcp)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_MATHEMATICS_MCP_URL = os.environ.get(
    "MATHEMATICS_MCP_URL",
    "https://mathematics.fastmcp.app/mcp",
)


@dataclass
class MCPCallResult:
    success: bool
    result: Any = None
    error: str | None = None


class MathematicsMCPClient:
    """Streamable HTTP client for Mathematics MCP tools."""

    def __init__(self, url: str = DEFAULT_MATHEMATICS_MCP_URL, timeout: float = 30.0):
        self.url = url
        self.timeout = timeout

    def _parse_sse_payload(self, body: str) -> dict[str, Any]:
        for line in body.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise ValueError("No SSE data payload in MCP response")

    def _request(self, method: str, params: dict[str, Any] | None = None) -> MCPCallResult:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
            message = self._parse_sse_payload(body)
            if "error" in message:
                return MCPCallResult(success=False, error=str(message["error"]))
            result = message.get("result", {})
            if result.get("isError"):
                text = result.get("content", [{}])[0].get("text", "MCP tool error")
                return MCPCallResult(success=False, error=text)
            if "structuredContent" in result:
                return MCPCallResult(success=True, result=result["structuredContent"])
            content = result.get("content", [])
            if content and content[0].get("type") == "text":
                return MCPCallResult(success=True, result=json.loads(content[0]["text"]))
            return MCPCallResult(success=True, result=result)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return MCPCallResult(success=False, error=str(exc))

    def calculate_statistics(self, data: list[float], operation: str) -> MCPCallResult:
        return self._request(
            "tools/call",
            {"name": "calculate_statistics", "arguments": {"data": data, "operation": operation}},
        )

    def batch_calculate(self, expressions: list[str]) -> MCPCallResult:
        return self._request(
            "tools/call",
            {"name": "batch_calculate", "arguments": {"expressions": expressions}},
        )

    def calculate_expression(self, expr: str) -> MCPCallResult:
        return self._request(
            "tools/call",
            {"name": "calculate_expression", "arguments": {"expr": expr}},
        )

    def ping(self) -> MCPCallResult:
        return self.calculate_expression("1 + 1")


def local_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def local_eval(expression: str) -> float:
    allowed = {"__builtins__": {}}
    return float(eval(expression, allowed, {}))  # noqa: S307 — trusted internal expressions only


def statistics_with_fallback(
    client: MathematicsMCPClient | None,
    data: list[float],
    operation: str,
) -> tuple[float | None, str]:
    """Return (value, source) where source is 'mcp' or 'local'."""
    clean = [float(v) for v in data if v is not None]
    if not clean:
        return None, "local"

    if client is not None:
        response = client.calculate_statistics(clean, operation)
        if response.success and isinstance(response.result, dict) and "result" in response.result:
            return float(response.result["result"]), "mcp"

    if operation == "mean":
        return local_mean(clean), "local"
    if operation == "median":
        ordered = sorted(clean)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid], "local"
        return (ordered[mid - 1] + ordered[mid]) / 2, "local"
    if operation == "stdev" and len(clean) > 1:
        mean = local_mean(clean)
        variance = sum((x - mean) ** 2 for x in clean) / (len(clean) - 1)
        return variance**0.5, "local"
    return local_mean(clean), "local"


def batch_eval_with_fallback(
    client: MathematicsMCPClient | None,
    expressions: list[str],
) -> list[tuple[float | None, str]]:
    if client is not None:
        response = client.batch_calculate(expressions)
        if response.success and isinstance(response.result, dict):
            outputs: list[tuple[float | None, str]] = []
            for item in response.result.get("results", []):
                if item.get("success"):
                    outputs.append((float(item["result"]), "mcp"))
                else:
                    outputs.append((None, "mcp"))
            if len(outputs) == len(expressions):
                return outputs

    results: list[tuple[float | None, str]] = []
    for expression in expressions:
        try:
            results.append((local_eval(expression), "local"))
        except Exception:
            results.append((None, "local"))
    return results
