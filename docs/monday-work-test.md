# Monday work test (2 Nov): the Developer Assistant against Qwen and Llama

One page. Do the steps in order. If a step fails, stop and write down the exact message.
AS400 comparisons are in brackets.

**Before you start:** all addresses and keys below come from CodeVision's own settings. Type them
only into your `.env` on the work laptop. Never into a file that leaves the laptop.

## Steps

1. **Unzip and set up.** Unzip the project. Create `.venv` with Python 3.14, then install the work
   libraries only: `pip install -r requirements.txt` (not `requirements-home.txt`).
   [Like restoring the library to the test LPAR and checking it has the right objects.]
2. **Fill in `.env`.** Copy `.env.example` to `.env`. Set:
   - `DA_LLM_PROVIDER=onprem`
   - `DA_ONPREM_URL`: the active (not commented out) chat-completions setting in CodeVision's
     `configs/llm_config.py`
   - `DA_ONPREM_MODEL`: start with `reasoning-vlm` (CodeVision's default). Then try `default`.
     Which name is Qwen or Llama is not known yet; write down what each one is.
   - `DA_ONPREM_API_KEY`: the value of `SPIRARE_API_KEY` in CodeVision's `.env`. If CodeVision
     uses a different header, also set `DA_ONPREM_AUTH_HEADER` and `DA_ONPREM_AUTH_PREFIX`
     (keep the quotes, for example `"Bearer "`)
   - `DA_ONPREM_VERIFY`: first try the path to the certificate file in CodeVision's `cert`
     folder. If the ping shows a certificate error, set `false` (CodeVision itself runs with
     checking off; it logs a warning each time). [Like a data area the program reads at start-up.]
   - `DA_ONPREM_MAX_TOKENS`: leave empty (CodeVision sends none). Set a number such as `1500`
     only if replies come back cut short.
   - **Port:** CodeVision also uses port 8050. Stop CodeVision before starting our screen.
3. **Load the rulebook, then ping.**
   - `.venv\Scripts\python src\da_load_starter_rulebook.py`
   - `.venv\Scripts\python src\da_llm_ping.py`

   The ping shows provider, model, host name, seconds taken and the first part of the reply, then
   `Ping OK.` (exit code 0). If it fails it prints a plain message saying what to check.
   **If the ping fails, stop and write down the message.** [Like a PING before you trust the line.]
4. **Run one full conversation with Qwen.** Start the screen with our stand-in web server
   (`.venv\Scripts\python src\web\da_home_web_server.py`, then open http://127.0.0.1:8050).
   It listens on this laptop only. Describe a made-up change, answer the 4 questions, settle any
   decision, and press "Proceed with this understanding". The goal is CONFIRMED_FOR_DISCOVERY.
   Then stop the server, change `DA_ONPREM_MODEL` to Llama, start it again and repeat.
   (Plugging into CodeVision's own menu comes after Monday.)
5. **Write down:**
   - the ping result (and the seconds it took)
   - which step failed, if any, and the exact message on the screen
   - the entries in `logs\da_rejected_replies.log`: every reply the engine rejected is saved there
     with its raw text. Copy the file's contents, or a photo of the screen, for Gian.
   - how long each reply took (roughly, with a watch is fine)
6. **Already known to check at work:** Enter-to-send uses a small inline JavaScript (Dash clientside
   callback). If CodeVision blocks inline scripts, Send still works by clicking the button.

**Proxy note:** if the laptop has `HTTP_PROXY` or `HTTPS_PROXY` set, also set `NO_PROXY=127.0.0.1`,
otherwise the call to our stand-in server on this laptop could be sent through the proxy.

## If something goes wrong

| What you see | What to check |
|---|---|
| "Cannot connect to the AI server" | `DA_ONPREM_URL` and the network |
| "refused the request as too large (HTTP 400)" | the prompt or context is too long for the model |
| "network proxy asked for sign-in (HTTP 407)" | the proxy settings on this laptop |
| "did not answer within N seconds" | the network, or raise `DA_ONPREM_TIMEOUT_SECONDS` |
| "The certificate check failed" | `DA_ONPREM_VERIFY` |
| "refused the request (HTTP 401/403)" | `DA_ONPREM_API_KEY`, `DA_ONPREM_AUTH_HEADER`, `DA_ONPREM_AUTH_PREFIX` |
| "address was not found (HTTP 404)" | the path at the end of `DA_ONPREM_URL` |
| "not in the expected chat-completions shape" | the reply format differs from the standard one: write the line down |
| "I couldn't process that answer" | open `logs\da_rejected_replies.log` and read the raw reply |
