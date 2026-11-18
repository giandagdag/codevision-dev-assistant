"""Helper process that turns text into vectors with CodeVision's own embedder (fix 11-3, D-A).

It runs under CodeVision's Python, so it uses only the standard library plus what CodeVision's
`agents.a_vector` imports. It never imports anything from the Developer Assistant: the DA has its
own `agents` and `configs` packages, and a same-named object in our library would win.
AS400 picture: like SBMJOB into CodeVision's library list instead of adding its library to ours.

Talk: one JSON line in {"text": "..."}, one JSON line out {"vector": [...]} / {"vector": null}.
The first line out is {"ready": true} or {"error": "plain words"}. It never prints or logs the text.
Start it with `python -I da_embed_worker.py <CodeVision src folder>` (-I keeps our own src folder
off the search path; this file then puts CodeVision's folder first).
"""

import json
import os
import sys


def main() -> int:
    protocol = sys.stdout
    sys.stdout = sys.stderr  # CodeVision code may print; only protocol lines go to the real stdout

    def say(message: dict) -> None:
        protocol.write(json.dumps(message) + "\n")
        protocol.flush()

    folder = sys.argv[1] if len(sys.argv) > 1 else ""
    if not folder or not os.path.isdir(folder):
        say({"error": "CodeVision's code folder was not found. Set DA_CODEVISION_SRC."})
        return 1
    sys.path.insert(0, folder)
    os.chdir(folder)
    try:
        from agents.a_vector import create_embeddings
    except ImportError as error:  # the message names a module, never text or a key
        say({"error": f"CodeVision's embedder could not start: {error}. "
                      "Set DA_CODEVISION_PYTHON to the Python that runs CodeVision."})
        return 1
    except Exception as error:  # noqa: BLE001 - name the kind only; the message may hold a header
        say({"error": f"CodeVision's embedder could not start ({type(error).__name__})."})
        return 1
    say({"ready": True})
    for line in sys.stdin:
        try:
            result = create_embeddings(json.loads(line)["text"])
            vector = None if result is None else [float(value) for value in result[0]]
        except Exception:  # noqa: BLE001 - one failed text is "no vector", never its details
            vector = None
        say({"vector": vector})
    return 0


if __name__ == "__main__":
    sys.exit(main())
