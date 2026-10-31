# The SIGMAI chat

A chat panel inside QGIS, for people who do not use an MCP client. You bring the API key; SIGMAI brings the tools, the consent layer, the audit and the recipe.

## Open it

Click **API & Chat** in the header of the SIGMAI panel (or `Plugins ▸ SIGMAI ▸ SIGMAI — Chat`). The tabs give way to the chat, in the panel's own look; **Back to panel** returns to them. The chat starts the bridge if it is off.

The first time, a **Connect your AI** card asks for the provider, the model and your API key, and says what is sent to the provider. Once a key is stored, the page opens on the conversation, and **AI settings** brings the card back.

## Providers and models

| Provider | How SIGMAI talks to it | Models |
|---|---|---|
| Anthropic | Messages API, streaming | `claude-opus-5-5` (default), `claude-sonnet-5-5`, `claude-haiku-5-5` |
| OpenAI-compatible | `POST <base URL>/chat/completions`, streaming | whatever the service offers: type the model name |

Ready-made base URLs for the OpenAI format: `https://api.openai.com/v1`, `https://generativelanguage.googleapis.com/v1beta/openai` (Gemini) and `http://localhost:11434/v1` (Ollama). Only HTTPS addresses are accepted, plus `http` on this machine. Small local models often struggle with twenty tools.

For Anthropic models, **Effort** (low, medium, high) controls how much the model reasons before answering. Medium is the default.

Changing the provider or the model starts a new conversation, because each provider keeps the history in its own format.

## The API key

**Save**, next to the key field, stores it in the encrypted QGIS authentication database (`QgsAuthManager`). QGIS asks you to create a master password the first time. The key never goes to the QGIS settings, the logs, the recipes or an error message. Saving with the field blank deletes the stored key.

Without the authentication database, SIGMAI uses the provider's environment variable (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`) if you set it, or keeps the key in memory for this session only.

## What is sent to the provider

To answer, the model receives:
- the conversation and SIGMAI's instructions;
- what the tools return: layer and field names, reference system, counts, sample attribute values, file paths and audit reports;
- with **Model sees the map** on, a low-resolution PNG preview of each exported map (about 1,000 pixels wide).

Data files are never sent: the model has no tool that reads them. The chosen provider's data policy applies. For nothing to leave the machine, use a local model.

## What the model can do

Only SIGMAI's twenty MCP tools, through the same function that serves an external MCP client. Every command passes through:
- the closed catalog;
- the access mode you chose in the panel;
- the authorised folders and the per-session limits;
- the audit and the recipe.

In *ask before each write* mode, the consent dialog appears for each write, as usual.

The model cannot read files, run code or use the internet. A request it cannot fulfil with these tools gets an answer, not a workaround.

## Tokens and cost

The panel shows the tokens used in the conversation and, for Anthropic models, the cost estimated at list price, with the date of the price table. **Cap** stops the conversation when the estimate passes the amount (US$ 5 by default; 0 means no cap); **Continue anyway** lifts it for the rest of the conversation. Your provider's bill is the real figure.

What keeps the count down:
- **Summaries:** tool answers are summaries. The audit lists only the failed rules, each with the problem and the command that fixes it, and recipes omit the layer styles. A tool called with `detail: "full"` returns everything.
- **Caching:** SIGMAI's instructions and tool list are cached between requests.
- **Limits:** at most sixty tool calls per turn; **Stop** ends the turn after the current call.

## Logs

Each conversation is written to `<QGIS profile>/sigmai/logs/chat/<date-time>.jsonl`, without the key: messages, tool calls and results, model and tokens. **Export conversation** saves it as Markdown. The bridge keeps logging every command, as it does for any client.

## Test mode

To replay a session word for word, for example the example of the SIGMAI paper:
- `SIGMAI_CHAT_SCRIPT=<file.json>` holds a JSON list of messages;
- with `SIGMAI_CHAT_AUTORUN=1`, the chat opens and sends the messages one after the other;
- when it finishes, `<file>.done.json` holds the transcript, the tokens and the cost;
- in this mode the model is told that nobody answers questions;
- `SIGMAI_CHAT_COST_CAP` can raise the cost cap for the scripted run.

`SIGMAI_CHAT_TEST_URL` points the Anthropic provider at a server on `127.0.0.1`. Only the automated tests use it.
