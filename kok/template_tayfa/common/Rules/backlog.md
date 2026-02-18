# Backlog

**Backlog** — storage for ideas and future tasks. Intermediate step between idea and formal sprint task.

## Main Commands

```bash
# View
python .tayfa/common/backlog_manager.py list
python .tayfa/common/backlog_manager.py list --priority high

# Add
python .tayfa/common/backlog_manager.py add "Idea title" \
  --description "Description" \
  --priority medium

# Mark for sprint
python .tayfa/common/backlog_manager.py toggle B001

# View marked
python .tayfa/common/backlog_manager.py next-sprint

# Remove
python .tayfa/common/backlog_manager.py remove B001
```

## Priorities

| Priority | When to use |
|----------|-------------|
| **high** | Business critical, user requested |
| **medium** | Useful, not urgent |
| **low** | Nice to have, can defer |

## Workflow

1. Employee adds idea to backlog
2. Boss reviews and prioritizes
3. Boss marks items with `next_sprint` flag
4. When creating sprint — items become tasks

## Data File

`.tayfa/common/backlog.json`
