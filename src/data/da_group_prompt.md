You are helping an Admin name an area (a capability) of an application.
These programs call each other a lot, so they probably belong together. Below are only their file
paths and one-line summaries. Answer with JSON only. No other words.

Programs{cut_note}:
{programs}

Reply with exactly this JSON shape:
{{"name": "<2 to 40 characters, plain business words, no path, no person's name>",
"description": "<max 120 characters, what this area covers>",
"not_in_group": ["<exact paths from the list that do not fit this area>"],
"confidence": "high|medium|low"}}
