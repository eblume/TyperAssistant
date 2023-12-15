import importlib.metadata

from .assistant import Assistant
from .typer import TyperAssistant, register_assistant

__version__ = importlib.metadata.version(__name__)
__all__ = ("TyperAssistant", "Assistant", "register_assistant")
