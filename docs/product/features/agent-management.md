<!-- Updated: 2025-02-13 | Sprint: - | Tasks: - -->

# Agent Management

## Brief Description

A system for creating and managing AI agents, where each agent has a unique role, skill profile, and set of skills for completing tasks.

## User Value

**As** a project manager (boss),
**I want to** create specialized agents for different tasks,
**so that** I can efficiently distribute work across the team.

## Main Usage Scenarios

### Scenario 1: Creating a New Agent

1. Boss identifies the need for a new specialist
2. Boss describes the role, skills, and area of responsibility
3. HR creates the agent via `create_employee.py`
4. The agent appears in `employees.json`
5. The orchestrator immediately sees the new agent
6. Boss can assign the agent to tasks

### Scenario 2: Using Skills

1. Agent receives a task
2. Agent reads their skills from `.tayfa/{agent}/skills/`
3. Applies methodologies and templates from skills
4. Completes the task with higher quality

### Scenario 3: Choosing an Executor for a Task

1. Boss analyzes the task (type, complexity, required skills)
2. Reviews agent profiles
3. Selects the one with matching skills
4. Checks the agent's workload
5. Assigns to the task

## Agent Folder Structure

```
.tayfa/{agent_name}/
├── prompt.md          # Agent system prompt
├── profile.md         # Profile: skills, specialization
└── skills/            # Agent skills
    ├── SKILL-xxx.md
    └── SKILL-yyy.md
```

## Key Behavior

| Situation | System Behavior |
|-----------|-----------------|
| Agent creation | Folder + prompt.md + profile.md + registration in employees.json |
| Agent launch | Reads prompt.md, receives task, uses skills |
| Agent removal | Removal from employees.json (folder remains) |

## Agent Roles

| Agent | Model | Primary Role | Typical Tasks |
|-------|-------|--------------|---------------|
| boss | opus | Manager | Creating tasks, oversight, decision-making |
| analyst | sonnet | Requester | Detailing requirements, acceptance criteria |
| developer | sonnet | Developer | Writing code, implementing features |
| tester | haiku | Tester | Quality verification, bug reports |
| hr | sonnet | HR Manager | Creating new agents |
| process_architect | opus | Process Architect | Workflow optimization |

## Agent Models

| Model | Cost | Usage |
|-------|------|-------|
| **opus** | High | Strategic roles (boss, architect) — deep analysis |
| **sonnet** | Medium | Working roles (analyst, developer) — cost/quality balance |
| **haiku** | Low | Routine tasks (tester) — checklist-based work |

## Skills

### What Are Skills

`SKILL-*.md` files contain:
- Work methodologies
- Templates and checklists
- Best practices
- Step-by-step instructions

### Skill Examples

```
.tayfa/boss/skills/
├── SKILL-task-decomposer.md     # Task decomposition
├── SKILL-team-assignment.md     # Executor assignment
└── SKILL-project-tracking.md    # Progress tracking

.tayfa/process_architect/skills/
├── SKILL-process-design.md      # Process design
├── SKILL-agent-optimizer.md     # Agent optimization
└── SKILL-task-structure.md      # Task structure
```

### Usage Rule

An agent **must** use their skills when completing tasks. Skills contain proven methodologies that improve work quality.

## Constraints and Notes

- Agent registry: only `employees.json`
- New agents: only through `create_employee.py`
- Boss does not edit employees.json manually
- Each agent has a fixed model (opus/sonnet/haiku)

## Related Components

- `.tayfa/common/employees.json` — agent registry
- `.tayfa/common/employee_manager.py` — management CLI
- `.tayfa/hr/create_employee.py` — agent creation
- `.tayfa/{agent}/prompt.md` — system prompt
- `.tayfa/{agent}/profile.md` — profile
- `.tayfa/{agent}/skills/` — skills

## CLI Commands

```bash
# List agents
python .tayfa/common/employee_manager.py list

# Create agent
python .tayfa/hr/create_employee.py {name} --model sonnet
```

## Change History

| Date | Sprint | What Changed |
|------|--------|--------------|
| 2025-02-13 | - | Initial version. Added skills description |
