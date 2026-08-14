"""MCP server exposing the wger REST API as tools.

The version is declared once, in ``pyproject.toml``, and read back from the
installed distribution's metadata here — the one lookup the whole package
shares, so nothing can drift from the release that was actually built.
"""

from importlib.metadata import version

__version__ = version("wger-mcp")
