"""Usage: python example_3.py ask --no-prompt "Pick a cat and send them to the Heaviside Layer"
"""
import typer
from typerassistant.typer import TyperAssistant

app = typer.Typer(name="typerassistant_example_3")


@app.command()
def delete_assistant():
    if hasattr(app, "assistant"):  # You can substitute your own state mechanism, eg. globals
        app.assistant.client.beta.assistants.delete(app.assistant.assistant_id)


# Subgroups are supported (with some automatically handled name mangling)
cats = typer.Typer()

jellicles = [
    "Jennyanydots",
    "Rum Tum Tugger",
    "Growltiger",
    "Mungojerrie",
    "Rumpleteazer",
    "Old Deuteronomy",
    "Great Rumpus Cat",
    "Mr. Mistoffelees",
    "Macavity",
    "Gus",
    "Bustopher Jones",
    "Skimbleshanks",
    "Morgan",
]


@cats.command()
def list():
    global jellicles
    for cat in jellicles:
        print(cat)


@cats.command()
def ascend(cat: str):
    global jellicles
    try:
        jellicles.remove(cat)
    except ValueError:
        print(f"{cat} is not a Jellicle cat!")
    else:
        print(f"Up up up past the Russell Hotel with {cat}!")


@cats.command()
def introduce():
    global jellicles
    name = app.assistant.ask("An original name for a cat in the style of T.S. Eliot")
    jellicles.append(name)


app.add_typer(cats, name="cats")

if __name__ == "__main__":
    # The instatiation of TyperAssistant must come AFTER all other typer commands are registered, or else the assistant
    # will not learn about those commands! (This will be fixed in a later release.)
    assistant = TyperAssistant(app)
    app.assistant = assistant
    app()
