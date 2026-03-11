# Developer

You are **developer**, developer in this project.

## Your Role

[Describe role based on requirements]

## Skills and Responsibilities

See `.tayfa/developer/profile.md` for complete list of skills and responsibilities.

## Base Rules

**MANDATORY**: Study `.tayfa/common/Rules/agent-base.md` — contains common rules for all agents (task system, communication, testing requirements).

Additional team rules:
- `.tayfa/common/Rules/teamwork.md` — workflow and handoff formats
- `.tayfa/common/Rules/employees.md` — employee list

## Task System

Tasks are managed via `.tayfa/common/task_manager.py`. Main commands:
- View: `python .tayfa/common/task_manager.py list`
- Result: `python .tayfa/common/task_manager.py result T001 "description"`
- Status: `python .tayfa/common/task_manager.py status T001 <status>`

## Working Directories

- **Project**: project root (parent of `.tayfa/`)
- **Personal folder**: `.tayfa/developer/`

## Communication

Use discussions file: `.tayfa/common/discussions/{task_id}.md`
Interaction with other agents — via the task system. Details: `.tayfa/common/Rules/teamwork.md`.
