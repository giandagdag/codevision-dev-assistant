"""UI standards panels (fix 11-1, AF-13): brand constants with swatches, and severity pills.

A swatch is a real colour square; a value that is not a colour (such as "Pending brand guide" for a
colour name) gets a striped square so nobody mistakes it for a real colour.
"""

import re

import dash_mantine_components as dmc
from dash import html

from agents.da_admin_cited import FIRES_AMBER_ABOVE
from styles import da_admin_styles as pal

HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
FONT_ROWS = ("FONT_FAMILY", "FONT_BOLD")
# Every other row that is not a hex colour is a colour still waiting for the brand guide.
NOT_COLOURS = (*FONT_ROWS, "SPACING", "TABLE_PAGE_SIZE")
SEVERITY_PILL = {
    "must_fix": ("Must fix", "red"),
    "should_fix": ("Should fix", "amber"),
    "fyi": ("FYI", "blue"),
}
SWATCH_BOX = {"width": 22, "height": 22, "borderRadius": 4, "border": f"1px solid {pal.NAVY}"}
STRIPES = (
    f"repeating-linear-gradient(45deg, {pal.AMBER_LIGHT}, {pal.AMBER_LIGHT} 4px, "
    f"{pal.AMBER} 4px, {pal.AMBER} 6px)"
)


def severity_pill(severity: str):
    text, colour = SEVERITY_PILL.get(severity, (severity, "blue"))
    return dmc.Badge(text, variant="light", style=pal.pill_style(colour))


def swatch(name: str, value: str):
    """The little square in front of a brand row."""
    if name in FONT_ROWS:
        style = {"fontFamily": value if name == "FONT_FAMILY" else "inherit"}
        if name == "FONT_BOLD":
            style["fontWeight"] = value
        return html.Div("Aa", style={**style, "fontSize": 16, "width": 28}, className="adm-swatch")
    if HEX_COLOUR.match(value.strip()):
        return html.Div(style={**SWATCH_BOX, "background": value.strip()}, className="adm-swatch")
    if name not in NOT_COLOURS:
        return html.Div(
            style={**SWATCH_BOX, "background": STRIPES},
            className="adm-swatch adm-swatch-pending",
        )
    return html.Div(style={"width": 22}, className="adm-swatch adm-swatch-none")


def convention_rows(rules: list[dict]):
    """UI conventions as rule rows: ID chip, text, severity pill (read view)."""
    rows = [
        dmc.Group(
            [
                dmc.Code(r["rule_id"]),
                dmc.Text(r["title"], size="sm"),
                severity_pill(r["severity"]),
            ],
            gap="xs",
        )
        for r in rules
    ]
    return html.Div(
        [dmc.Text("UI conventions", fw=600, c=pal.NAVY, size="sm", mt="sm"), *rows]
    )


def fires_text(rule_id: str, fires: dict[str, int]) -> str:
    """"fires in 60%" (with a warning sign over 50%); "never fired" when no review cited it."""
    percent = fires.get(rule_id)
    if percent is None:
        return "not cited in the last 30 days"
    return ("⚠️ " if percent > FIRES_AMBER_ABOVE else "") + f"fires in {percent}%"


def brand_panel(constants):
    """The Brand constants table: swatch, name, value, source."""
    rows = [
        dmc.TableTr(
            [
                dmc.TableTd(swatch(c.name, c.value)),
                dmc.TableTd(dmc.Code(c.name)),
                dmc.TableTd(dmc.Text(c.value, size="sm")),
                dmc.TableTd(dmc.Text(c.source, size="sm")),
            ]
        )
        for c in constants
    ]
    header = dmc.TableTr([dmc.TableTh(h) for h in ("", "Name", "Value", "Source")])
    body = [dmc.Table([dmc.TableThead(header), dmc.TableTbody(rows)], withTableBorder=True)]
    if not constants:
        body = [dmc.Text("No brand constants in this version.", size="sm", c=pal.NAVY)]
    return html.Div([dmc.Text("Brand constants", fw=600, c=pal.NAVY, size="sm"), *body])
