"""Usage: python example_1.py ask "Please greet me by name"
"""
import getpass

import typer
from typerassistant import register_assistant

app = typer.Typer(name="typerassistant_example_1")
register_assistant(app)


@app.command()
def say_hello(name: str):
    print(f"Hello, {name}!")


@app.command()
def get_current_user():
    print(getpass.getuser())


if __name__ == "__main__":
    app()
