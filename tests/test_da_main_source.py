"""Phase 9, step 3: main source and the freshness rules (9-12, 9-13, 9-16 pure part)."""

from agents.da_main_source import (
    BitbucketMainSource,
    FakeMainSource,
    check_freshness,
    get_main_source,
    next_step,
    stale_message,
)

PATH = "src/agents/limits_expiry_report.py"
TEXT = "def a():\n    return 1\n"


def main_folder(tmp_path, text=TEXT):
    target = tmp_path / PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(text.encode("utf-8"))
    return FakeMainSource(tmp_path)


def test_9_12_line_endings_and_a_bom_do_not_count(tmp_path):
    source = main_folder(tmp_path)
    his = "﻿" + TEXT.replace("\n", "\r\n")

    result = check_freshness({PATH: his}, source)

    assert result.all_equal
    assert next_step(result) == "e_fresh"
    assert result.main_source == "fake"
    assert "Freshness check passed" in stale_message(result)


def test_9_13_a_different_file_is_stale_and_the_banner_names_both_ways_to_update(tmp_path):
    source = main_folder(tmp_path)

    result = check_freshness({PATH: TEXT + "# my change\n"}, source)

    assert result.paths[0].state == "differs"
    assert next_step(result) == "e_stale"
    message = stale_message(result)
    assert PATH in message
    assert "git pull" in message
    assert "ZIP" in message
    assert "intentional" in message


def test_9_14_after_the_folder_is_updated_a_second_check_passes(tmp_path):
    source = main_folder(tmp_path)

    first = check_freshness({PATH: "old"}, source)
    second = check_freshness({PATH: TEXT}, source)

    assert next_step(first) == "e_stale"
    assert next_step(second) == "e_fresh"


def test_a_file_that_main_does_not_have_is_named(tmp_path):
    source = FakeMainSource(tmp_path)

    result = check_freshness({PATH: TEXT}, source)

    assert result.paths[0].state == "not_on_main"
    assert next_step(result) == "e_stale"
    assert f"`{PATH}` is not on Bitbucket main yet." in stale_message(result)


def test_9_16_a_file_missing_in_his_folder_is_stale(tmp_path):
    source = main_folder(tmp_path)

    result = check_freshness({PATH: None}, source)

    assert result.paths[0].state == "missing_in_folder"
    assert next_step(result) == "e_stale"
    assert "Your folder does not have" in stale_message(result)


def test_9_16_the_bitbucket_placeholder_is_never_a_silent_pass(make_settings):
    source = get_main_source(make_settings(main_source="bitbucket"))

    result = check_freshness({PATH: TEXT}, source)

    assert isinstance(source, BitbucketMainSource)
    assert result.paths[0].state == "unreachable"
    assert not result.all_equal
    assert next_step(result) == "e_stale"
    assert "I could not reach Bitbucket main" in stale_message(result)


def test_the_fake_source_cannot_read_outside_its_folder(tmp_path):
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    inner = tmp_path / "main"
    inner.mkdir()

    assert FakeMainSource(inner).get_text("../outside.txt") is None


def test_an_empty_list_of_files_is_not_a_pass(tmp_path):
    assert check_freshness({}, FakeMainSource(tmp_path)).all_equal is False


def test_the_shipped_made_up_files_match(make_settings):
    settings = make_settings()
    source = get_main_source(settings)
    shipped = (settings.fake_main_dir.parent / "da_fake_codevision" / PATH).read_text(
        encoding="utf-8"
    )

    assert check_freshness({PATH: shipped}, source).all_equal
