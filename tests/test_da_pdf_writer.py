"""Fix G5 F1: the standard-library PDF writer."""

import re

from src.agents.da_pdf_writer import MARGIN, PAGE_W, PdfReport, text_width, wrap

COLS = [("Test", 20), ("Result", 80)]


def test_valid_pdf_with_header_trailer_and_footer():
    pdf = PdfReport("CVDA-1 build 1 test report")
    pdf.heading("Report")
    pdf.table(COLS, [["T-1", "pass"], "full width failure message"])
    data = pdf.to_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert data.rstrip().endswith(b"%%EOF")
    assert b"trailer" in data and b"startxref" in data
    assert b"CVDA-1 build 1 test report - Page 1 of 1" in data
    assert b"(T-1)" in data


def test_xref_offsets_point_at_objects():
    data = PdfReport("f").to_bytes()
    start = int(re.search(rb"startxref\n(\d+)", data).group(1))
    assert data[start:start + 4] == b"xref"
    first = int(re.findall(rb"(\d{10}) 00000 n", data)[0])
    assert data[first:first + 7] == b"1 0 obj"


def test_wrap_fits_width_and_breaks_long_words():
    width = 100
    lines = wrap("word " * 30 + "x" * 200, "F1", 9, width)
    assert len(lines) > 3
    assert all(text_width(line, "F1", 9) <= width + 0.01 for line in lines)


def test_non_ascii_becomes_question_mark_and_parens_escaped():
    pdf = PdfReport("f")
    pdf.paragraph("café (ok)")
    data = pdf.to_bytes()
    assert b"(caf? \\(ok\\))" in data


def test_many_rows_make_pages_and_repeat_header():
    pdf = PdfReport("f")
    pdf.table(COLS, [[f"T-{i}", "ok"] for i in range(200)])
    data = pdf.to_bytes()
    pages = len(re.findall(rb"/Type /Page ", data))
    assert pages > 1
    assert data.count(b"(Test)") == pages  # header on every page
    assert f"Page {pages} of {pages}".encode() in data


def test_g5_21_column_positions_are_the_same_on_every_page():
    """Read the cell rectangles (`x y w h re S`) from the drawing commands of each page."""
    pdf = PdfReport("f")
    pdf.table(COLS, [[f"T-{i}", "a long result " * 5] for i in range(40)])
    pdf.to_bytes()
    assert len(pdf.pages) > 1
    seen = []
    for page in pdf.pages:
        cell = r"([\d.]+) [\d.]+ ([\d.]+) [\d.]+ re S"
        rects = {m for line in page for m in re.findall(cell, line)}
        assert rects
        seen.append(rects)
    assert all(columns == seen[0] for columns in seen)  # the same two columns on every page
    assert len(seen[0]) == 2


def test_g5_22_a_500_character_word_wraps_inside_its_cell():
    pdf = PdfReport("f")
    pdf.table(COLS, [["T-1", "x" * 500]])
    cell = (PAGE_W - 2 * MARGIN) * 80 / 100
    lines = [re.search(r"\((x+)\) Tj", line) for line in pdf.pages[0]]
    runs = [m.group(1) for m in lines if m]
    assert len(runs) > 1 and sum(map(len, runs)) == 500
    assert all(text_width(r, "F1", 9) < cell for r in runs)


def test_row_taller_than_page_is_split_without_losing_text():
    pdf = PdfReport("f")
    pdf.table(COLS, [["T-1", " ".join(f"w{i}" for i in range(3000))]])
    data = pdf.to_bytes()
    assert b"w2999" in data and b"w0 " in data
    assert len(re.findall(rb"/Type /Page ", data)) > 1


def test_full_width_row_uses_whole_table_width():
    assert PAGE_W - 2 * MARGIN > 700
