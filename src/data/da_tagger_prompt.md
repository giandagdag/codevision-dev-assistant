You are helping an Admin sort programs into capabilities (areas of an application).
Read the program below and answer with JSON only. No other words.

Module: {path}

Capabilities you may choose from (name: what it covers):
{capabilities}

Program text{cut_note}:
```
{code}
```

Reply with exactly this JSON shape:
{{"summary": "<one plain line, max 120 characters, what the program does>",
"capability": "<one exact name from the list above, or none, or new>",
"confidence": "high|medium|low",
"reason": "<max 160 characters, why that capability>"}}
Use "new" only when the program clearly belongs to an area that no listed capability covers. Then add
two more fields: "new_name" (2 to 40 characters, plain words, no path, no person's name) and
"new_description" (max 120 characters, what the area covers). Otherwise leave them out.
