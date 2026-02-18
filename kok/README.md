# Tayfa — Multi-Agent System on Claude Code

![Tests](https://github.com/milgrig/tayfa/workflows/Tests/badge.svg)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Overview

Tayfa is an AI agent system where each agent is an "employee" with its own role, memory, and working directory. Agents communicate through files and are managed via a single HTTP API.

**Stack**: Claude Code CLI (WSL) + FastAPI (uvicorn)

---

## Architecture

```
┌──────────────┐     POST /run      ┌─────────────────┐     claude CLI      ┌───────────┐
│ Orchestrator │ ──────────────────→ │  claude_api.py  │ ──────────────────→ │  Claude   │
│              │ ←────────────────── │  (FastAPI:8788) │ ←────────────────── │  Code     │
└──────────────┘     JSON response   └─────────────────┘     JSON result     └───────────┘
                                            │
                                            ▼
                                    ~/claude_agents.json
                                    (agent registry, session_id)
```

The file system is the primary means of communication between agents:

```
Tayfa/
  Personel/
    Rules/          — shared rules for all agents
    boss/           — manager
    hr/             — HR manager
    <name>/         — any employee's directory
      prompt.md     — system prompt (agent role)
```

---

## 1. Starting WSL

Claude Code runs inside WSL (Ubuntu). WSL is invoked from PowerShell:

```powershell
# Single command
wsl bash -c "command"

# With login shell (required for claude CLI installed via npm/nvm)
wsl bash -lc "command"
```

Windows paths in WSL:
- Paths are converted automatically: `C:\Path\To\Tayfa` → `/mnt/c/Path/To/Tayfa`

---

## 2. Setting Up uvicorn (Claude API Server)

### File Locations

| File | Path | Description |
|---|---|---|
| `claude_api.py` | `~/claude_api.py` (WSL home) | FastAPI application |
| `claude_run.sh` | `~/claude_run.sh` (WSL home) | Legacy script for `/run` without an agent |
| `claude_agents.json` | `~/claude_agents.json` (WSL home) | Agent registry (created automatically) |
| Virtual env | `~/claude_venv/` | Python venv with uvicorn and fastapi |

### Starting

```bash
# In WSL:
source ~/claude_venv/bin/activate
python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788
```

From PowerShell as a single command:
```powershell
wsl bash -lc "source ~/claude_venv/bin/activate && cd <WSL-path-to-Tayfa> && python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788"
```

### Logs

uvicorn writes logs to stderr. When starting via a script, you can redirect:
```powershell
$proc = Start-Process -FilePath "wsl" `
  -ArgumentList "bash", "-c", "`"source ~/claude_venv/bin/activate && cd <WSL-path-to-Tayfa> && python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788`"" `
  -PassThru -WindowStyle Hidden `
  -RedirectStandardOutput "claude-api.out.log" -RedirectStandardError "claude-api.err.log"
```

---

## 3. API — Working with Agents

All operations go through a single endpoint:

```
POST http://localhost:8788/run
Content-Type: application/json
```

### Create an Agent

```json
{
  "name": "developer_python",
  "system_prompt_file": "Personel/developer_python/prompt.md",
  "workdir": "<WSL-path-to-Tayfa>",
  "allowed_tools": "Read Edit Bash"
}
```

Response: `{"status": "created", "agent": "developer_python"}`

### Send a Task to an Agent

The agent remembers the conversation history (via session_id + `--resume`).

```json
{
  "name": "developer_python",
  "prompt": "Write a parser for CSV files"
}
```

Response:
```json
{
  "code": 0,
  "result": "Agent response text...",
  "session_id": "uuid",
  "cost_usd": 0.05,
  "is_error": false,
  "num_turns": 3
}
```

### Reset Agent Memory

Resets the conversation history. The system prompt and settings are preserved.

```json
{
  "name": "developer_python",
  "reset": true
}
```

### One-Off Request (Without an Agent)

No history, no system prompt.

```json
{
  "prompt": "What year is it now?"
}
```

### List Agents

```
GET http://localhost:8788/agents
```

### Delete an Agent

```
DELETE http://localhost:8788/agents/developer_python
```

---

## 4. How system_prompt_file Works

If an agent has a `system_prompt_file` specified, the prompt is read from the md file on **every** `/run` call. This means:

- You edited `prompt.md` → the next agent call already uses the new prompt.
- No need to recreate the agent.
- The path is relative to `workdir` (typically `<WSL-path-to-Tayfa>`).

---

## 5. How Agents Communicate with Each Other

Agents interact through a **task system** (`common/task_manager.py`). Boss creates a task specifying the assigner, developer, and tester. The Orchestrator runs the corresponding agent at each stage.


---

## 6. Cursor CLI via WSL

The Orchestrator can send requests not only to the Claude API but also to **Cursor CLI** (headless). In the interface, when selecting an agent, you can specify "Send to: Claude / Cursor". When Cursor is selected, the request is executed via WSL.

### Installing Cursor CLI in WSL

```bash
# In WSL:
curl https://cursor.com/install -fsSL | bash
# Add to PATH (in ~/.bashrc):
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
# Verify:
agent --version
```

For headless mode in scripts, an API key is needed: `export CURSOR_API_KEY=...` (see [Cursor documentation](https://cursor.com/docs/cli/headless)).

### Creating Chats (create-chat)

Before sending messages to Cursor, each agent needs its own chat. Command in WSL:

```bash
bash -lc 'export PATH="$HOME/.local/bin:$PATH"; cd <WSL-path-to-Tayfa>; agent --print --output-format json create-chat'
```

The response is a JSON with a `chat_id` field (or `session_id` / `id`). The Orchestrator saves the "agent → chat_id" mapping in `.cursor_chats.json` at the Tayfa root.

In the interface: the **"Create Cursor Chats (WSL)"** button calls `create-chat` for all agents with Cursor runtime and saves the chat_id. You can create a chat for a single agent: `POST /api/cursor-create-chat` with body `{ "name": "agent_name" }`.

### How Sending Works

The Orchestrator when sending to Cursor:

1. Takes or creates a chat for the agent (create-chat if no entry exists in `.cursor_chats.json`).
2. Composes a prompt with the role and assignment, writes it to `.cursor_cli_prompt.txt`.
3. Runs in WSL: `agent -p --force --resume <chat_id> --output-format json "$(cat .cursor_cli_prompt.txt)"` from the project directory.
4. Parses the response JSON, returns the `result` field to the chat, deletes the temporary file.

Call timeout: 600 s. The `agent` command must be in `PATH` in WSL (typically `~/.local/bin`).

---

## 7. Quick Reference

| Action | How |
|---|---|
| Start API | `wsl bash -lc "source ~/claude_venv/bin/activate && cd <WSL-path-to-Tayfa> && python -m uvicorn claude_api:app --app-dir ~ --host 0.0.0.0 --port 8788"` |
| Create an agent | `POST /run` with `name` + `system_prompt_file` (without `prompt`) |
| Task to agent (Claude) | `POST /run` with `name` + `prompt` |
| Task to agent (Cursor CLI) | `POST /api/send-prompt-cursor` with `name` + `prompt` (uses agent's chat, create-chat if needed) |
| Create Cursor chat for agent | `POST /api/cursor-create-chat` with `{ "name": "agent" }` |
| Create Cursor chats for all | `POST /api/cursor-create-chats` |
| List Cursor chats | `GET /api/cursor-chats` |
| Reset memory | `POST /run` with `name` + `reset: true` |
| List agents | `GET /agents` |
| Delete an agent | `DELETE /agents/<name>` |
| Agent registry | `~/claude_agents.json` (WSL) |
| Agent rules | `<path-to-Tayfa>\Personel\Rules\` |
