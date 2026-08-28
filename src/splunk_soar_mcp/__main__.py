"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys

from .config import Mode


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="splunk-soar-mcp",
        description="MCP server for a Splunk SOAR (Phantom) instance.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
        help="Transport to serve on (default: stdio, which is what MCP clients launch).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for HTTP transports.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port for HTTP transports.")
    parser.add_argument(
        "--mode",
        choices=[m.value for m in Mode],
        help="Override SOAR_MCP_MODE for this run.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the tools this configuration exposes, then exit.",
    )
    args = parser.parse_args()

    from .config import load_settings
    from .server import build_server

    try:
        settings = load_settings()
    except Exception as exc:
        parser.exit(
            2,
            f"Configuration error: {exc}\n\n"
            "Set SPLUNK_SOAR_URL and SPLUNK_SOAR_API in the environment or a .env "
            "file. See .env.example.\n",
        )
    if args.mode:
        settings.mode = Mode(args.mode)

    server = build_server(settings)

    if args.list_tools:
        import anyio

        async def _dump() -> None:
            tools = await server.list_tools()
            print(f"mode: {settings.mode.value} — {len(tools)} tool(s)\n")
            for tool in sorted(tools, key=lambda t: t.name):
                first_line = (tool.description or "").strip().split("\n")[0]
                print(f"  {tool.name:<34} {first_line[:88]}")

        anyio.run(_dump)
        sys.exit(0)

    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run(args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
