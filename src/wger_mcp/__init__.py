"""MCP server exposing the wger REST API as tools.

The package version lives in ``pyproject.toml`` and is read back from the
installed distribution's metadata here — once, for the whole package, so that
``api_client``'s User-Agent and the ``--version`` flag cannot report different
numbers and neither can drift from the release that was actually built.
"""

from importlib.metadata import version

__version__ = version("wger-mcp")
