# How Cursor Agents Are Created in Tayfa Architecture

## Overview

Tayfa uses a **multi-agent orchestration system** where agents (Claude AI instances) are created and managed through a structured process. Unlike monolithic systems, each agent has:

- **Own folder** in `.tayfa/<agent_name>/`
- **Dedicated prompt** in `.tayfa/<agent_name>/prompt.md`
- **Chat history** in `.tayfa/<agent_name>/chat_history.json`
- **Configuration** in `.tayfa/common/employees.json`
- **Personal notes** in `.tayfa/<agent_name>/notes.md`

---

## 1. Agent Creation Workflow

### Step 1: HR Creates Employee

```bash
python .tayfa/hr/create_employee.py <name> [--model opus|sonnet|haiku]
```

**Example:**
```bash
python .tayfa/hr/create_employee.py developer_backend --model sonnet
python .tayfa/hr/create_employee.py architect --model opus
```

**What it does:**
- Creates `.tayfa/<name>/` directory
- Generates template files:
  - `source.md` — initial description
  - `profile.md` — role, responsibilities, skills
  - `prompt.md` — system prompt for Claude (template, HR fills in)
  - `notes.md` — history of employee onboarding

### Step 2: HR Fills in prompt.md

The generated `prompt.md` is a **template**. HR must customize it:

```markdown
# [Role Title]

You are **[name]**, [role] in this project.

## Your Role
[Describe role]

## Skills and Responsibilities
See `.tayfa/[name]/profile.md` for complete list.

## Base Rules
**MANDATORY**: Study `.tayfa/common/Rules/agent-base.md`

Additional team rules:
- `.tayfa/common/Rules/teamwork.md`
- `.tayfa/common/Rules/employees.md`

## Task System
Tasks are in `.tayfa/common/tasks.json`, managed via `.tayfa/common/task_manager.py`

## Working Directories
- **Project**: project root
- **Personal folder**: `.tayfa/[name]/`
```

**Key sections HR customizes:**
- Role description (what does this agent do?)
- Skills and responsibilities
- Specific guidelines for this agent
- Tools and commands available
- Communication protocols

### Step 3: Register in Employee Registry

The script automatically calls `employee_manager.register_employee()`:

```python
register_employee(
    name="developer_backend",
    role="Backend Developer",
    model="sonnet",
    fallback_model="",
    max_budget_usd=0.0,
    permission_mode="bypassPermissions",
    allowed_tools="Read Edit Write Bash"
)
```

This creates an entry in `.tayfa/common/employees.json`:

```json
{
  "employees": {
    "developer_backend": {
      "role": "Backend Developer",
      "model": "sonnet",
      "fallback_model": "",
      "max_budget_usd": 0.0,
      "permission_mode": "bypassPermissions",
      "allowed_tools": "Read Edit Write Bash",
      "created_at": "2026-02-18"
    }
  }
}
```

### Step 4: Notify Orchestrator to Create Agent

After prompt.md is ready, the orchestrator is notified:

```bash
curl -X POST http://localhost:8008/api/ensure-agents \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/path/to/project"}'
```

Or from UI: **"Ensure agents"** button (calls this API endpoint)

The orchestrator reads:
1. `.tayfa/common/employees.json` — agent configuration
2. `.tayfa/<agent_name>/prompt.md` — system prompt
3. `.tayfa/<agent_name>/chat_history.json` — previous messages (if any)

---

## 2. Agent Configuration

### employees.json Fields

| Field | Description | Example |
|-------|-------------|---------|
| `role` | Human-readable role | "Backend Developer" |
| `model` | Claude model: opus, sonnet, haiku | "sonnet" |
| `fallback_model` | Model to use if primary overloaded | "haiku" |
| `max_budget_usd` | API budget limit (0 = unlimited) | 5.0 |
| `permission_mode` | How to handle tool execution | "bypassPermissions" |
| `allowed_tools` | Space-separated tool list | "Read Edit Write Bash" |
| `created_at` | ISO date | "2026-02-18" |

### Available Tools

Each agent can be granted:
- **Read** — Read files and code
- **Edit** — Modify existing files
- **Write** — Create new files
- **Bash** — Execute terminal commands
- **Glob** — Pattern-based file search
- **Grep** — Code search in files

### Permission Modes

- `bypassPermissions` — Execute tools without asking
- `default` — Ask user for permission (interactive)
- `acceptEdits` — Auto-accept file edits
- `delegate` — Escalate decisions to boss
- `dontAsk` — Never use tools requiring permission
- `plan` — Plan-only mode (can't execute)

---

## 3. Agent Life Cycle

### 1. Idle State
- Agent is registered in `employees.json`
- Prompt is in `.tayfa/<agent_name>/prompt.md`
- No active task

### 2. Activated (Assigned a Task)
- Task system assigns task to this agent
- Orchestrator creates a session with the agent
- Agent loads:
  - System prompt from `prompt.md`
  - Task details from `.tayfa/common/tasks.json`
  - Discussion history from `.tayfa/common/discussions/{task_id}.md`
  - Previous chat history from `.tayfa/<agent_name>/chat_history.json`

### 3. Working (In Progress)
- Agent receives task
- Executes tools (Read, Edit, Write, Bash) as needed
- Communicates via discussion file
- Makes decisions within role scope

### 4. Handoff
- Agent updates task status: `in_progress` → `in_review`
- Records result in `.tayfa/common/task_manager.py result T001 "..."`
- Next agent (tester) is automatically assigned

### 5. Done
- Final tester marks task as `done`
- Task is archived
- Agent becomes idle again

---

## 4. Agent Types in Tayfa

### Built-in Agents (Always Present)

#### **boss** (Project Manager)
- Model: Opus (complex reasoning)
- Role: Coordinate tasks, make decisions, escalation point
- Cannot be removed

#### **hr** (HR Manager)
- Model: Sonnet
- Role: Employee management, prompts editing
- Cannot be removed

### Domain Agents (Configurable)

#### **developer** (Application Developer)
- Model: Opus
- Tools: Read, Edit, Write, Bash
- Role: Implement features, run tests
- **MUST**: Install deps, run code, run pytest before handoff

#### **tester** (QA Engineer)
- Model: Sonnet
- Tools: Read, Bash
- Role: Verify implementation against criteria
- **MUST**: Run `bash ./run_tests.sh` first

#### **reviewer** (Code Reviewer)
- Model: Haiku (lightweight)
- Tools: Read, Edit
- Role: Fast code review without execution

#### **devops** (DevOps Engineer)
- Model: Haiku
- Tools: Read, Edit, Write, Bash
- Role: CI/CD, scripts, automation

#### **tech_writer** (Documentation)
- Model: Haiku
- Tools: Read, Edit, Write
- Role: Docs, README, CHANGELOG

#### **analyst** (Requirements Analyst)
- Model: Sonnet
- Tools: Read
- Role: Detail requirements, define acceptance criteria
- Acts as "customer" in task system

#### **python_dev** (Senior Python Developer)
- Model: Opus
- Tools: Read, Edit, Write, Bash
- Role: Complex architecture and optimization

#### **agent_specialist** (AI Agent Researcher)
- Model: Opus
- Tools: Read, Bash (web research focused)
- Role: Research AI architectures, improve agent prompts

---

## 5. Creating a New Agent

### Full Process

```bash
# 1. Create employee folder structure
python .tayfa/hr/create_employee.py my_specialist --model opus

# 2. Edit the prompt
cat > .tayfa/my_specialist/prompt.md << 'EOF'
# My Specialist

You are **my_specialist**, a specialized AI agent for [domain].

## Your Role

[Describe what this agent does]

## Skills and Responsibilities

- [Skill 1]
- [Skill 2]

## Base Rules

**MANDATORY**: Study `.tayfa/common/Rules/agent-base.md`

Additional team rules:
- `.tayfa/common/Rules/teamwork.md`
- `.tayfa/common/Rules/employees.md`

## Task Workflow

[How this agent works in the task system]

## Tools

You have access to: Read, Edit, Write, Bash

[Tools guidelines]

## Communication

Use discussions: `.tayfa/common/discussions/{task_id}.md`
EOF

# 3. Update agent configuration (optional: more detailed permissions)
python .tayfa/common/employee_manager.py register my_specialist "My Specialist" \
  --model opus \
  --permission-mode bypassPermissions \
  --allowed-tools "Read Edit Write Bash"

# 4. Notify orchestrator to create agent
# From UI: click "Ensure agents" button
# Or via API:
curl -X POST http://localhost:8008/api/ensure-agents \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/path/to/project"}'
```

---

## 6. Agent Prompt Structure

### Minimal Prompt Template

```markdown
# [Agent Role]

You are **[agent_name]**, [role description].

## Your Responsibilities

- [What you do]
- [How you work]

## Base Rules

**MANDATORY**: Read `.tayfa/common/Rules/agent-base.md`
- Task system and workflows
- Communication protocols
- Execution requirements
- Working directories

## Rules for This Agent

### Tasks You Accept
- [Type 1]: [Description]
- [Type 2]: [Description]

### Tools You Have
- **Read**: Read code and documentation
- **Edit**: Modify existing files
- **Write**: Create new files
- **Bash**: Run terminal commands

### Decision Authority

You decide:
- [What you can decide independently]

You escalate (ask boss):
- [What needs approval]

## Communication

1. **Start**: Read `.tayfa/common/discussions/{task_id}.md` for context
2. **Work**: Use Read/Edit/Write/Bash tools as needed
3. **Document**: Add entries to discussion file
4. **Handoff**: Call `task_manager.py result` and `status` to transition

## Task System Commands

```bash
# View task
python .tayfa/common/task_manager.py get T001

# Record result
python .tayfa/common/task_manager.py result T001 "What you did"

# Update status
python .tayfa/common/task_manager.py status T001 in_progress
python .tayfa/common/task_manager.py status T001 in_review
```

## Code Execution is MANDATORY

**For developers**:
```bash
pip install -r requirements.txt
python kok/app.py
pytest kok/tests/
```

**For testers**:
```bash
bash ./run_tests.sh
```

Do NOT pass tasks without running the code.

## Questions & Decisions

**Forbidden**: Ask for clarification and wait.

**Required**: Make decisions within your role scope, document them, complete the task.

If your decision is wrong → tester will return the task.
```

---

## 7. Agent Communication Flow

### Task Assignment

```
boss creates task T001
    ↓
orchestrator reads employees.json
    ↓
finds "customer: analyst" → activates analyst
    ↓
analyst details requirements → sets status to in_progress
    ↓
analyst updates status to in_review
    ↓
orchestrator finds "developer: developer" → activates developer
    ↓
developer implements feature
    ↓
sets status to in_review
    ↓
orchestrator finds "tester: tester" → activates tester
    ↓
tester verifies → sets status to done
    ↓
task complete
```

### Discussion File (Central Communication Hub)

**Location**: `.tayfa/common/discussions/{task_id}.md`

**Format**:
```markdown
# Task discussion T001: Feature Title

## [2026-02-18 10:30] analyst (customer)

### Task description
[Initial requirements]

### Acceptance criteria
1. [Criterion 1]
2. [Criterion 2]

---

## [2026-02-18 10:45] developer (developer)

### Questions & Decisions
- Decided to use approach X instead of Y because [reason]

### Implementation plan
1. [Step 1]
2. [Step 2]

---

## [2026-02-18 11:20] developer (developer)

✅ Implementation complete
- [What was done]
- Ran: pytest, code verified working
- Ready for testing

---

## [2026-02-18 11:30] tester (tester)

### Test Results
✅ run_tests.sh passed
✅ API endpoints working
✅ Acceptance criteria met

Task PASSED.
```

---

## 8. Orchestrator Integration

The orchestrator (running on port 8008) handles:

1. **Agent Session Management**
   - Creates Claude AI sessions for each agent
   - Loads prompt from `.tayfa/<agent_name>/prompt.md`
   - Maintains chat history in `.tayfa/<agent_name>/chat_history.json`

2. **Task Routing**
   - Reads `.tayfa/common/tasks.json`
   - Determines next agent based on task status
   - Activates agent and provides task context

3. **File System Integration**
   - Agents can Read/Edit/Write files
   - Agents can Bash (limited by `allowed_tools`)
   - All operations logged

4. **Agent Lifecycle**
   - Ensures agents exist: `GET /api/ensure-agents`
   - Lists agents: `GET /api/agents`
   - Gets agent info: `GET /api/agents/<name>`
   - Activates agent: `POST /api/agents/<name>/activate`

---

## 9. API Endpoints

### Ensure Agents Exist

```bash
POST /api/ensure-agents
Content-Type: application/json

{
  "project_path": "/path/to/project"
}

Response: {
  "created": ["agent1", "agent2"],
  "updated": ["agent3"],
  "unchanged": ["agent4"],
  "errors": []
}
```

**Called by**: HR after filling in prompts, or "Ensure agents" UI button

### List Agents

```bash
GET /api/agents

Response: [
  {
    "name": "developer",
    "role": "Application Developer",
    "model": "opus",
    "tools": ["Read", "Edit", "Write", "Bash"],
    "status": "idle" | "active",
    "current_task": "T001" | null
  }
]
```

### Activate Agent for Task

```bash
POST /api/agents/developer/activate
Content-Type: application/json

{
  "task_id": "T001"
}

Response: {
  "agent": "developer",
  "task_id": "T001",
  "session_id": "sess_abc123",
  "started_at": "2026-02-18T10:30:00"
}
```

---

## 10. Employee Manager CLI

### List Employees

```bash
python .tayfa/common/employee_manager.py list

Output:
Employees (5):
  developer: Application Developer [opus] budget=$0.0 mode=bypassPermissions tools=Read,Edit,Write,Bash (since 2026-02-16)
  tester: QA Engineer [sonnet] budget=$0.0 mode=bypassPermissions tools=Read,Bash (since 2026-02-16)
  ...
```

### Register Employee

```bash
python .tayfa/common/employee_manager.py register my_agent "My Role" \
  --model opus \
  --fallback-model sonnet \
  --max-budget 5.0 \
  --permission-mode bypassPermissions \
  --allowed-tools "Read Edit Write Bash"
```

### Get Employee Info

```bash
python .tayfa/common/employee_manager.py get developer

Output:
{
  "role": "Application Developer",
  "model": "opus",
  "fallback_model": "",
  "max_budget_usd": 0.0,
  "permission_mode": "bypassPermissions",
  "allowed_tools": "Read Edit Write Bash",
  "created_at": "2026-02-16"
}
```

### Remove Employee

```bash
python .tayfa/common/employee_manager.py remove my_agent

Output: {
  "status": "removed",
  "name": "my_agent"
}

# Note: Cannot remove boss or hr
```

---

## 11. Key Design Principles

### 1. **Single Source of Truth**
- `.tayfa/common/employees.json` — agent config
- `.tayfa/<agent_name>/prompt.md` — agent system prompt
- `.tayfa/common/tasks.json` — all tasks

### 2. **No Manual Editing of JSON**
- Use CLI tools (`employee_manager.py`, `task_manager.py`)
- Never edit `.json` files directly

### 3. **Agents Are Stateless**
- Everything is on disk (prompt, history, tasks)
- Agent can be recreated from these files
- Easy to migrate or backup

### 4. **Clear Separation of Concerns**
- Each agent has a role and scope
- Agents communicate via discussion files
- Task system enforces workflow

### 5. **No Waiting**
- Agents **must not** ask for clarification
- **Mandatory**: Make decisions, document them, move forward
- If wrong → tester returns task

### 6. **Execution-First Culture**
- Developers **must** run code before handoff
- Testers **must** run tests before approval
- No theoretical verification

---

## 12. Troubleshooting

### Agent Not Created

```bash
# Check employees.json
cat .tayfa/common/employees.json

# Verify prompt.md exists
cat .tayfa/<agent_name>/prompt.md

# Ensure agents
curl -X POST http://localhost:8008/api/ensure-agents \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/path/to/project"}'
```

### Agent Has Old Prompt

1. Edit `.tayfa/<agent_name>/prompt.md`
2. Click "Ensure agents" or call API
3. Agent will reload new prompt on next task

### Remove and Recreate Agent

```bash
# 1. Remove from registry
python .tayfa/common/employee_manager.py remove my_agent

# 2. Remove folder
rm -rf .tayfa/my_agent

# 3. Recreate
python .tayfa/hr/create_employee.py my_agent --model sonnet

# 4. Edit prompt.md

# 5. Ensure agents
curl -X POST http://localhost:8008/api/ensure-agents ...
```

---

## 13. Advanced: Custom Agent for Specific Domain

### Example: Create "Database Specialist"

```bash
# 1. Create employee
python .tayfa/hr/create_employee.py db_specialist --model opus
```

### 2. Customize prompt.md

```markdown
# Database Specialist

You are **db_specialist**, database architecture and optimization expert.

## Your Role

- Design database schemas
- Optimize queries
- Migrate databases
- Write migration scripts
- Analyze performance

## Responsibilities

- **Accept**: Database design tasks, migration tasks, performance optimization
- **Refuse**: Frontend work, unrelated tasks
- **Escalate**: Major architectural decisions to python_dev

## Skills

- PostgreSQL, MySQL, SQLite
- Query optimization
- Migration strategies
- Schema design
- Indexing strategies

## Base Rules

Study `.tayfa/common/Rules/agent-base.md`

## Task Workflow

When assigned a DB task:
1. Read task in `.tayfa/common/tasks.json`
2. Check acceptance criteria in discussion file
3. Read existing database code in `kok/models/`
4. Propose changes in discussion file (ask for approval if major)
5. Implement: write migration files, update schema
6. Test: run migrations, verify data integrity
7. Set status to in_review

## Tools

- **Read**: Examine database code
- **Edit**: Modify schema files, add indexes
- **Write**: Create migration scripts
- **Bash**: Run psql, migrations, benchmarks

## Code Execution

For all DB tasks:
```bash
# Run migrations
alembic upgrade head

# Test data operations
python -c "from kok.models import *; ..."

# Benchmarks
python kok/tests/test_db_performance.py
```

Do NOT pass tasks without running migrations and testing.
```

### 3. Register with specific tools

```bash
python .tayfa/common/employee_manager.py register db_specialist "Database Specialist" \
  --model opus \
  --allowed-tools "Read Edit Write Bash"
```

### 4. Ensure agents

```bash
curl -X POST http://localhost:8008/api/ensure-agents ...
```

---

## Summary

The Tayfa agent creation system is:

| Aspect | Details |
|--------|---------|
| **Creation** | `python .tayfa/hr/create_employee.py <name>` |
| **Configuration** | Edit `.tayfa/<name>/prompt.md` |
| **Registry** | `.tayfa/common/employees.json` |
| **Activation** | Orchestrator reads config, creates Claude session |
| **Communication** | Via `.tayfa/common/discussions/{task_id}.md` |
| **Lifecycle** | idle → active (task assigned) → complete → idle |
| **Key Rule** | Execute code, don't just plan |

This design enables **flexible, reproducible, and auditable AI agent orchestration** within the Cursor platform.
