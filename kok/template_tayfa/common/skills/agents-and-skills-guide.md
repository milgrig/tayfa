# Quick Guide: Agent Creation and Employee Skills

## How an agent is created

1. **Prepare employee folder**
   In `.tayfa/<name>/` the following structure is created:
   - `prompt.md` — system prompt (role, instructions)
   - `profile.md` — profile: role, **skills**, responsibilities
   - optionally `skills.md` — extended skill descriptions
   - `notes.md`, `source.md`

2. **Register agent via API**
   The orchestrator sends a request. You can specify **use_skills** — an array of skill names from `.tayfa/common/skills/`:
   ```json
   {
     "name": "employee_name",
     "system_prompt_file": ".tayfa/employee_name/prompt.md",
     "workdir": "C:/Cursor/TayfaWindows",
     "allowed_tools": "Read Edit Bash",
     "use_skills": ["project-decomposer"]
   }
   ```
   Sent as **POST** to `http://localhost:8788/run` **without `prompt` field** — this is a create/update request.

3. **System prompt assembly**
   The orchestrator (or API when called with `system_prompt_file`) on agent create/update:
   - reads `.tayfa/<name>/prompt.md`;
   - reads `.tayfa/<name>/profile.md` and if present — `.tayfa/<name>/skills.md`;
   - injects the "Skills" block from profile (and from `skills.md`) into the prompt and passes the assembled text as system prompt.

4. **Who creates agents**
   New employees are onboarded by **HR**: creates folder, fills `profile.md` (including skills), optionally `skills.md`, and registers in `employees.json`. Agent creation in API is handled by the orchestrator. Only **boss** contacts **hr** about staffing.

---

## How to properly add skills to employees

- **Primary skill source** — the **"## Skills"** section in `.tayfa/<name>/profile.md`.
  The orchestrator injects it into the system prompt on agent create/update.

- **Optionally** — file `.tayfa/<name>/skills.md` for detailed descriptions (levels, checklists, references).
  If present, the orchestrator injects it too. In `profile.md` Skills block you can write: "See skills.md".

- **Do not duplicate** skill list in `prompt.md` — skills are taken only from `profile.md` and optionally `skills.md`.

- **When to add/change skills:**
  1. **Onboarding** — HR fills "Skills" in `profile.md` (and optionally creates `skills.md`) based on role description.
  2. **Update** — boss or hr assigns update task; responsible person edits `profile.md` (and optionally `skills.md`).

- **Rules for HR and boss:**
  On onboarding, always fill the "Skills" section in `profile.md`. On role or responsibility changes, update skills in `profile.md` too.

After changing `profile.md` or `skills.md`, the next agent call (or prompt rebuild via API) will use updated skills automatically.

---

## Explicit skill attachment (skills/)

All **Agent Skills** are stored in `.tayfa/common/skills/` — each subfolder (e.g. `project-decomposer`) contains a `SKILL.md` file.

When creating an agent or sending a prompt via orchestrator, you can specify which skills to attach:

```json
{
  "name": "developer_python",
  "prompt": "Create a presentation about our API architecture",
  "use_skills": ["public/pptx"]
}
```

Add the **use_skills** field — an array of skill identifiers (folder names). The orchestrator reads corresponding `SKILL.md` files and appends their content to the agent's system prompt. Nested paths are supported, e.g. `"public/pptx"` → `skills/public/pptx/SKILL.md`.
