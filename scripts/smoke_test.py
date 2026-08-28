#!/usr/bin/env python3
"""Connect to the server over stdio and exercise it, as a real MCP client would.

Everything here runs without reaching the SOAR instance: it checks the handshake,
the tool/resource/prompt inventory, and a block-builder round trip that is pure
local computation. Pass --live to additionally call soar_system_info, which does
need a reachable instance.

    python scripts/smoke_test.py
    python scripts/smoke_test.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PASS, FAIL = "  ok  ", " FAIL "


def check(label: str, condition: bool, detail: str = "") -> bool:
    print(f"[{PASS if condition else FAIL}] {label}{f' — {detail}' if detail else ''}")
    return condition


def text_of(result) -> str:
    return "".join(
        block.text for block in result.content if getattr(block, "type", "") == "text"
    ).strip()


async def main(live: bool) -> int:
    env = dict(os.environ)
    env.setdefault("SPLUNK_SOAR_URL", "https://soar.invalid")
    env.setdefault("SPLUNK_SOAR_API", "smoke-test-placeholder")
    env.setdefault("SOAR_MCP_MODE", "readonly")

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "splunk_soar_mcp"], env=env
    )

    ok = True
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        info = await session.initialize()
        ok &= check("handshake", True, f"{info.server_info.name} {info.server_info.version}")

        tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        ok &= check("tools listed", len(tools) >= 30, f"{len(tools)} tools")
        ok &= check(
            "readonly mode registers no mutating tool",
            not ({"soar_add_comment", "soar_run_playbook"} & set(tools)),
        )
        ok &= check(
            "every tool is described",
            all(tool.description for tool in tools.values()),
        )

        resources = {str(r.uri) for r in (await session.list_resources()).resources}
        ok &= check("resources listed", "soar://reference/datapaths" in resources,
                    f"{len(resources)} resources")

        prompts = {p.name for p in (await session.list_prompts()).prompts}
        ok &= check("prompts listed", "debug_playbook_run" in prompts, ", ".join(sorted(prompts)))

        contents = (await session.read_resource("soar://reference/datapaths")).contents
        body = getattr(contents[0], "text", "")
        ok &= check("resource reads", "custom_function_result" in body, f"{len(body)} chars")

        built = text_of(
            await session.call_tool(
                "soar_build_format_block",
                {"name": "Smoke Test", "template": "hello {0}", "parameters": ["container:name"]},
            )
        )
        ok &= check("block builder returns base64", len(built) > 100, f"{len(built)} chars")

        decoded = text_of(
            await session.call_tool(
                "soar_decode_vpe_block", {"payload": built, "summary_only": True}
            )
        )
        ok &= check(
            "block round-trips through decode",
            "format" in decoded and "smoke_test" in decoded,
        )

        failed = await session.call_tool(
            "soar_build_code_block", {"name": "Bad", "user_code": "    if True\n"}
        )
        ok &= check(
            "syntax errors are reported, not raised",
            "does not compile" in text_of(failed),
        )

        if live:
            result = await session.call_tool("soar_system_info", {})
            print("\n--- soar_system_info ---")
            print(text_of(result))
            ok &= check("live instance reachable", not result.isError)

    print("\n" + ("all checks passed" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="also call the real instance")
    raise SystemExit(asyncio.run(main(parser.parse_args().live)))
