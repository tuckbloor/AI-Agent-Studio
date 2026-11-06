"""Project-owned, opt-in Agent Studio tools for the NATIVE AI App Server /mcp.

This file is only installed if app/mcp_tools.py did not already exist.
MCP remains disabled until enabled by an administrator in /admin.
"""
from studio_integration.mcp_registration import register_tools as register_studio_tools


def register_tools(registry):
    register_studio_tools(registry)
