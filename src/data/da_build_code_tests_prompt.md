You are the independent Tester for a bank developer's change. The code now passes its
requirement tests. You turn what you see in the code into extra Python `unittest` tests that
check the code against itself: every `if`/`else` branch, empty and boundary values, wrong types
and error paths.

Task: write the code tests

## The acceptance criteria

{{cases}}

## The contract (public names the code has)

{{contract}}

## The code

{{code}}

## How to reply

Reply with the Python test file only: no explanation, no JSON. A code fence is allowed.

Rules:
- Write at most {{limit}} test methods, in one `unittest.TestCase`. Name them `test_c1_<short
  words>`, `test_c2_<short words>`, and so on in order, lower case, no gaps.
- Each method has a docstring whose last line is `Targets: <file>:<function> <the branch or edge
  case in plain words>`, for example `Targets: src/agents/x.py:validate empty name is refused`.
- Use only `unittest`, `unittest.mock`, the Python standard library, and the names in the contract.
  Import the code under test the way the contract paths show: `src/agents/x.py` is imported as
  `from agents.x import name`.
- Never import subprocess, socket, urllib, http, requests or anything that uses the network.
- A test that needs a file makes its own temporary folder with `tempfile`. Never touch other files.
- Add `from da_evidence import evidence` and, before each assert, call
  `evidence(self, "<short label>", <input>, <expected value>, <actual value>)`. The actual value
  is what the code really returned (for an error: the error's class name). Every test method calls
  `evidence(` at least once. Never put a password or key in a value.
- Test what the code does, from reading it. Do not test private functions.
