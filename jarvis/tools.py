"""Typed allowlist. Foundation exposes reads only; no arbitrary shell or writes."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Tool:
    name: str
    risk: int
    fields: dict
    function: object

class Registry:
    def __init__(self): self.tools = {}

    def register(self, tool):
        if tool.name in self.tools: raise ValueError('Duplicate tool')
        self.tools[tool.name] = tool

    def execute(self, name, args):
        if name not in self.tools: raise ValueError('Unknown tool')
        tool = self.tools[name]
        if not isinstance(args,dict) or set(args) != set(tool.fields): raise ValueError('Invalid tool arguments')
        if any(not isinstance(args[k],t) for k,t in tool.fields.items()): raise ValueError('Invalid tool argument type')
        # No model-supplied approved=true escape hatch. Later writes need a server-side
        # approval ledger binding a single-use token to user, exact arguments and expiry.
        if tool.risk > 0: raise PermissionError('Side-effect tools are disabled in this foundation')
        return {'ok':True, 'tool':name, 'result':tool.function(**args)}
