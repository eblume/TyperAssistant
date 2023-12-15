"""Usage: python example_3.py deuteronomy "Pick a cat and send them to the Heaviside Layer"
"""
import typer
from typerassistant.typer import TyperAssistant

app = typer.Typer(name="typerassistant_example_3")
# Instead of using register_assistant, we can manually generate assistants as-needed.
# Remote assistant definition is delayed until the assistant is actually used.
assistant = TyperAssistant(app, instructions="The assistant is Old Deuteronomy, the sage of the Jellicle Cats.")

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
    """Introduce a new cat to the Jellicle tribe."""
    global jellicles, assistant
    cat = (
        assistant.ask(
            "An original name for a cat in the style of T.S. Eliot",
            instructions="Respond only with a name for a cat with no other text.",
            use_commands=False,
        )
        .splitlines()[0]
        .strip()
    )
    assert cat
    jellicles.append(cat)
    print(f"Welcome, {cat}, to the Jellicle tribe!")


app.add_typer(cats, name="cats")


# We can prevent recursive assistant generation by setting omit_from_assistant on the context object.
@app.command("deuteronomy", context_settings={"obj": {"omit_from_assistant": True}})
def ask_old_deuteronomy(query: str):
    print(assistant.ask(query, confirm_commands=False))


if __name__ == "__main__":
    app()
