# Quick Guide: Creating Agents and Employee Skills

## How an Agent is Created in the Application

1. **Preparing the employee folder**
   In `Personel/<name>/` the following structure is created:
   - `prompt.md` — system prompt (role, instructions)
   - `profile.md` — profile: role, **skills**, area of responsibility
   - optionally `skills.md` — extended skill description
   - `tasks.md`, `notes.md`, `source.md`

2. **Registering the agent via API**
   A JSON is placed in `Personel/Request/` (or the orchestrator sends a request). You can explicitly specify **use_skills** — an array of skill names from the `Tayfa/skills/` folder (see below):
   ```json
   {
     "name": "employee_name",
     "system_prompt_file": "Personel/employee_name/prompt.md",
     "workdir": "/mnt/c/Cursor/Tayfa",
     "allowed_tools": "Read Edit Bash",
     "use_skills": ["project-decomposer"]
   }
   ```
   A **POST** is sent to `http://localhost:8788/run` **without a `prompt` field** — this is a request to create/update an agent.

3. **Assembling the system prompt**
   The orchestrator (or the API when called with `system_prompt_file`) during agent creation/update:
   - reads `Personel/<name>/prompt.md`;
   - reads `Personel/<name>/profile.md` and if present — `Personel/<name>/skills.md`;
   - inserts the "Skills" section from the profile (and from `skills.md`) into the prompt and passes the assembled text as the agent's system prompt.

4. **Who creates agents**
   New employees are onboarded by **HR**: creates the folder, fills in `prompt.md`, `profile.md` (including skills), optionally `skills.md`. Agent creation in the API is performed by the orchestrator based on this data. Only **boss** contacts **hr** with staffing requests.

---

## How to Properly Add Skills to Employees

- **Primary source of skills** — the **"## Skills"** section in `Personel/<name>/profile.md`.
  The orchestrator inserts it into the system prompt during agent creation/update.

- **Optionally** — a `Personel/<name>/skills.md` file for details (levels, checklists, references).
  If it exists, the orchestrator includes it as well. In `profile.md` in the "Skills" section you can write: "See skills.md".

- **Do not duplicate** the skill list in `prompt.md` — skills are taken only from `profile.md` and optionally from `skills.md`.

- **When to add/change skills:**
  1. **Onboarding** — HR fills in "Skills" in `profile.md` when creating an employee (and creates `skills.md` if needed)
  2. **Updating** — boss or hr assigns the task; the responsible person edits `profile.md` (and `skills.md` if needed).

- **Rules for HR and boss:**
  During onboarding, the "Skills" section in `profile.md` must be filled in. When a role or area of responsibility changes, skills in `profile.md` must also be updated.

After changing `profile.md` or `skills.md`, the next agent call (or prompt reassembly via API) will already use the updated skills — there is no need to "apply" them separately.

---

## Explicit Skill Attachment (Tayfa/skills)

All **Cursor Agent Skills** are stored in **Tayfa/skills/** — each subfolder (e.g. `project-decomposer`, `team-role-analyzer` or `public/pptx`) contains a `SKILL.md` file.

When creating an agent or sending a prompt through the orchestrator, you can specify which skills to attach to the agent:

```json
{
  "name": "developer_python",
  "prompt": "Create a presentation about our API architecture",
  "use_skills": ["public/pptx"]
}
```

When creating an agent, add a **use_skills** field to the JSON request — an array of identifiers (folder names in `Tayfa/skills/`). The orchestrator will read the corresponding `SKILL.md` files and add their content to the agent's system prompt. Nested paths are supported, e.g. `"public/pptx"` → `Tayfa/skills/public/pptx/SKILL.md`.
