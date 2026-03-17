# Sprint Archival

## Purpose

After sprint completion, data is archived:
- **Agents DO NOT see** archived data (to keep context clean)
- **User CAN access** when needed (history preserved)

---

## Structure

```
.tayfa/
├── common/
│   ├── tasks.json          ← active tasks and sprints
│   └── archive/            ← completed sprint archive
│       ├── S001/
│       │   ├── sprint.json     ← sprint data
│       │   ├── tasks.json      ← sprint tasks (snapshot)
│       │   └── summary.md      ← summary (optional)
│       ├── S002/
│       └── ...
```

---

## Archival Process

### When Archived

Sprint is archived **automatically** when "Finalize sprint" task completes:
1. All sprint tasks have status `done` or `cancelled`
2. Finalizing task moves to `done`
3. Release performed (merge, tag, push)
4. **→ Sprint archived**

### What Happens

1. **Archive folder created**: `.tayfa/common/archive/S001/`

2. **Sprint snapshot saved**: `sprint.json`
   ```json
   {
     "id": "S001",
     "title": "Name",
     "status": "completed",
     "version": "v0.1.0",
     "released_at": "2025-01-15T12:00:00",
     "created_by": "boss"
   }
   ```

3. **Sprint tasks saved**: `tasks.json`

4. **Removed from main tasks.json**:
   - Sprint tasks removed
   - Sprint removed from list
   - `next_id` and `next_sprint_id` NOT reset (IDs stay unique)

---

## Rules for Agents

### ⛔ Agents DO NOT access archive

```
FORBIDDEN for agents:
- Reading files from .tayfa/common/archive/
- Using archived data in work
- Referencing archived tasks
```

**Why:** Archive is history for humans. Agents work only with active tasks.

### ✅ Agents work only with active data

```
ALLOWED for agents:
- Reading .tayfa/common/tasks.json (active tasks)
- Using task_manager.py list/get/status/result
```

---

## User Access

User can anytime:

### View archived sprints
```bash
ls .tayfa/common/archive/
# S001  S002  S003
```

### View specific sprint data
```bash
cat .tayfa/common/archive/S001/sprint.json
cat .tayfa/common/archive/S001/tasks.json
```

### Restore sprint (if needed)
Manual restore: copy data back to `tasks.json`.

---

## CLI Commands

```bash
# View archived sprints
python .tayfa/common/task_manager.py archived

# View specific archived sprint
python .tayfa/common/task_manager.py archived S001
```

---

## Summary

| Aspect | Description |
|--------|-------------|
| **When** | Automatically on sprint finalization |
| **Where** | `.tayfa/common/archive/S00X/` |
| **What** | sprint.json + tasks.json |
| **Agents** | NO access |
| **User** | Full access via filesystem |
| **IDs** | Stay unique (not reused) |
