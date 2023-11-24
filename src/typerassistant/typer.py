import sys
from dataclasses import KW_ONLY, dataclass, field
from typing import Iterable, Optional

import typer
from typer.main import get_command_from_info

from .assistant import Assistant
from .spec import FunctionSpec, ParameterSpec


@dataclass
class TyperAssistant(Assistant):
    """An Assistant generated from a Typer app."""

    app: typer.Typer
    _: KW_ONLY
    command_name: str = "ask"
    instructions: str = "The agent is an interface to a python Typer CLI. The tools available correspond to typer commands. Please help the user with their queries, executing CLI functions as needed. Be concise, but don't shorten the function names even if they look like file paths."
    # About the above instruction, please see the extended note in `assistant.py::Assistant.do_func`.
    name: Optional[str] = field(init=False, default=None)

    def __post_init__(self):
        # In AppAssistant, we always infer the name
        self.name = self.app.info.name or sys.argv[0]
        # Register the ask command
        # TODO check name collision?
        self.app.command(self.command_name)(self.ask_command)
        super().__post_init__()

    def functions(self) -> Iterable[FunctionSpec]:
        """Generate FunctionSpecs from the Typer app."""
        yield from super().functions()  # currently a non-op but may be useful to others
        for func in typerfunc(self.app):
            # Reject the ask_command
            if func.name == f"{self.name}.{self.command_name}":
                continue
            yield func

    def ask_command(self, query: str):
        """Ask the assistant a question, with response printed to stdout."""
        typer.echo(self.ask(query))


def typerfunc(app: typer.Typer, command_prefix: str = None) -> list[FunctionSpec]:
    """Returns a list of FunctionSpecs describing the CLI of app.

    This function recurses on command groups, with a command_prefix appended to the beginning of each command name in
    that group.
    """
    if command_prefix is None:
        if isinstance(app.info.name, str):
            command_prefix = app.info.name
        else:
            command_prefix = sys.argv[0]

    functions: list[FunctionSpec] = []

    for command_info in app.registered_commands or []:
        command = get_command_from_info(
            command_info=command_info,
            pretty_exceptions_short=app.pretty_exceptions_short,
            rich_markup_mode=app.rich_markup_mode,
        )
        # I'm not sure where it happens, but it's documented here: https://typer.tiangolo.com/tutorial/commands/name/
        #     "Note that any underscores in the function name will be replaced with dashes."
        # Therefore, convert all dashes back to underscores. *shrug*
        fullname = f"{command_prefix}.{command.name.replace('-', '_')}"

        # Extract callback signature for parameters.
        params = []
        for param in command.params:
            descr = param.help or "No description available"

            param_spec = ParameterSpec(
                name=param.name,
                description=descr,
                default=param.default,
                required=param.required,
            )

            params.append(param_spec)

        spec = FunctionSpec(
            name=fullname,
            description=command.help,
            parameters=params,
            action=command_info.callback,  # command_info.callback is the user function, command.callback is the internal click wrapper.
        )
        functions.append(spec)

    # Iterate over registered groups, recursing on each
    for group in app.registered_groups:
        # As with the command name, convert all dashes to underscores.
        functions.extend(
            typerfunc(group.typer_instance, command_prefix=command_prefix + "." + group.name.replace("-", "_"))
        )

    return functions
