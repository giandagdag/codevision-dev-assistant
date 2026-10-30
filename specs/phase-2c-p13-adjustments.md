# Phase 2C, P13: adjustments from the work photos

Status: APPROVED v1.0 (30 Oct 2026). Decisions by Gian, 30 Oct.
Depends on: Phase 2C (merged, PR #5)
Build: Saturday 31 Oct, branch `phase-2c-p13`, before the Monday work test (2 Nov).

## In plain words

Friday's photos of CodeVision's own LLM code (`spirare.py`, `payload_generation.py`,
`llm_config.py`) confirmed most of what 2C guessed. This is a short list of small changes so our
onprem client sends exactly what the work server already accepts, and copes with a
"reasoning" model. No real addresses, keys or names go into any file.

AS400 comparison: the remote program's parameter list turned out slightly different from the
manual. We adjust our CALL to match, nothing else.

## 1. What the photos confirmed (no change needed)
- Library `requests`, body sent as JSON. Reply text at `choices[0].message.content`.
- Auth header `Authorization: Bearer <key>`, plus `Content-Type: application/json` (our defaults).
- Endpoint path shape `.../v1/chat/completions`. Temperature and top_p 0.2. Up to 3 retries.
- Messages: one `system` (the prompt) and one `user` message.

## 2. Changes

### 2.1 Body matches CodeVision (decision P13-A)
- By default the body has only `model`, `messages`, `temperature`, `top_p`. Remove `max_tokens`
  and `stream` from the default body.
- New setting `DA_ONPREM_MAX_TOKENS`: empty by default (field not sent). A number sends
  `max_tokens` with that value, for use if Monday's replies come back cut short.
- `.env.example`: add the setting, empty, with a one-line comment.

### 2.2 Plain messages for two work-specific status codes
- HTTP 400: not retried. Message: "The AI server refused the request as too large (HTTP 400).
  The prompt or context is probably too long." (CodeVision treats 400 as "too much context".)
- HTTP 407: retried like 429 and 5xx (counts within the 3 tries). Final message: "The network
  proxy asked for sign-in (HTTP 407). Check the proxy settings on this laptop." (CodeVision
  retries on 407.)

### 2.3 Strip a reasoning block before parsing (decision P13-B)
- CodeVision's default model is named `reasoning-vlm`. Reasoning models often put their thinking
  in `<think>...</think>` before the answer.
- In `agents/da_understand_agent.py`, before the JSON is parsed: if the reply contains a
  `<think>...</think>` block (case-insensitive, possibly multi-line), remove it and any whitespace
  around it. Also remove a lone closing `</think>` with everything before it (some servers drop
  the opening tag). Then parse as today.
- The rejected-reply log keeps the FULL raw reply, think block included.
- Surgical: one small helper plus one call. Nothing else in the engine changes.

### 2.4 Monday checklist (`docs/monday-work-test.md`)
Update step 2 with where each value comes from, without writing any value into the file:
- `DA_ONPREM_URL`: the active (not commented out) chat-completions setting in CodeVision's
  `configs/llm_config.py`
- `DA_ONPREM_MODEL`: start with `reasoning-vlm` (CodeVision's default). Then try `default`.
  Which name is Qwen or Llama is not known yet; write down what each one is.
- `DA_ONPREM_API_KEY`: the value of `SPIRARE_API_KEY` in CodeVision's `.env`
- `DA_ONPREM_VERIFY`: first try the path to the certificate file in CodeVision's `cert` folder.
  If the ping shows a certificate error, set `false` (CodeVision itself runs with checking off).
- Port: CodeVision also uses port 8050. Stop CodeVision before starting our screen.

## 3. Out of scope
- Plugging the page into CodeVision's menu and routing (after Monday; the photos showed it is
  3 small edits: `display_page_from_url_change` in `universal_callbacks.py`, `navigation_links()`
  in `web_components.py`, and callback registration in `web_server.py`).
- Changing the Understand prompt. Phase 3.

## 4. Done when
- [ ] `pytest` 0 failures, `ruff check` 0 problems, smoke check items 1 to 14 pass
- [ ] Tests prove: default body has no `max_tokens` or `stream`; with `DA_ONPREM_MAX_TOKENS=1500`
      it sends `max_tokens` 1500
- [ ] Tests prove: 400 is not retried and gives its message; 407 is retried and gives its message
- [ ] Tests prove: a reply wrapped in a think block, and one with only a closing `</think>`, both
      parse; a normal reply is unchanged; the log keeps the raw text with the think block
- [ ] Reviewer: 0 Must fix. P13 marked done in `specs/parked-items.md`

## 5. Decisions

| # | Question | Decision |
|---|---|---|
| P13-A | Body fields | Match CodeVision exactly; `max_tokens` only via a setting (Gian, 30 Oct) |
| P13-B | Reasoning block | Strip `<think>` before parsing, keep the raw reply in the log (Gian, 30 Oct) |
