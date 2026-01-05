---
description: Read Icarus Documentation
---

## Documentation Workflow

### Before Starting Any Work
1.  **Architecture Review**: Read `docs/architecture/` to understand system design, patterns, and constraints.
2.  **Implementation Context**: Check `docs/implementations/` for:
    *   Existing implementation plans
    *   Completed work and decisions made
    *   In-progress features and their status
3.  **Project Status**: Look for `docs/TODO.md`, `docs/STATUS.md`, or similar tracking documents.

### Documentation Directory Structure
*   `docs/architecture/`: High-level design, system patterns, key constraints
*   `docs/implementations/`: Implementation plans, feature designs, technical decisions
*   `docs/adr/` (if exists): Architectural Decision Records
*   `docs/api/` (if exists): API documentation and interfaces

### During Work
*   **Create Plans**: Write implementation plans in `docs/implementations/` before significant changes.
*   **Document Decisions**: Record architectural choices and rationale as you go.
*   **Update Status**: Keep TODO lists and status documents current.

### Before Ending Session
*   **Summarize Progress**: Update relevant documentation with what was completed.
*   **Document Blockers**: Note any issues, questions, or dependencies.
*   **Outline Next Steps**: Clear action items for the next session.

### Documentation Search Strategy
When unsure about functionality or patterns:
1.  Search `docs/` first for existing documentation
2.  Search codebase for actual implementations
3.  Check tests for usage examples
4.  **Never assume** - verify before implementing