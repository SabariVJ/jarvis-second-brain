"""Typed allowlist for Jarvis actions; model/source text has no tool authority."""
from jarvis.security import redact


_RISK={0:'L0_READ',1:'L1_REVERSIBLE',2:'L2_PERSONAL_WRITE',3:'L3_EXTERNAL_WRITE',4:'L4_DESTRUCTIVE'}


class ToolError(ValueError):
    def __init__(self, code, message, tool=None):
        super().__init__(message)
        self.result={'ok':False,'tool':tool,'result':None,'error':{'code':code,'message':message},'verification':'NOT_RUN'}


class ToolPermissionError(PermissionError):
    def __init__(self, name, permission_class):
        super().__init__(f'{name} requires {permission_class} authorization')
        self.result={'ok':False,'tool':name,'result':None,'error':{'code':'PERMISSION_REQUIRED','message':str(self)},'verification':'NOT_RUN'}


class Tool:
    """Tool definition. Legacy (risk, fields, function) construction remains supported."""
    def __init__(self,name,risk=0,fields=None,function=None,*,description='',arguments=None,
                 permission_class=None,verifier=None,available=True):
        self.name=name;self.description=description or name.replace('_',' ')
        self.permission_class=permission_class or _RISK.get(risk,'L4_DESTRUCTIVE')
        self.risk=next((level for level,label in _RISK.items() if label==self.permission_class),4)
        self.arguments=arguments if arguments is not None else {
            key:{**_python_type(value),'required':True} for key,value in (fields or {}).items()}
        self.fields={key:_schema_python_type(value.get('type')) for key,value in self.arguments.items()}
        self.function=function;self.verifier=verifier;self.available=bool(available)


def _python_type(value):
    if value is str:return {'type':'string'}
    if value is int:return {'type':'integer'}
    if value is float:return {'type':'number'}
    if value is bool:return {'type':'boolean'}
    if value is dict:return {'type':'object'}
    if value is list:return {'type':'array'}
    return {'type':'any'}


def _schema_python_type(value):
    return {'string':str,'integer':int,'number':float,'boolean':bool,'object':dict,'array':list}.get(value,object)


class Registry:
    def __init__(self,authorizer=None):
        self.tools={};self.authorizer=authorizer;self.preflight=None

    def register(self,tool):
        if not isinstance(tool,Tool) or not tool.name or not callable(tool.function):raise ValueError('Tool definition is invalid')
        if tool.name in self.tools:raise ValueError('Duplicate tool')
        if tool.permission_class not in _RISK.values():raise ValueError('Tool permission class is invalid')
        if not isinstance(tool.arguments,dict):raise ValueError('Tool arguments schema must be an object')
        self.tools[tool.name]=tool

    @staticmethod
    def _validate_value(value,schema,path,depth=0):
        if depth>8:raise ToolError('ARGUMENTS_TOO_DEEP',f'{path} is nested too deeply')
        kind=schema.get('type','any')
        valid={'string':lambda: isinstance(value,str),'integer':lambda: isinstance(value,int) and not isinstance(value,bool),
            'number':lambda: isinstance(value,(int,float)) and not isinstance(value,bool),
            'boolean':lambda: isinstance(value,bool),'object':lambda: isinstance(value,dict),'array':lambda: isinstance(value,list),
            'any':lambda: value is None or isinstance(value,(str,int,float,bool,dict,list))}
        if kind not in valid or not valid[kind]():raise ToolError('INVALID_ARGUMENT',f'{path} must be {kind}')
        if kind=='string':
            if len(value)>schema.get('maxLength',4000) or len(value)<schema.get('minLength',0):raise ToolError('INVALID_ARGUMENT',f'{path} has an invalid length')
            if 'enum' in schema and value not in schema['enum']:raise ToolError('INVALID_ARGUMENT',f'{path} has an unsupported value')
        if kind in ('integer','number'):
            if isinstance(value,float) and (value!=value or abs(value)==float('inf')):raise ToolError('INVALID_ARGUMENT',f'{path} must be finite')
            if value<schema.get('minimum',float('-inf')) or value>schema.get('maximum',float('inf')):raise ToolError('INVALID_ARGUMENT',f'{path} is outside its supported range')
        if kind=='array':
            if len(value)>schema.get('maxItems',100):raise ToolError('INVALID_ARGUMENT',f'{path} has too many items')
            item_schema=schema.get('items',{'type':'any'})
            for i,item in enumerate(value):Registry._validate_value(item,item_schema,f'{path}[{i}]',depth+1)
        if kind=='object':
            props=schema.get('properties',{});required=schema.get('required',[])
            if any(key not in props for key in value) or any(key not in value for key in required):raise ToolError('INVALID_ARGUMENT',f'{path} has missing or unsupported fields')
            for key,item in value.items():Registry._validate_value(item,props[key],f'{path}.{key}',depth+1)

    def definition(self,name):
        tool=self.tools.get(name)
        if not tool:return None
        return {'name':tool.name,'description':tool.description,'arguments':tool.arguments,
            'permission_class':tool.permission_class,'available':tool.available}

    def definitions(self):
        return [self.definition(name) for name in sorted(self.tools)]

    def validate(self,name,args):
        tool=self.tools.get(name)
        if not tool:raise ToolError('UNKNOWN_TOOL','Tool is not registered',name)
        if not isinstance(args,dict):raise ToolError('INVALID_ARGUMENTS','Tool arguments must be an object',name)
        schema=tool.arguments;required={key for key,value in schema.items() if value.get('required',True)}
        if set(args)-set(schema) or required-set(args):raise ToolError('INVALID_ARGUMENTS','Tool arguments do not match the registered schema',name)
        try:
            for key,value in args.items():self._validate_value(value,schema[key],key)
        except ToolError as error:
            error.result['tool']=name;raise
        if self.preflight and tool.available:self.preflight(name,args)
        return tool,args

    def execute(self,name,args,*,authorization=None):
        tool,args=self.validate(name,args)
        if not tool.available:raise ToolError('TOOL_UNAVAILABLE','This tool is not available in the current runtime',name)
        authorized=tool.permission_class=='L0_READ'
        if not authorized and self.authorizer:
            decision=self.authorizer(tool,args,authorization)
            authorized=bool(decision.get('allowed')) if isinstance(decision,dict) else bool(decision)
        if not authorized:raise ToolPermissionError(name,tool.permission_class)
        try:
            result=tool.function(**args)
        except ToolError as error:
            error.result['tool']=name;raise
        except Exception as error:
            message=redact(str(error))[:300] or 'Tool execution failed'
            raise ToolError('EXECUTION_FAILED',message,name) from None
        verification='NOT_CHECKED'
        if tool.verifier:
            try:verification='VERIFIED' if tool.verifier(result,args) else 'UNVERIFIED'
            except Exception:verification='UNVERIFIED'
        return {'ok':True,'tool':name,'result':result,'error':None,'verification':verification}
