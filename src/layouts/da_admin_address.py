"""Fix G5 N5: the Admin tab and view live in the address (/admin?tab=catalog&view=queue).

The same words are used by the page on load (Python) and by two small browser callbacks that
keep the address and the tabs in step (no reload). A bad key is ignored: Overview opens."""

import json
from urllib.parse import parse_qs

from layouts.da_admin_common import (
    ADMIN_TABS,
    TAB_CAPABILITY,
    TAB_OVERVIEW,
    TAB_REPO,
)
from layouts.da_admin_queue_ids import VIEW_CAPS, VIEW_QUEUE

# address key -> the id the page uses inside (the two that differ from the key)
_RENAMED = {TAB_REPO: "repository", TAB_CAPABILITY: "catalog"}
TAB_KEYS = {_RENAMED.get(tab, tab): tab for tab, _, _ in ADMIN_TABS}
VIEW_KEYS = {"capabilities": VIEW_CAPS, "queue": VIEW_QUEUE}


def tab_and_view(search: str | None) -> tuple[str, str | None]:
    """(tab id, view id or None) from the address text. Unknown or missing: Overview."""
    query = parse_qs((search or "").lstrip("?"))
    tab = TAB_KEYS.get((query.get("tab") or [""])[0], TAB_OVERVIEW)
    view = VIEW_KEYS.get((query.get("view") or [""])[0]) if tab == TAB_CAPABILITY else None
    return tab, view


# Browser side. Address -> tabs (Back, Forward, a typed link) and tabs -> address (a click).
_TAB_KEYS = json.dumps(TAB_KEYS)
_VIEW_KEYS = json.dumps(VIEW_KEYS)
_CAPABILITY = json.dumps(TAB_CAPABILITY)

ADDRESS_TO_TABS_JS = f"""
function(search, tab, view) {{
    var noChange = window.dash_clientside.no_update;
    var query = new URLSearchParams(search || '');
    var tabs = {_TAB_KEYS}, views = {_VIEW_KEYS};
    var wantTab = tabs[query.get('tab')];
    if (!wantTab) {{ return [noChange, noChange]; }}
    var wantView = wantTab === {_CAPABILITY} ? views[query.get('view')] : undefined;
    return [wantTab === tab ? noChange : wantTab,
            !wantView || wantView === view ? noChange : wantView];
}}
"""

TABS_TO_ADDRESS_JS = f"""
function(tab, view, search) {{
    var tabs = {_TAB_KEYS}, views = {_VIEW_KEYS};
    var key = Object.keys(tabs).find(function (k) {{ return tabs[k] === tab; }});
    if (!key) {{ return window.dash_clientside.no_update; }}
    var query = new URLSearchParams();
    query.set('tab', key);
    if (tab === {_CAPABILITY}) {{
        var viewKey = Object.keys(views).find(function (k) {{ return views[k] === view; }});
        if (viewKey) {{ query.set('view', viewKey); }}
    }}
    var next = '?' + query.toString();
    return next === (search || '') ? window.dash_clientside.no_update : next;
}}
"""
