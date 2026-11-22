"""Tiny PDF writer (standard library only) for the test report (Fix G5, F1).

PDF 1.4, built-in fonts Helvetica and Helvetica-Bold, A4 landscape. Because the
font widths are a table here, text wrapping is exact and no font file is needed.
Think of it as a spool file printer: we lay out lines ourselves, then write them.
"""

PAGE_W, PAGE_H = 841.89, 595.28  # A4 landscape in points
MARGIN = 15 * 72 / 25.4  # 15 mm
FOOTER_H = 22  # room kept at the bottom for the footer line
BODY_PT, HEAD_PT = 9, 12
PAD = 2.5  # cell padding in points

# Character widths (1/1000 em) for ASCII 32..126, in order.
_REGULAR = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"
)
_BOLD = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"
)
WIDTHS = {
    "F1": [int(n) for n in _REGULAR.split()],
    "F2": [int(n) for n in _BOLD.split()],
}


def clean(text) -> str:
    """Keep printable ASCII. Anything else becomes '?' (WinAnsi extras are not mapped)."""
    text = str(text).replace("\t", " ")
    return "".join(c if c in "\n" or 32 <= ord(c) <= 126 else "?" for c in text)


def text_width(text: str, font: str, size: float) -> float:
    return sum(WIDTHS[font][ord(c) - 32] for c in text) * size / 1000


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Break text at word boundaries; a word wider than the line is cut by characters."""
    lines: list[str] = []
    for para in clean(text).split("\n"):
        current = ""
        for word in para.split(" "):
            while text_width(word, font, size) > width:  # long word: break it
                if current:
                    lines.append(current)
                    current = ""
                cut = 1
                while cut < len(word) and text_width(word[: cut + 1], font, size) <= width:
                    cut += 1
                lines.append(word[:cut])
                word = word[cut:]
            trial = f"{current} {word}" if current else word
            if current and text_width(trial, font, size) > width:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return lines


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class PdfReport:
    def __init__(self, footer: str):
        self.footer = clean(footer)
        self.pages: list[list[str]] = [[]]
        self.y = PAGE_H - MARGIN  # top of the free space on the current page

    # ---- low level -------------------------------------------------------
    def _bottom(self) -> float:
        return MARGIN + FOOTER_H

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN

    def _text(self, x, y, text, font="F1", size=BODY_PT) -> None:
        self.pages[-1].append(f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({_esc(text)}) Tj ET")

    # ---- public ----------------------------------------------------------
    def heading(self, text: str) -> None:
        lead = HEAD_PT * 1.3
        if self.y - lead - 6 < self._bottom():
            self._new_page()
        self.y -= 6
        for line in wrap(text, "F2", HEAD_PT, PAGE_W - 2 * MARGIN):
            self.y -= lead
            self._text(MARGIN, self.y + 3, line, "F2", HEAD_PT)

    def paragraph(self, text: str, bold: bool = False) -> None:
        font, lead = ("F2" if bold else "F1"), BODY_PT * 1.3
        for line in wrap(text, font, BODY_PT, PAGE_W - 2 * MARGIN):
            if self.y - lead < self._bottom():
                self._new_page()
            self.y -= lead
            self._text(MARGIN, self.y + 3, line, font)

    def table(self, columns: list[tuple[str, float]], rows: list) -> None:
        """columns: (title, percent). A row is a list of cell texts, or one string
        for a full-width row (for example a failure message under its test)."""
        total = PAGE_W - 2 * MARGIN
        widths = [total * pct / 100 for _, pct in columns]
        header = [t for t, _ in columns]
        self._row(header, widths, bold=True, shade=True)
        for row in rows:
            if isinstance(row, str):
                self._row([row], [total], span=True, header=(header, widths))
            else:
                self._row(list(row), widths, header=(header, widths))

    def _row(self, cells, widths, bold=False, shade=False, span=False, header=None) -> None:
        font, lead = ("F2" if bold else "F1"), BODY_PT * 1.25
        cols = [wrap(c, font, BODY_PT, w - 2 * PAD) for c, w in zip(cells, widths, strict=False)]
        page_lines = int((PAGE_H - 2 * MARGIN - FOOTER_H - 2 * PAD) // lead)
        need = max(len(c) for c in cols)
        fits = self.y - (need * lead + 2 * PAD) >= self._bottom()
        if not fits and need <= page_lines:
            self._new_page()  # a row is never split unless taller than a page
            if header:
                self._row(header[0], header[1], bold=True, shade=True)
        elif not fits:  # taller than a page: carry what fits, continue on a new page
            room = max(int((self.y - self._bottom() - 2 * PAD) // lead), 1)
            self._row_lines([c[:room] for c in cols], widths, font, lead, shade)
            self._new_page()
            if header:
                self._row(header[0], header[1], bold=True, shade=True)
            rest = [c[room:] for c in cols]
            if any(rest):
                self._row_lines_split(rest, widths, font, lead, shade, header)
            return
        self._row_lines(cols, widths, font, lead, shade)

    def _row_lines_split(self, cols, widths, font, lead, shade, header) -> None:
        """Place pre-wrapped lines, moving to new pages as often as needed."""
        while any(cols):
            room = max(int((self.y - self._bottom() - 2 * PAD) // lead), 1)
            self._row_lines([c[:room] for c in cols], widths, font, lead, shade)
            cols = [c[room:] for c in cols]
            if any(cols):
                self._new_page()
                if header:
                    self._row(header[0], header[1], bold=True, shade=True)

    def _row_lines(self, cols, widths, font, lead, shade) -> None:
        height = max(len(c) for c in cols) * lead + 2 * PAD
        top, x, out = self.y, MARGIN, self.pages[-1]
        if shade:
            out.append(f"0.9 g {x:.2f} {top - height:.2f} {sum(widths):.2f} {height:.2f} re f 0 g")
        for lines, w in zip(cols, widths, strict=False):
            out.append(f"0.5 w {x:.2f} {top - height:.2f} {w:.2f} {height:.2f} re S")
            for i, line in enumerate(lines):
                self._text(x + PAD, top - PAD - (i + 1) * lead + 3, line, font)
            x += w
        self.y -= height

    def to_bytes(self) -> bytes:
        total = len(self.pages)
        for n, page in enumerate(self.pages, 1):
            foot = f"{self.footer} · Page {n} of {total}".replace("·", "-")
            page.append(
                f"BT /F1 8 Tf {MARGIN:.2f} {MARGIN:.2f} Td ({_esc(clean(foot))}) Tj ET"
            )
        objs: list[bytes] = [b"", b"", b"", b""]  # 1 catalog, 2 pages, 3 and 4 fonts
        objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
        font = b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>"
        objs[2] = font % b"Helvetica"
        objs[3] = font % b"Helvetica-Bold"
        kids = []
        for page in self.pages:
            stream = "\n".join(page).encode("ascii")
            objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
            content_no = len(objs)
            page_obj = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_no} 0 R >>"
            )
            objs.append(page_obj.encode("ascii"))
            kids.append(f"{len(objs)} 0 R")
        objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {total} >>".encode("ascii")
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objs) + 1)
        out += b"startxref\n%d\n%%%%EOF\n" % xref
        return bytes(out)
