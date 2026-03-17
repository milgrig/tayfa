# Changelog

History of significant changes to the Tayfa product.

---

## [Unreleased]

### Added
- Discussion system `.tayfa/common/discussions/` — centralized place for task communication
- Mandatory handoff formats between stages (requester -> developer -> tester)
- Skills folder for each agent — methodologies and templates
- Product documentation `docs/product/`
- Documentation maintenance rules `product-docs.md`

### Changed
- Updated prompts for all agents with new handoff formats
- Updated `teamwork.md` rules



---

## [0.1.0] - Initial Version

### Added
- Task and sprint system with three roles
- Orchestrator (Web UI) on FastAPI
- Integration with Claude Code CLI
- Automatic git operations
- Agent management through employees.json
- Base agents: boss, hr, analyst, developer, tester, process_architect
- Team work rules (teamwork.md, employees.md, git-workflow.md)
- Skills for boss and process_architect

---

## Entry Format

Each entry follows the format:

```
## [Version] - Date

### Added
- New features

### Changed
- Changes to existing functionality

### Fixed
- Bugs

### Removed
- Removed functionality

### Security
- Security fixes
```
