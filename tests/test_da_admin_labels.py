from agents.da_admin_labels import LABELS, label, raw_names_in
from styles import da_admin_styles, da_styles


def test_spec_examples_have_plain_labels():
    assert label("DA_SEARCH_TOP_K") == "Search results per query"
    assert label("max_material_decisions") == "Decision limit"
    assert label("build_max_rounds") == "Max fix rounds"


def test_unknown_name_loses_its_underscores():
    assert label("some_new_field") == "Some new field"


def test_scan_finds_raw_names_but_not_chip_texts():
    text = "Set DA_SEARCH_TOP_K and build_max_rounds, see agents/da_code_index.py"
    found = raw_names_in(text, allowed=frozenset({"da_code_index"}))
    assert found == ["DA_SEARCH_TOP_K", "build_max_rounds"]


def test_every_label_is_free_of_raw_names():
    assert all(not raw_names_in(text) for text in LABELS.values())


def test_admin_palette_matches_the_shared_two_colours():
    assert da_admin_styles.NAVY == da_styles.NAVY == "#1E2B45"
    assert da_admin_styles.BLUE == da_styles.BLUE == "#1F6FE0"
    assert da_admin_styles.GREEN == "#157F3B"
