import sys
from pathlib import Path

APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
from studio_integration.mcp_registration import register_tools

class DemoRegistry:
    def __init__(self):self.tools={}
    def tool(self,*,name,description,input_schema,read_only=True):
        assert name.startswith('studio_')
        assert read_only is True
        def wrapped(fn):self.tools[name]=fn;return fn
        return wrapped

def test_native_mcp_tools_register_and_execute():
    r=DemoRegistry();register_tools(r)
    assert len(r.tools)==20
    output=r.tools['studio_word_count']('Hello world')
    assert 'Words:' in output
    assert '2' in output
