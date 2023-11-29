from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class ParameterSpec:
    name: str
    description: str
    required: bool
    default: Optional[str] = None
    enum: Optional[list[str]] = None


# Why not use openai.types.beta.threads.run_create_params.ToolAssistantToolsFunction?
# For one, it's not documented and it's really hard to use programmatically. For another, I want to use this to bind
# functionspec definitions to callable actions, for reversable function<->functionspec lookups.
# TODO find a better way to document this decision and explain it.
# TODO make this parametric to the return type, and thread it through to the result
@dataclass
class FunctionSpec:
    name: str
    description: str
    parameters: list[ParameterSpec]
    action: Callable[..., Any]

    def dict(self) -> dict:
        struct = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {  # This is now technically a JSONSchema object
                    "type": "object",
                    "properties": {
                        param.name: {
                            "type": "string",  # TODO other types?
                            "description": param.description,
                            "default": param.default or "None",
                        }
                        for param in self.parameters
                    },
                    "required": [param.name for param in self.parameters if param.required],
                },
            },
        }

        # enum processing - do this in a second pass to avoid empty enums
        for param in self.parameters:
            if param.enum:
                struct["function"]["parameters"]["properties"][param.name]["enum"] = list(param.enum)
        return struct


@dataclass
class FunctionCall:
    call_id: str
    function: FunctionSpec
    parameters: dict[str, Any]

    def dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "function": self.function.name,
            "parameters": self.parameters,
        }


@dataclass
class FunctionResult:
    call: FunctionCall
    return_value: Any  # See note above on parametric return types
    stdout: str

    def dict(self) -> dict:
        return {
            "call_id": self.call.call_id,
            "function": self.call.function.name,
            "return_value": self.return_value,
            "stdout": self.stdout,
        }
