"""MCP server for Splunk SOAR (Phantom)."""

from .server import build_server

__version__ = "0.1.0"
__all__ = ["build_server", "__version__"]
