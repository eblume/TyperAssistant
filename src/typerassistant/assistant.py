import json
import time
from collections.abc import Iterable
from contextlib import redirect_stdout
from dataclasses import KW_ONLY, dataclass, field
from io import StringIO
from textwrap import shorten
from typing import Optional, Type, TypeVar

from openai import OpenAI
from openai.types.beta.assistant import Assistant as RemoteAssistant
from openai.types.beta.thread import Thread
from openai.types.beta.threads import RequiredActionFunctionToolCall
from openai.types.beta.threads.run_submit_tool_outputs_params import ToolOutput
from openai.types.beta.threads.thread_message import ThreadMessage
from rich import print
from rich.panel import Panel
from rich.prompt import Confirm

from .spec import FunctionCall, FunctionSpec

# The number of times to poll for a run to complete before giving up
MAX_RUN_ITERATIONS = 20


# The number of seconds to sleep between run iterations
RUN_ITERATION_SLEEP = 3


# The best usage guide for function calling seems to be:
#   https://cookbook.openai.com/examples/how_to_call_functions_with_chat_models

AssistantT = TypeVar("AssistantT", bound="Assistant")


@dataclass
class Assistant:
    """An assistant managed remotely via OpenAI's assistant API.

    This class implements the basic lifecycle of an assistant, from CRUD to running a thread. It is intended to be
    subclassed to extend functionality.
    """

    name: str
    _: KW_ONLY
    instructions: str = "The agent is a helpful assistant. Its behavior and capabilities can be extended via the 'typerassistant' python package's API."
    client: OpenAI = field(default_factory=OpenAI)
    replace: bool = False
    _assistant: Optional[RemoteAssistant] = field(init=False, default=None)

    @classmethod
    def from_id(cls: Type[AssistantT], assistant_id: str, client: Optional[OpenAI] = None) -> AssistantT:
        """Retrieve the assistant with the given ID from OpenAI.

        This method will skip all assistant creation steps and simply use the remote definition."""
        if client is None:
            client = OpenAI()
        assistant = client.beta.assistants.retrieve(assistant_id)
        assert assistant.name
        new = cls(client=client, name=assistant.name, instructions=assistant.instructions or cls.instructions)
        new._assistant = assistant
        return new

    @property
    def assistant(self) -> RemoteAssistant:
        if self._assistant is None:
            self._assistant = self.make_assistant(self.replace)
        return self._assistant

    def ask(
        self,
        query: str,
        thread: Optional[Thread] = None,
        use_commands: bool = True,
        confirm_commands: bool = True,
        instructions: Optional[str] = None,
    ) -> str:
        """Ask the assistant a question, returning the response.

        This may block for the lifecycle of several API requests as well as waiting on remotely managed threads, in fact
        blocking for several minutes and then succeeding is not uncommon. The caller should make arrangements for
        multithreading, etc. should it be needed.

        If a thread is not provided, a new one will be made.
        """
        if thread is None:
            thread = self.thread()
        self.add_message(query, thread)
        self.run_thread(thread, use_commands=use_commands, confirm_commands=confirm_commands, instructions=instructions)
        messages = list(self.messages(thread))
        content = messages[0].content
        assert len(content) == 1
        assert content[0].type == "text"
        assert len(content[0].text.annotations) == 0
        return content[0].text.value

    def functions(self) -> Iterable[FunctionSpec]:
        """Returns an iterable of FunctionSpecs describing the function calling tools of this assistant."""
        # The base assistant just returns an empty list but almost any real use case will extend this
        yield from []

    def thread(self, thread_id: Optional[str] = None) -> Thread:
        """Retrieves the thread, or creates one if none exists."""
        if thread_id is None:
            return self.client.beta.threads.create()
        return self.client.beta.threads.retrieve(thread_id)

    def add_message(self, content: str, thread: Thread) -> ThreadMessage:
        """Adds a message to the current thread, returning the message."""
        return self.client.beta.threads.messages.create(thread_id=thread.id, role="user", content=content)

    def messages(self, thread: Thread) -> list[ThreadMessage]:
        return list(self.client.beta.threads.messages.list(thread_id=thread.id))

    def run_thread(
        self, thread: Thread, use_commands: bool, confirm_commands: bool, instructions: Optional[str] = None
    ):
        """Runs the current thread, blocking until it completes.

        See ask() for more details.
        """
        kwargs = {}
        if not use_commands:
            kwargs["tools"] = []
        if instructions is not None:
            kwargs["instructions"] = instructions

        run = self.client.beta.threads.runs.create(thread_id=thread.id, assistant_id=self.assistant.id, **kwargs)

        iterations = 0
        while iterations < MAX_RUN_ITERATIONS:
            iterations += 1
            time.sleep(RUN_ITERATION_SLEEP)  # Sleep right away, openai is never done immediately

            match run.status:
                case "queued" | "in_progress":
                    run = self.client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                    continue
                case "completed":
                    return
                case "requires_action":
                    if not use_commands:
                        raise RuntimeError("Run requires action but commands are disabled")
                    iterations = 0
                    assert run.required_action is not None
                    calls = run.required_action.submit_tool_outputs.tool_calls
                    results = self.tool_calls(calls, confirm_commands)
                    run = self.client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread.id,
                        run_id=run.id,
                        tool_outputs=results,
                    )
                case "cancelling" | "cancelled" | "failed" | "expired":
                    raise RuntimeError(f"Run failed with status {run.status}")
                case _:
                    raise RuntimeError(f"Unexpected status {run.status}")

    def tool_calls(self, calls: list[RequiredActionFunctionToolCall], confirm_commands: bool) -> list[ToolOutput]:
        """Translate a ToolCall API response in to  a list of FunctionCalls and do them."""
        function_specs = {func.name: func for func in self.functions()}

        # Build function call list
        # Here we use "function" to distinguish the openai call description from our
        # internal function call description.
        function_calls: list[FunctionCall] = []
        for call in calls:
            match call.type:
                case "function":
                    name = call.function.name
                    args = json.loads(call.function.arguments)
                case _:
                    raise ValueError(f"Unexpected call type {call.type}")

            if name not in function_specs:
                # Long story short, sometimes the LLM thinks typer arg0 is a file and thus insists on pulling it out of
                # the function name. This is a workaround kludge, and could cause problems.
                for func in function_specs.values():
                    if func.name.endswith(name):
                        function = func
                        break
                else:
                    raise ValueError(f"Unknown function {name}")
            else:
                function = function_specs[name]
            function_calls.append(FunctionCall(call_id=call.id, function=function, parameters=args))

        if confirm_commands:
            for i, call in enumerate(function_calls, 1):
                argtxt = str(call.parameters).strip("{}")
                command_title = shorten(f"{call.function.name}({argtxt})", 50)
                print(Panel(command_title, border_style="dim", title=f"Command {i}", title_align="left"))
            if not Confirm.ask("Allow the assistant to run these commands?"):
                raise RuntimeError("Aborted by user")

        results = []
        for call in function_calls:
            with redirect_stdout(StringIO()) as buf:
                call.function.action(**call.parameters)
            output = buf.getvalue().rstrip()
            result = ToolOutput(tool_call_id=call.call_id, output=output)
            results.append(result)

            argtxt = str(call.parameters).strip("{}")
            command_title = shorten(f"{call.function.name}({argtxt})", 50)
            print(Panel(output, border_style="dim", title=command_title, title_align="left"))

        return results

    def make_assistant(self, replace: bool) -> RemoteAssistant:
        """Get or create an assistant in the OpenAI API reflecting the current state of this object.

        If an assistant with the given name already exists, it will be returned. Otherwise, a new assistant will be
        created. (In the future, an update or drift-detection system may be implemented.)

        If replace is True, any existing assistant with the same name will be deleted first.

        If you want to load a remote assistant directly by ID without potentially creating a new one, use from_id()
        instead.
        """
        # We would prefer to query for assistants of the given name, but the API doesn't support that.
        # So for now we just scan them all.
        assistants = list(self.client.beta.assistants.list())
        for assistant in assistants:
            if assistant.name == self.name:
                if replace:
                    self.client.beta.assistants.delete(assistant.id)
                else:
                    return assistant
        return self.client.beta.assistants.create(
            name=self.name,
            instructions=self.instructions,
            tools=[tool.tool() for tool in self.functions()],
            model="gpt-4-1106-preview",
        )

    def delete_assistant(self):
        """Delete the assistant from OpenAI."""
        self.client.beta.assistants.delete(self.assistant.id)
