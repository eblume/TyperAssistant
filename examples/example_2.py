"""Usage: python example_2.py
(Then provide input to the prompt, then press enter.)
"""
from openai import OpenAI
from typerassistant.assistant import Assistant


class SomeDatabase:
    def get_or_create_some_thread(self):
        return OpenAI().beta.threads.create()


thread_id = SomeDatabase().get_or_create_some_thread().id

user_prompt = "APPROACH, MORTAL, AND BEG SUPERBOT'S ASSISTANCE"
instructions = (
    f"SUPERBOT, YOU ARE COMMANDED TO BE SUPER! (MAKE SURE THE USER KNOWS IT! (They were greated with '{user_prompt}'))"
)

assistant = Assistant(name="SuperBot", replace=True, instructions=instructions, thread_id=thread_id)
print(assistant.ask(input(f"{user_prompt}: ")))
