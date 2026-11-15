"""The waiting line each button shows while the server works (Fix batch B1, F12).

One table for the words. The key is the button's own label in lower case. A button that is not in
the table gets a line built from its own label, so no button ever shows another button's text.
A small browser script (see BUSY_JS) puts the line on screen the moment the button is pressed.
"""

import json

# Used when a label is not in the table: "⏳ Working on <label>…".
FALLBACK_TEMPLATE = "⏳ Working on “{label}”…"

BUSY_LINES = {
    "send": "⏳ Reading your message…",
    "confirm": "⏳ Saving your confirmation…",
    "proceed to approach": "⏳ Asking the AI for an approach…",
    "try again": "⏳ Trying again…",
    "accept approach": "⏳ Saving the approach and writing the test plan…",
    "change something": "⏳ Asking the AI to change it…",
    "get help": "⏳ Getting help for you…",
    "accept test plan": "⏳ Checking the test plan…",
    "keep this case": "⏳ Adding the test case…",
    "discard it": "⏳ Dropping the draft case…",
    "change the approach": "⏳ Going back to the approach…",
    "upload folder to check": "⏳ Checking your folder…",
    "upload folder to re-scan": "⏳ Re-scanning your folder…",
    "reconnect": "⏳ Reconnecting to your folder…",
    "build": "⏳ Starting the build…",
    "re-scan and build again": "⏳ Re-scanning your folder, then building again…",
    "check my edits": "⏳ Checking your edits…",
    "send to my senior": "⏳ Sending this to your senior…",
    "accept, with reason": "⏳ Saving your reason…",
    "keep mine": "⏳ Keeping your lines…",
    "take the ai's": "⏳ Taking the AI's lines…",
    "apply my choices": "⏳ Applying your choices…",
}


def busy_line(label: str) -> str:
    """The waiting line for a button label (the same rule the browser script uses)."""
    clean = label.strip()
    return BUSY_LINES.get(clean.lower()) or FALLBACK_TEMPLATE.format(label=clean)


# Installed once for the whole page. A click on any button puts that button's line on the busy
# text (the callbacks' `running=` then shows it). No rule lives here: it only chooses words.
BUSY_JS = f"""
function(content) {{
    if (!window.daBusyWords) {{
        window.daBusyWords = true;
        var lines = {json.dumps(BUSY_LINES, ensure_ascii=False)};
        var fallback = {json.dumps(FALLBACK_TEMPLATE, ensure_ascii=False)};
        document.addEventListener('click', function(event) {{
            var hit = event.target;
            var button = hit && hit.closest ? hit.closest('button') : null;
            var busy = document.getElementById('da-busy');
            if (!button || !busy) {{ return; }}
            var label = (button.innerText || '').trim();
            if (!label) {{ return; }}
            busy.textContent = lines[label.toLowerCase()] || fallback.replace('{{label}}', label);
        }}, true);
    }}
    return window.dash_clientside.no_update;
}}
"""
