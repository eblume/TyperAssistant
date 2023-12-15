"""Usage: python example_2.py
(Then provide input to the prompt, then press enter.)
"""
from typing import Optional

from typerassistant import Assistant


class SomeDatabase:
    # This is a stand-in for whatever sort of session management you might have in your application.
    def get_or_create_some_thread(self, assistant: Assistant, thread_id: Optional[str] = None):
        return assistant.thread(thread_id=thread_id)


user_prompt = "APPROACH, MORTAL, AND BEG SUPERBOT'S ASSISTANCE"
instructions = f"""\
SUPERBOT, YOU ARE COMMANDED TO BE SUPER!
MAKE SURE THE USER KNOWS IT!
(They were greated with '{user_prompt}')
"""

assistant = Assistant(name="SuperBot", instructions=instructions)

# You can also just omit thread, if your use case doesn't require it.
thread = SomeDatabase().get_or_create_some_thread(assistant)

print(assistant.ask(input(f"{user_prompt}: "), thread=thread))
