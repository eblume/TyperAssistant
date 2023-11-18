import json
from textwrap import shorten
from io import StringIO
from contextlib import redirect_stdout
import time
from dataclasses import dataclass, KW_ONLY, field
from typing import Optional, Any
from collections.abc import Iterable

from openai import OpenAI
from openai.types.beta.assistant import Assistant as RemoteAssistant
from openai.types.beta.thread import Thread
from openai.types.beta.threads.thread_message import ThreadMessage
from rich import print
from rich.panel import Panel

from .spec import FunctionSpec


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
    thread_id: Optional[str] = None
    assistant_id: Optional[str] = None

    def __post_init__(self):
        if self.name is None:
            self.name = self.__class__.__name__

        if self.replace or self.assistant_id is None:
            # TODO rethink this, delay making the assistant until we need it.
            self.assistant_id = self.make_assistant().id

    def ask(self, query: str, instructions: Optional[str] = None) -> str:
        """Ask the assistant a question, returning the response.

        This may block for the lifecycle of several API requests as well as waiting on remotely managed threads, in fact
        blocking for several minutes and then succeeding is not uncommon. The caller should make arrangements for
        multithreading, etc. should it be needed.
        """
        self.add_message(query)
        self.run_thread()
        messages = list(self.messages())
        # TODO figure out proper context processing with citations, etc.
        content = messages[0].content
        assert len(content) == 1
        assert content[0].type == "text"
        assert len(content[0].text.annotations) == 0
        return content[0].text.value

    def functions(self) -> Iterable[FunctionSpec]:
        """Returns an iterable of FunctionSpecs describing the function calling tools of this assistant."""
        # The base assistant just returns an empty list but almost any real use case will extend this.
        yield from []

    def do_function(self, name: str, func_args: dict[str, Any]) -> str:
        """Execute the given function with the given arguments."""

        # Helper func because of... well, you'll see the novel coming up in a few dozen lines.
        def _capture_result(command: FunctionSpec) -> str:
            # TODO Make all console output optional and remove to seperate methods
            # (Sorry if you're waiting on this)
            # print(f"Executing command {name} with args {func_args}")  # TODO logging
            with redirect_stdout(StringIO()) as buf:
                retval = command.action(**func_args)
            output = buf.getvalue().rstrip()
            if output:
                argtxt = str(func_args).strip("{}")
                command_title = shorten(f"{name}({argtxt})", 50)
                print(Panel(output, border_style="dim", title=command_title, title_align="left"))
                if retval is None:
                    return f"Output::\n{output}"
                else:
                    return f"Result::\n{retval}\n\nOutput::\n{output}output"
            # We string the result here just in case... I don't think it matters though.
            # TODO Think more about encapsulating command return values.
            return str(retval)

        for command in self.functions():
            if command.name == name:
                return _capture_result(command)

        # OK Let's take a break in the middle of this function and talk about a bug, and about why LLMs are tricky.
        #
        # There is a strange bug that seems to occur within the OpenAI function calling system, in which (I think) the
        # LLM interprets the command name differently if it looks like a file name. For instance, if the command name
        # is "example_1.py.get_current_user" Then the LLM will call this as just "get_current_user", I guess helpfully
        # stripping off what it perceives as an unexpected and unneeded file name.
        #
        # For now, two workarounds, neither perfect:
        # 1. Ask the LLM extra special nice to please not do that. (It works! Mostly! 🤯)
        # 2. If no func matches, search again with just the suffix.
        #
        # It's possible that #2 might introduce some nasty problems, and I think for now that's just part of the whole deal
        # with LLMs.
        #
        # TODO report this bug upstream? example_1.py is a small repro. Literally just remove the asking nice part and
        # then ask it to "greet me by name" and it will fail to find the function. (Remove this loop too.)
        #
        # I thought intercal was a joke. Back to our function, where we just failed to find our function.
        for command in self.functions():
            if command.name.endswith(name):
                return _capture_result(command)
        # (Ironically, Copilot wrote that loop first try, no sweat.)

        raise ValueError(f"Command {name} not found")

    def thread(self) -> Thread:
        """Retrieves the thread this assistant is using, or creates one if none exists."""
        # TODO proper support for multiple threads and resuming threads, etc.
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

    def run_thread(self):
        """Runs the current thread, blocking until it completes.

        See ask() for more details.
        """
        # TODO better docs
        # TODO handle multiple runs, run resuming, etc.? For now we just create a new run every time.
        run = self.client.beta.threads.runs.create(thread_id=self.thread().id, assistant_id=self.assistant_id)
        iterations = 0
        while iterations < MAX_RUN_ITERATIONS:
            iterations += 1
            time.sleep(RUN_ITERATION_SLEEP)  # Sleep right away, openai is never done immediately
            # print(f"Run status is {run.status}, iteration {iterations}")  # TODO logging

            # TODO figure out logging, this blocks for so long it will probably require some UI feedback
            match run.status:
                case "queued" | "in_progress":
                    run = self.client.beta.threads.runs.retrieve(thread_id=self.thread().id, run_id=run.id)
                    continue
                case "completed":
                    return
                case "requires_action":
                    iterations = 0  # Ball is in our court
                    calls = run.required_action.submit_tool_outputs.tool_calls
                    results = []
                    for call in calls:
                        if call.type == "function":  # for now always true
                            name = call.function.name
                            args = json.loads(call.function.arguments)
                            result = (
                                self.do_function(name, args) or "Success"
                            )  # TODO better result handling... catch exceptions?
                            results.append({"tool_call_id": call.id, "output": result})
                    # TODO: Consider NOT submitting reslts, and instead just pretty-print a command execution
                    # explaination and then execute it. Update the prompt to inform the assistant that it won't get a
                    # chance to respond to the command, or something.
                    if results:
                        # print(f"Submitting results {results}")  # TODO logging
                        run = self.client.beta.threads.runs.submit_tool_outputs(
                            thread_id=self.thread().id, run_id=run.id, tool_outputs=results
                        )
                case "cancelling" | "cancelled" | "failed" | "expired":
                    raise RuntimeError(f"Run failed with status {run.status}")
                case _:
                    raise RuntimeError(f"Unexpected status {run.status}")

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
