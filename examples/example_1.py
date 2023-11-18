"""Usage: python example_1.py ask "Please greet me by name"
"""
import getpass
import typer
from typerassistant import TyperAssistant
from openai import OpenAI

app = typer.Typer()
client = OpenAI()  # Assuming OPENAI_API_KEY is set in the environment


@app.command()
def say_hello(name: str):
    print(f"Hello, {name}!")


@app.command()
def get_current_user():
    print(getpass.getuser())


TyperAssistant(app, client=client, replace=True)
app()
