"""Register Agent Studio's 20 read-only text tools in AI App Server's native MCP registry.

Only called from an approved per-app app/mcp_tools.py file when MCP is enabled.
"""
from .builtin_tools import public_tools, execute


def register_tools(registry):
    for item in public_tools():
        identifier=item['id']
        name='studio_'+identifier.split(':',1)[-1]
        schema={
            'type':'object',
            'properties':{'text':{'type':'string','maxLength':4096}},
            'required':['text'],
            'additionalProperties':False,
        }
        @registry.tool(name=name,description=item['description'][:500],input_schema=schema,read_only=True)
        def handle(text:str, identifier=identifier):
            return str(execute(identifier,text))[:16000]
