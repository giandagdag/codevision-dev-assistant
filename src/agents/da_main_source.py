"""Where the server gets a file "as it is on Bitbucket main" (Phase 9, spec section 5).

Like comparing your source member with the production library before you start (CMPPFM): if someone
promoted a change after you copied it, editing your old copy would undo their work. At home the
`fake` source reads a made-up folder. The `bitbucket` source is a placeholder until work fact WF-1
says how the real one is reached. A check that cannot run is never a silent pass.
"""

from pathlib import Path
from typing import Protocol

from agents.da_workspace_checks import fingerprint
from configs.da_config import Settings
from pydantic_classes.da_enhance_models import FreshnessResult, PathFreshness

NOT_CONFIGURED_MESSAGE = "Bitbucket main is not configured yet."
UNREACHABLE_TEXT = "I could not reach Bitbucket main, so freshness is not checked."


class MainSourceError(Exception):
    """Main could not be read (not configured, timeout, error). The message says why."""


class MainSource(Protocol):
    name: str

    def get_text(self, path: str) -> str | None:
        """The file as on main, or None when main has no such file. Raises MainSourceError."""
        ...


class FakeMainSource:
    """A made-up folder that stands in for Bitbucket main."""

    name = "fake"

    def __init__(self, folder: Path) -> None:
        self._folder = Path(folder).resolve()

    def get_text(self, path: str) -> str | None:
        target = (self._folder / path).resolve()
        # A path that climbs out of the folder is simply "not on main".
        if self._folder not in target.parents or not target.is_file():
            return None
        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise MainSourceError(f"The fake main folder could not be read: {error}") from error


class BitbucketMainSource:
    """Placeholder until the work adapter exists (WF-1)."""

    name = "bitbucket"

    def get_text(self, path: str) -> str | None:
        raise MainSourceError(NOT_CONFIGURED_MESSAGE)


def get_main_source(settings: Settings) -> MainSource:
    if settings.main_source == "bitbucket":
        return BitbucketMainSource()
    return FakeMainSource(settings.fake_main_dir)


# --- the comparison (plain code) ---


def check_path(path: str, his_text: str | None, source: MainSource) -> PathFreshness:
    """Compare one file. `his_text` is None when his folder does not have it."""
    if his_text is None:
        return PathFreshness(path=path, state="missing_in_folder")
    his = fingerprint(his_text)
    try:
        main_text = source.get_text(path)
    except MainSourceError:
        return PathFreshness(path=path, state="unreachable", his_fingerprint=his)
    if main_text is None:
        return PathFreshness(path=path, state="not_on_main", his_fingerprint=his)
    main = fingerprint(main_text)
    state = "equal" if his == main else "differs"
    return PathFreshness(path=path, state=state, his_fingerprint=his, main_fingerprint=main)


def check_freshness(files: dict[str, str | None], source: MainSource) -> FreshnessResult:
    """`files` maps each target path to the text from his folder (None = missing there)."""
    paths = [check_path(path, text, source) for path, text in files.items()]
    return FreshnessResult(paths=paths, main_source=source.name)


def next_step(result: FreshnessResult) -> str:
    """`e_fresh` when every file equals main, otherwise `e_stale`."""
    return "e_fresh" if result.all_equal else "e_stale"


def stale_options(result: FreshnessResult) -> list[str]:
    """The buttons at `e_stale` (spec section 5, steps 5 and 6). Check again is always there.
    "Intentional" needs a copy that really differs; "unchecked" needs a main that could not be
    reached. A file missing from his folder has no text to keep, so neither override is offered."""
    options = ["check_again"]
    states = {item.state for item in result.paths}
    if "missing_in_folder" in states or result.all_equal:
        return options
    if "unreachable" in states:
        options.append("unchecked")
    elif states & {"differs", "not_on_main"}:
        options.append("intentional")
    return options


def stale_message(result: FreshnessResult) -> str:
    """The plain words for the chat and the banner (spec section 5, steps 1, 4, 5 and 6)."""
    if result.all_equal:
        return "Freshness check passed. Your copy matches Bitbucket main."
    lines: list[str] = []
    for item in result.paths:
        if item.state == "missing_in_folder":
            lines.append(
                f"Your folder does not have `{item.path}`. Get the latest code, or choose "
                "another folder."
            )
        elif item.state == "not_on_main":
            lines.append(f"`{item.path}` is not on Bitbucket main yet.")
        elif item.state == "differs":
            lines.append(
                f"Your copy of `{item.path}` differs from Bitbucket main. Building on an old "
                "copy could undo someone else's change. Get the latest code first (`git pull` "
                "in Command Prompt, or download a fresh ZIP from Bitbucket), or confirm your "
                "local changes are intentional."
            )
    if any(item.state == "unreachable" for item in result.paths):
        lines.append(UNREACHABLE_TEXT)
    return "\n".join(lines)
