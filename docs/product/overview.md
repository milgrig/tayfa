<!-- Updated: 2025-02-13 | Sprint: - | Tasks: - -->

# Tayfa — Multi-Agent Orchestration System

## What It Is

Tayfa is a framework for managing a team of AI agents that work as virtual employees. Each agent has its own role, skills, and area of responsibility. Agents coordinate through a task and sprint system, communicate in a structured format, and automatically commit results to Git.

## Core Concept

AI agents operate following a real development team model:
- **Boss** — project manager, creates tasks and assigns executors
- **Analyst** — details requirements, writes acceptance criteria
- **Developer** — implements features
- **Tester** — verifies quality

## Key Features

### 1. Agent Team Management
- Creating new agents through an HR process
- Each agent has a profile, skills, and a system prompt
- Agents specialize in different roles

### 2. Task and Sprint System
- All tasks are linked to sprints
- Three roles in each task: requester -> developer -> tester
- Statuses: pending -> in_progress -> in_review -> done
- Dependencies between tasks

### 3. Structured Communication
- Task discussions in files `.tayfa/common/discussions/{task_id}.md`
- Mandatory handoff formats between stages
- Clear acceptance criteria and test cases

### 4. Git Automation
- Automatic commits on task status changes
- Branches for sprints (`sprint/S001`)
- Automatic merge and tags on finalization

### 5. Orchestrator (Web UI)
- Visual task board (kanban by sprints)
- Launch agents with a button click
- Project management

## Architecture

```
Tayfa2/
├── kok/                          # Orchestrator code
│   ├── app.py                    # FastAPI application
│   ├── claude_api.py             # Claude CLI integration
│   ├── git_manager.py            # Git operations
│   ├── task_manager.py           # (copy for orchestrator)
│   └── static/                   # Web UI
│
├── .tayfa/                       # Team folder
│   ├── common/                   # Shared resources
│   │   ├── tasks.json            # Central task database
│   │   ├── employees.json        # Agent registry
│   │   ├── discussions/          # Task discussions
│   │   ├── archive/              # Completed sprint archive
│   │   ├── Rules/                # Work rules
│   │   └── task_manager.py       # CLI for task management
│   │
│   ├── boss/                     # Manager
│   │   ├── prompt.md
│   │   ├── profile.md
│   │   └── skills/
│   │
│   ├── analyst/                  # Analyst
│   ├── developer/                # Developer
│   ├── tester/                   # Tester
│   └── ...                       # Other agents
│
└── docs/product/                 # Product documentation
```

## Target Audience

- Developers using AI assistants for automation
- Teams experimenting with multi-agent systems
- AI orchestration researchers

## Technologies

- **Backend**: Python, FastAPI
- **AI**: Claude Code CLI (Anthropic)
- **Storage**: JSON files (tasks, employees)
- **VCS**: Git (automatic integration)
- **Frontend**: HTML/JS (static)

## Related Documents

- [[features/task-system]] — task and sprint system
- [[features/agent-management]] — agent management
- [[features/discussions]] — agent communication
- [[features/git-integration]] — Git automation
