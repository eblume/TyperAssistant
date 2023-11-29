import json
import time
from collections.abc import Iterable
from contextlib import redirect_stdout
from dataclasses import KW_ONLY, dataclass, field
from io import StringIO
from textwrap import shorten
from typing import Any, Optional

from openai import OpenAI
from openai.types.beta.assistant import Assistant as RemoteAssistant
from openai.types.beta.thread import Thread
from openai.types.beta.threads.thread_message import ThreadMessage
from rich import print
from rich.panel import Panel
from rich.prompt import Confirm

from .spec import FunctionCall, FunctionResult, FunctionSpec

# The number of times to poll for a run to complete before giving up
MAX_RUN_ITERATIONS = 20


# The number of seconds to sleep between run iterations
RUN_ITERATION_SLEEP = 3


# The best usage guide for function calling seems to be:
#   https://cookbook.openai.com/examples/how_to_call_functions_with_chat_models


@dataclass
class Assistant:
    """An assistant managed remotely via OpenAI's assistant API.

    This class implements the basic lifecycle of an assistant, from CRUD to running a thread. It is intended to be
    subclassed to extend functionality.
    """

    _: KW_ONLY
    client: OpenAI = field(default_factory=OpenAI)
    name: Optional[str] = None
    instructions: str = "Assist the user with their query. Be concise."
    replace: bool = False
    prompt: bool = True
    thread_id: Optional[str] = None
    assistant_id: Optional[str] = None

    def __post_init__(self):
        if self.name is None:
            self.name = self.__class__.__name__

        if self.replace or self.assistant_id is None:
            # TODO rethink this, delay making the assistant until we need it.
            self.assistant_id = self.make_assistant().id

    def ask(self, query: str, instructions: Optional[str] = None, thread_id: Optional[str] = None) -> str:
        """Ask the assistant a question, returning the response.

        This may block for the lifecycle of several API requests as well as waiting on remotely managed threads, in fact
        blocking for several minutes and then succeeding is not uncommon. The caller should make arrangements for
        multithreading, etc. should it be needed.

        If supplied, thread_id overrides the thread_id of this assistant.
        """
        self.add_message(query)
        self.run_thread(thread_id or self.thread_id)
        messages = list(self.messages())
        # TODO figure out proper context processing with citations, etc.
        content = messages[0].content
        assert len(content) == 1
        assert content[0].type == "text"
        assert len(content[0].text.annotations) == 0
        return content[0].text.value

    def functions(self) -> Iterable[FunctionSpec]:
        """Returns an iterable of FunctionSpecs describing the function calling tools of this assistant."""
        # The base assistant just returns an empty list but almost any real use case will extend this
        yield from []

    def thread(self) -> Thread:
        """Retrieves the thread this assistant is using, or creates one if none exists."""
        if self.thread_id is None:
            self.thread_id = self.client.beta.threads.create().id
        return self.client.beta.threads.retrieve(self.thread_id)

    def add_message(self, content: str, role: str = "user") -> ThreadMessage:
        """Adds a message to the current thread, returning the message."""
        return self.client.beta.threads.messages.create(
            thread_id=self.thread().id,
            role=role,
            content=content,
        )

    def messages(self) -> list[ThreadMessage]:
        # TODO it's not clear if this function is actually useful, and it could be setting us up for a problem if we
        # want to rely on the underlying library's pagination support to e.g. NOT retrieve all messages.
        # OTOH it encapsulates concerns well for subclassers.
        return list(self.client.beta.threads.messages.list(thread_id=self.thread().id))

    def run_thread(self, thread_id: Optional[str] = None):
        """Runs the current thread, blocking until it completes.

        See ask() for more details.
        """
        if thread_id is None:
            thread = self.thread()
        else:
            thread = self.client.beta.threads.retrieve(thread_id)
        # TODO check validity and status of thread
        # For now we will just let the API throw if it's not valid.
        run = self.client.beta.threads.runs.create(thread_id=thread.id, assistant_id=self.assistant_id)
        iterations = 0
        while iterations < MAX_RUN_ITERATIONS:
            iterations += 1
            time.sleep(RUN_ITERATION_SLEEP)  # Sleep right away, openai is never done immediately
            # print(f"Run status is {run.status}, iteration {iterations}")  # TODO logging
            match run.status:
                case "queued" | "in_progress":
                    run = self.client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                    continue
                case "completed":
                    return
                case "requires_action":
                    iterations = 0
                    # TODO reconsider iterations, in context of prompt
                    calls = run.required_action.submit_tool_outputs.tool_calls
                    results = self.tool_calls(thread.id, run.id, calls)
                    outputs = [
                        {
                            "tool_call_id": result.call.call_id,
                            "output": json.dumps(result.dict()),
                        }
                        for result in results
                    ]
                    run = self.client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread.id,
                        run_id=run.id,
                        tool_outputs=outputs,
                    )
                case "cancelling" | "cancelled" | "failed" | "expired":
                    raise RuntimeError(f"Run failed with status {run.status}")
                case _:
                    raise RuntimeError(f"Unexpected status {run.status}")

    def tool_calls(self, thread_id: str, run_id: str, calls: list[dict[str, Any]]) -> list[FunctionResult]:
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

        if self.prompt:
            # TODO customize prompt
            for i, call in enumerate(function_calls, 1):
                argtxt = str(call.parameters).strip("{}")
                command_title = shorten(f"{call.function.name}({argtxt})", 50)
                print(Panel(command_title, border_style="dim", title=f"Command {i}", title_align="left"))
            if not Confirm.ask("Allow the assistant to run these commands?"):
                # TODO proper abort flow
                raise RuntimeError("Aborted by user")

        results = []
        for call in function_calls:
            with redirect_stdout(StringIO()) as buf:
                retval = call.function.action(**call.parameters)
            output = buf.getvalue().rstrip()
            result = FunctionResult(call=call, return_value=retval, stdout=output)
            results.append(result)

            # TODO customize stdout
            argtxt = str(call.parameters).strip("{}")
            command_title = shorten(f"{call.function.name}({argtxt})", 50)
            print(Panel(result.stdout, border_style="dim", title=command_title, title_align="left"))

        return results

    def make_assistant(self) -> RemoteAssistant:
        # We would prefer to query for assistants of the given name, but the API doesn't support that.
        assistants = list(self.client.beta.assistants.list())
        for assistant in assistants:
            if assistant.name == self.name:
                if self.replace:
                    self.client.beta.assistants.delete(assistant.id)
                else:
                    return assistant
        return self.client.beta.assistants.create(
            name=self.name,
            instructions=self.instructions,
            tools=[tool.dict() for tool in self.functions()],
            model="gpt-4-1106-preview",
        )

    def delete_assistant(self):
        """Delete the assistant from OpenAI."""
        self.client.beta.assistants.delete(self.assistant_id)
