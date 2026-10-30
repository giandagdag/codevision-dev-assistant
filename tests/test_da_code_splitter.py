import json
from dataclasses import fields

from agents.da_code_splitter import SNIPPET_LIMIT, CodePiece, split_folder, split_python_file
from agents.da_search_index import FAKE_INDEX_FILE

SAMPLE = '''"""Module docs."""
import os

LIMIT = 5


def helper(x):
    return x + LIMIT


class Checker:
    kind = "demo"

    def check(self, value):
        return value > 0

    @staticmethod
    def build():
        return Checker()


async def fetch():
    return os.getcwd()
'''


def by_symbol(pieces):
    return {piece.symbol: piece for piece in pieces}


def test_one_piece_per_function_class_and_method_with_symbols():
    pieces = split_python_file("app/sample.py", SAMPLE)

    assert [p.symbol for p in pieces] == [
        "<module>", "helper", "Checker", "Checker.check", "Checker.build", "fetch",
    ]


def test_line_numbers_are_correct_and_decorators_are_included():
    found = by_symbol(split_python_file("app/sample.py", SAMPLE))

    assert (found["helper"].line_start, found["helper"].line_end) == (7, 8)
    assert (found["Checker"].line_start, found["Checker"].line_end) == (11, 19)
    assert (found["Checker.check"].line_start, found["Checker.check"].line_end) == (14, 15)
    # The decorator line (17) belongs to the method that follows it.
    assert (found["Checker.build"].line_start, found["Checker.build"].line_end) == (17, 19)
    assert found["Checker.build"].snippet.startswith("    @staticmethod")


def test_module_level_code_becomes_one_module_piece():
    module = by_symbol(split_python_file("app/sample.py", SAMPLE))["<module>"]

    assert "import os" in module.snippet and "LIMIT = 5" in module.snippet
    assert "def helper" not in module.snippet


def test_file_with_only_definitions_has_no_module_piece():
    pieces = split_python_file("a.py", "def a():\n    return 1\n")

    assert [p.symbol for p in pieces] == ["a"]


def test_empty_file_gives_no_pieces():
    assert split_python_file("a.py", "") == []
    assert split_python_file("a.py", "\n\n") == []


def test_snippet_is_cut_to_2000_characters():
    body = "\n".join(f"    x{i} = {i}" for i in range(400))
    piece = split_python_file("a.py", f"def big():\n{body}\n")[0]

    assert len(piece.snippet) == SNIPPET_LIMIT


def test_broken_file_gives_one_whole_file_piece_and_a_warning(caplog):
    pieces = split_python_file("bad.py", "def broken(:\n    pass\n")

    assert len(pieces) == 1
    assert (pieces[0].symbol, pieces[0].line_start) == ("", 1)
    assert "Could not parse" in caplog.text
    assert "bad.py" not in caplog.text


def test_split_folder_skips_venv_pycache_and_secret_paths_and_is_sorted(tmp_path):
    def write(name, text="def f():\n    return 1\n"):
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)

    write("b/two.py")
    write("a/one.py")
    write(".venv/lib/x.py")
    write("a/__pycache__/y.py")
    write("app/secrets_loader.py")
    write("app/server.key.py")
    write("notes.txt", "not python")

    pieces = split_folder(tmp_path)

    assert [p.path for p in pieces] == ["a/one.py", "app/server.key.py", "b/two.py"]
    assert pieces == split_folder(tmp_path)


def test_pretend_index_fields_match_the_splitter_fields():
    index_piece = json.loads(FAKE_INDEX_FILE.read_text())["pieces"][0]
    splitter_fields = {field.name for field in fields(CodePiece)}

    # path, symbol, line_start and snippet mean the same in both; the index adds its own labels.
    shared = {"symbol", "line_start", "snippet"}
    assert shared <= splitter_fields and shared <= set(index_piece)
    assert "path" in index_piece and "path" in splitter_fields
    assert {"piece_no", "kind", "language", "deprecated", "restricted", "tags"} <= set(index_piece)
