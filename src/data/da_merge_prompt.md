You are helping an Admin tidy a list of suggested areas (capabilities) of an application.
Below are the suggested names with a short description. Some may be the same area.
Answer with JSON only. No other words.

Suggested areas:
{areas}

Reply with exactly this JSON shape. List only areas that should be merged; leave the others out:
{{"merges": [{{"names": ["<exact name A>", "<exact name B>"],
"name": "<2 to 40 characters, plain business words>",
"description": "<max 120 characters>"}}]}}
Use an empty list when nothing should be merged.
