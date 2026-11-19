"""Tag history on the Capability catalog: list, what changed, Restore T (Upgrade G, G5f).

AS400 picture: the save-file list of the tag file with a compare and a restore. Plain components;
the work is done by agents/da_tag_versions.py."""

import dash_mantine_components as dmc

from agents.da_tag_versions import list_versions

TAG_A = "adm-tagver-a"
TAG_B = "adm-tagver-b"
TAG_COMPARE_BTN = "adm-tagver-compare"
TAG_COMPARE_OUT = "adm-tagver-compare-out"
TAG_RESTORE = "adm-tagver-restore"
TAG_RESTORE_BTN = "adm-tagver-restore-btn"
TAG_RESTORE_MODAL = "adm-tagver-restore-modal"
TAG_RESTORE_CONFIRM = "adm-tagver-restore-confirm"
TAG_RESTORE_LATER = "adm-tagver-restore-later"
TAG_RESTORE_OUT = "adm-tagver-restore-out"
RESTORE_ASK = (
    "The program tags go back to this version and are saved as a new version. The catalog "
    "(rulebook) is not changed: undo an Approve there with History, Restore."
)


def version_options(directory=None) -> list[dict]:
    return [
        {"value": str(r["version"]), "label": f"T{r['version']}: {r['note']} ({r['who']})"[:80]}
        for r in list_versions(directory)
    ]


def _select(component_id: str, data: list[dict], placeholder: str):
    return dmc.Select(id=component_id, data=data, placeholder=placeholder, size="xs", w=260)


def tag_history_panel(directory=None):
    data = version_options(directory)
    return dmc.Stack(
        [
            dmc.Text("Tag history", fw=600, size="sm", mt="sm"),
            dmc.Text(
                "Every approve, reject, assign and restore saves the program tags as a version."
                if data
                else "No tag versions yet. The first Admin decision saves one.",
                size="xs",
                c="dimmed",
            ),
            dmc.Group(
                [
                    _select(TAG_A, data, "From version"),
                    _select(TAG_B, data, "To version"),
                    dmc.Button("What changed", id=TAG_COMPARE_BTN, size="xs", variant="default"),
                ],
                gap="xs",
            ),
            dmc.Text("", id=TAG_COMPARE_OUT, size="sm"),
            dmc.Group(
                [
                    _select(TAG_RESTORE, data, "Restore version"),
                    dmc.Button("Restore", id=TAG_RESTORE_BTN, size="xs", variant="default"),
                ],
                gap="xs",
            ),
            dmc.Text("", id=TAG_RESTORE_OUT, size="sm"),
            dmc.Modal(
                dmc.Stack(
                    [
                        dmc.Text(RESTORE_ASK, size="sm"),
                        dmc.Group(
                            [
                                dmc.Button("Later", id=TAG_RESTORE_LATER, variant="default"),
                                dmc.Button("Restore these tags", id=TAG_RESTORE_CONFIRM),
                            ]
                        ),
                    ]
                ),
                id=TAG_RESTORE_MODAL,
                title="Restore this version?",
                opened=False,
            ),
        ],
        gap="xs",
    )
