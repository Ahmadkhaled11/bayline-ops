# Set up your AI account

The desk helper calls a language model from your own computer. Bayline gives out no keys: you use a free account of your own. This guide sets one up and checks it once.

Before you start, set up the repository as the README says, and make sure `python -m pytest` runs. The tests need no network and no key.

In the commands below, replace `python` with `.venv\Scripts\python` on Windows or `.venv/bin/python` on macOS and Linux.

## 1. Get a free key

Use Google's Gemini API.

1. Go to https://aistudio.google.com and sign in with a Google account.
2. Read the terms before you accept them. Some free plans are only for people aged 18 or over.
3. Choose **Get API key**, then **Create API key**.
4. Copy the key and keep it somewhere safe, such as a password manager.

On a free plan, the provider may keep what you send and use it to improve its models. Send only the sample messages in this repository, never real customer details.

## 2. Check it once

The tool reads four settings from your terminal. They last until you close it.

Windows PowerShell:

```powershell
$env:BAYLINE_LLM_MODE = "live"
$env:BAYLINE_LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
$env:BAYLINE_LLM_MODEL = "gemini-3.5-flash-lite"
$key = Read-Host "Key" -AsSecureString
$env:BAYLINE_LLM_API_KEY = [System.Net.NetworkCredential]::new("", $key).Password
python -m bayline llm-check --ping
```

macOS and Linux:

```sh
export BAYLINE_LLM_MODE=live
export BAYLINE_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export BAYLINE_LLM_MODEL=gemini-3.5-flash-lite
printf "Key: "; read -rs BAYLINE_LLM_API_KEY; echo
export BAYLINE_LLM_API_KEY
python -m bayline llm-check --ping
```

Paste the key when the terminal asks for it. It does not show on screen.

It worked if `key set` says `yes` and the last line starts with `response:` followed by a few words from the model. The key itself is never printed.

Close this terminal when you are done. Everything else runs in replay mode, which sends nothing.

## 3. If the check fails

| The tool says | What to do |
| --- | --- |
| No `response:` line, and `mode: replay` | `BAYLINE_LLM_MODE` is not set to `live` in this terminal. |
| `Missing BAYLINE_LLM_...` | That setting is not set in this terminal. Set it and run the check again. |
| `BAYLINE_LLM_MODE must be replay, live or record` | The mode is mistyped. Set it to `live`, in small letters. |
| `BAYLINE_LLM_BASE_URL must be an HTTP base address without credentials or query` | Copy the base address exactly as above, with nothing after it. |
| `Model HTTP 400` | Check the model name. If it is right, the provider refused the request; tell Sana. |
| `Model HTTP 401` or `Model HTTP 403` | The key is wrong or not active yet. Create a new one and paste it again. |
| `Model HTTP 404` | The model name or the base address is wrong. Check both. |
| `Model HTTP 429` | Too many requests for the free plan. Wait a minute and try once more. |
| Any other `Model HTTP` number | Check the key, the model name and the base address. |
| `Model transport unavailable` | Your computer could not reach the provider. Check your connection, a proxy or a firewall. |
| `Model returned an invalid response` | The base address is not the provider's OpenAI-compatible address, or the model name is wrong. Check both. |

If it still fails, tell Sana in `# customer-platform` what the tool said. Never paste the key.

## 4. Keep your key safe

- Never put a key in a file inside this repository, not even one that Git ignores.
- Never paste a key into an issue, a pull request or the chat.
- If a key leaks, delete it on the provider's page and create a new one.
