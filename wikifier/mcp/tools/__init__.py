"""MCP tool modules. Live server uses server_impl; these are optional registrars."""

from .workflow import register_tools as register_workflow_tools
from .intel import register_tools as register_intel_tools
from .status import register_tools as register_status_tools

__all__ = [
    "register_workflow_tools",
    "register_intel_tools",
    "register_status_tools",
]
