# Phase 2C: Work LLM connector

Status: APPROVED v1.0 (29 Oct 2026). Decisions D-A to D-D chosen by Gian. D-E proposed.
Depends on: Phase 2A, Phase 2B
Next: the Monday work test (2 Nov), then Phase 3, Discover
Deadline: built and merged by Sunday 1 Nov.

## In plain words

Today the app can only talk to the scripted fake AI. The "onprem" choice in `.env` is an empty
placeholder that stops with "not configured yet". This phase fills it in, so that on the work
laptop the Understand conversation runs against CodeVision's Qwen or Llama.

We cannot reach Qwen or Llama from home. So we build the connector to the standard
"chat completions" format (the same format CodeVision's `API_CALL` uses), and test the whole path
at home against a pretend server that answers in that same format. Friday's photos of the real
work code confirm the details; any difference is a small adjustment on Saturday (section 6).

AS400 comparison: the screen (DDS) and the logic (RPG) already exist. This phase writes the
program that calls the remote system, against its published parameter list, plus a dummy
remote program on the test LPAR that answers the same way. A ping utility (like PING or a
quick CALL test) proves the line works before the real screen is used.

## 1. Goal

- With `DA_LLM_PROVIDER=onprem` and the work settings filled in, a developer can run the full
  Understand conversation against Qwen or Llama, from the first message to CONFIRMED_FOR_DISCOVERY.
- At home, the same path is proven end to end against the pretend server, including errors.
- On Monday, a one-command ping shows in seconds whether the work LLM can be reached, and any
  reply the engine rejects is saved to a local file so it can be read and fixed quickly.

## 2. In scope

### 2.1 The onprem client (`agents/da_llm_client.py`)
- New `OnPremLLMClient` with the same `complete(prompt, system=None) -> LLMReply` as the other
  providers. `get_llm_client` returns it for `onprem` instead of raising "not configured yet".
- Library: `requests` 2.32.5 (already on the work `requirements.txt`). Add it to
  `requirements.txt`. If Friday's photo shows CodeVision uses `httpx`, switching is a Saturday change.
- Sends one HTTP POST to `DA_ONPREM_URL` with a JSON body:
  `model`, `messages` (a `system` message only when given, then the `user` message),
  `temperature` 0.2 and `top_p` 0.2 (as CodeVision's `llm_config.py`), `max_tokens` 2048,
  `stream` false.
- Headers: `Content-Type: application/json`. When `DA_ONPREM_API_KEY` is set, one auth header:
  name `DA_ONPREM_AUTH_HEADER` (default `Authorization`), value `DA_ONPREM_AUTH_PREFIX`
  (default `Bearer `) followed by the key. No auth header when the key is empty.
- Reply text is read from `choices[0].message.content`. The model name comes from the reply's
  `model` field when present, else the setting.
- Network retries (separate from the engine's existing "bad JSON, try once more" retry):
  connection errors, timeouts, HTTP 429 and HTTP 5xx are tried up to 3 times in total
  (CodeVision also retries 3 times), waiting 2 then 4 seconds. Other 4xx answers are not retried.
- Every failure raises `LLMClientError` with a plain message that says what to check:
  cannot connect (check `DA_ONPREM_URL` and the network), timed out after N seconds,
  certificate problem (check `DA_ONPREM_VERIFY`), 401/403 (check the key), 404 (check the URL path),
  any other status (the code plus at most 300 characters of the answer), and a reply in the wrong
  shape (for example no `choices`). The key never appears in any message or log line.

### 2.2 Settings (`configs/da_config.py`, `.env.example`)

| Setting | Default | Meaning |
|---|---|---|
| `DA_ONPREM_URL` | none, required for onprem | Full chat-completions address |
| `DA_ONPREM_MODEL` | none, required for onprem | Model name: Qwen or Llama (D-B). Used for both roles for now |
| `DA_ONPREM_API_KEY` | empty | Secret. Only in `.env`. Hidden from printouts (`repr=False`) |
| `DA_ONPREM_AUTH_HEADER` | `Authorization` | Name of the auth header |
| `DA_ONPREM_AUTH_PREFIX` | `Bearer ` | Text placed before the key |
| `DA_ONPREM_VERIFY` | `true` | `true`, `false`, or the path to the bank's certificate file (D-C) |
| `DA_ONPREM_TIMEOUT_SECONDS` | `120` | How long to wait for one reply |

- Missing URL or model with `onprem` chosen: `ConfigError` naming the missing setting.
- `DA_ONPREM_VERIFY=false`: allowed for the prototype, but a WARNING line is logged every time an
  onprem client is created ("Certificate check is OFF. Use only for the prototype.").
- A certificate path that does not exist: `ConfigError` naming the path.
- `.env.example` gets the new settings with made-up values only (for example
  `https://llm.example.com/v1/chat/completions`). Never a real address.

### 2.3 Rejected-reply log (D-D)
- When the engine rejects an interpreter reply (`parse_reply` returns problems, any provider),
  append one entry to `logs/da_rejected_replies.log`: time in Singapore time, request ID when
  available, attempt number, provider, model, the problem list, and the raw reply text
  (cut at 20,000 characters).
- `logs/` is added to `.gitignore`. The file stays on the laptop.
- If the file cannot be written, log a warning and carry on. The conversation never fails because
  of this log.
- Surgical change to `agents/da_understand_agent.py`: only the hook that writes the entry.

### 2.4 Ping script (`src/da_llm_ping.py`)
- Like CodeVision's `test_connection.py`. Loads the settings, makes the generator client, sends a
  tiny prompt (system: "Reply with the single word OK.", user: "ping").
- Prints: provider, model, the server's host name only (never the full address or key), time
  taken, and the first 200 characters of the reply. On failure prints the plain error.
- Exit code 0 on success, 1 on failure. Works with `fake` too.
- Run: `.venv\Scripts\python src\da_llm_ping.py`

### 2.5 Pretend server (`src/web/da_fake_onprem_server.py`)
- Standard library only (`http.server`), listens on 127.0.0.1 only, default port 8070.
- Accepts the chat-completions POST and answers in the same shape as the real server
  (`choices[0].message.content`, `model`), with content taken from the same scripted entries the
  fake interpreter uses, in the same order. So the whole screen runs with `onprem` at home.
- Modes (command-line option): `normal`; `bad-json` (the first reply of each turn is not JSON, to
  prove the engine retry and the rejected-reply log); `error` (answers HTTP 500, to prove the
  network retry and the error message).
- If `DA_FAKE_ONPREM_KEY` is set, it refuses requests without the matching auth header (401),
  so the auth path is tested too.
- Run: `.venv\Scripts\python src\web\da_fake_onprem_server.py`, then in `.env` set
  `DA_LLM_PROVIDER=onprem`, `DA_ONPREM_URL=http://127.0.0.1:8070/v1/chat/completions`,
  `DA_ONPREM_MODEL=fake-qwen`, and start the screen as usual.

### 2.6 Smoke check (extend `da_smoke_check.py`)
13. The ping succeeds with `onprem` against the pretend server
14. A full conversation with `onprem` against the pretend server reaches CONFIRMED_FOR_DISCOVERY

### 2.7 Monday checklist (`docs/monday-work-test.md`)
One page, plain steps, AS400 comparisons where helpful:
1. Unzip, create `.venv` with Python 3.14, `pip install -r requirements.txt` (work libraries only)
2. Copy `.env.example` to `.env`; fill the `DA_ONPREM_*` values from CodeVision's settings
   (never into any file that leaves the laptop)
3. Run the rulebook loader, then the ping. Stop and note the error if the ping fails
4. Start the screen (D-E) and run one full conversation with Qwen, then repeat with Llama
5. What to write down: ping result, which step failed, the rejected-reply log entries, how long
   each reply took
6. The "check at work" items already known: Enter-to-send uses inline JavaScript (README note)

### 2.8 README
- "How Phase 2C works", with the ping and pretend-server run commands.

## 3. Out of scope (do NOT build in 2C)
- Phase 3 or any later phase.
- Plugging the page into CodeVision's real menu and page routing (needs the Q6 photo; after Monday).
- Changing the Understand prompt. Only after we see Monday's real replies.
- Streaming replies, a separate reviewer model, P10 and the deferred demo look items.

## 4. Rules
- R1. No secrets in code, logs, tests or error messages. The key lives only in `.env`.
- R2. Tests never call a real AI or the internet. The pretend server runs on 127.0.0.1 only,
  started by the tests themselves.
- R3. Made-up addresses only (`example.com`). Never copy work addresses into home files.
- R4. Certificate check is on by default. Off only by an explicit `.env` setting, with a warning.
- R5. Surgical changes: 2A and 2B files are touched only where this spec says.
- R6. Work libraries only: `requests` 2.32.5 is the one addition.
- All earlier phase rules still apply.

## 5. Done when
- [ ] `pytest` 0 failures (all earlier tests included), `ruff check` 0 problems
- [ ] The smoke check prints items 1 to 14
- [ ] Tests prove: the request body and headers match 2.1 (with and without a key, with and
      without a system message)
- [ ] Tests prove: reply text and model are read from a chat-completions answer
- [ ] Tests prove: timeouts, connection errors, 429 and 500 are retried up to 3 times; 401, 403
      and 404 are not; each gives its plain message
- [ ] Tests prove: a wrong-shape answer gives a plain message, not a crash
- [ ] Tests prove: the key never appears in error messages or log output
- [ ] Tests prove: missing URL or model gives a ConfigError naming the setting; verify `false`
      logs the warning; a missing certificate path gives a ConfigError
- [ ] Tests prove: a rejected reply writes one log entry with the raw text, and a log that cannot
      be written does not stop the conversation
- [ ] Tests prove: the ping script exits 0 on success and 1 on failure
- [ ] Gian's hands-on check at home: with the pretend server and `onprem`, a full conversation on
      the screen; in `bad-json` mode, the rejected-reply log has entries
- [ ] Reviewer: 0 Must fix. README and the Monday checklist written. Parked items updated.

## 6. To confirm from Friday's photos (Saturday adjustment)
- Auth: the header name and value format (Bearer, a custom key header, or none)
- Body: any extra or differently named fields (for example a custom ID or `max_new_tokens`)
- Reply: where the text sits, if not `choices[0].message.content`
- Library: `requests` or `httpx` inside `API_CALL`
- Any extra required headers, and the path shape of the endpoint
Each difference becomes a settings default or a one-function change, with its test updated.

## 7. Decisions

| # | Question | Decision |
|---|---|---|
| D-A | How to talk to Qwen/Llama | Own small client, standard chat format, testable at home (Gian, 29 Oct) |
| D-B | Which model for Understand | A setting in `.env`, so Qwen and Llama can both be tried on Monday (Gian, 29 Oct) |
| D-C | Certificate check | On by default, certificate file setting, can be switched off in `.env` with a warning (Gian, 29 Oct) |
| D-D | Rejected replies | Saved to a local log file with the raw text (Gian, 29 Oct) |
| D-E | How to run the screen on Monday | PROPOSED: run our stand-in web server on the work laptop (127.0.0.1 only) for the test. Plugging into CodeVision's menu comes after Monday. This relaxes 2B's "never copied to work" for the home web server, for the test only |

## 8. Decisions made during planning
(The planner adds them here.)
