"""Made-up helper: turns every text note in a folder into one .md document. Not real UOB code."""

from pathlib import Path


def convert_folder(folder):
    """Creates one .md file next to each .txt note and returns the new file names."""
    made = []
    for note in Path(folder).glob("*.txt"):
        target = note.with_suffix(".md")
        target.write_text("# " + note.stem + "\n\n" + note.read_text(encoding="utf-8"))
        made.append(target.name)
    return made
