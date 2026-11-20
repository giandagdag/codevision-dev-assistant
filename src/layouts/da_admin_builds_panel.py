"""Index builds on Repository and index: compare two builds, use an older build (Upgrade G, G5c/d).

AS400 picture: the save-file list with a compare and a restore. Plain components; the work is done
by agents/da_index_builds.py and da_index_rollback.py."""

import dash_mantine_components as dmc

from agents.da_admin_index import index_dir
from agents.da_index_builds import KEPT_INDEX_COPIES, build_numbers, has_copy

BUILD_A = "adm-build-a"
BUILD_B = "adm-build-b"
BUILD_COMPARE_BTN = "adm-build-compare"
BUILD_COMPARE_OUT = "adm-build-compare-out"
BUILD_USE = "adm-build-use"
BUILD_USE_BTN = "adm-build-use-btn"
BUILD_USE_MODAL = "adm-build-use-modal"
BUILD_USE_CONFIRM = "adm-build-use-confirm"
BUILD_USE_LATER = "adm-build-use-later"
BUILD_USE_OUT = "adm-build-use-out"
BUILD_USE_NAME = "adm-build-use-name"  # the confirm line that names the build
USE_ASK = (
    "The index files go back to this build. Newer builds and their copies stay, so you can go "
    "forward again. Discovery uses the restored index at once."
)


def build_options(directory=None) -> tuple[list[dict], list[dict]]:
    """(all builds, builds that still have a saved copy), newest first."""
    out = directory or index_dir()
    numbers = sorted(build_numbers(out), reverse=True)
    everything = [{"value": str(n), "label": f"Build {n}"} for n in numbers]
    return everything, [o for o in everything if has_copy(out, int(o["value"]))]


def _select(component_id: str, data: list[dict], placeholder: str):
    return dmc.Select(id=component_id, data=data, placeholder=placeholder, size="xs", w=130)


def builds_panel(directory=None):
    everything, with_copy = build_options(directory)
    return dmc.Stack(
        [
            dmc.Text("Index builds", fw=600, size="sm"),
            dmc.Text(
                f"The newest {KEPT_INDEX_COPIES} builds keep a full copy; older ones keep a "
                "summary only.",
                size="xs",
                c="dimmed",
            ),
            dmc.Group(
                [
                    _select(BUILD_A, everything, "From build"),
                    _select(BUILD_B, everything, "To build"),
                    dmc.Button("Compare", id=BUILD_COMPARE_BTN, size="xs", variant="default"),
                ],
                gap="xs",
            ),
            dmc.Text("", id=BUILD_COMPARE_OUT, size="sm"),
            dmc.Group(
                [
                    _select(BUILD_USE, with_copy, "Use build"),
                    dmc.Button("Use build", id=BUILD_USE_BTN, size="xs", variant="default"),
                ],
                gap="xs",
            ),
            dmc.Text("", id=BUILD_USE_OUT, size="sm"),
            dmc.Modal(
                dmc.Stack(
                    [
                        dmc.Text("", id=BUILD_USE_NAME, size="sm", fw=600),
                        dmc.Text(USE_ASK, size="sm"),
                        dmc.Group(
                            [
                                dmc.Button("Later", id=BUILD_USE_LATER, variant="default"),
                                dmc.Button("Use this build", id=BUILD_USE_CONFIRM),
                            ]
                        ),
                    ]
                ),
                id=BUILD_USE_MODAL,
                title="Use this build?",
                opened=False,
            ),
        ],
        gap="xs",
    )
