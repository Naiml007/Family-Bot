# AGENTS.md — <PROJECT NAME>

> Guidance for AI coding agents working in THIS repo. Loaded automatically.
> Keep concise, imperative, evergreen. Update when commands/conventions change.
> README.md is for humans; this file is for agents.

## 1. Project Overview
- **What it is:** <one sentence>
- **Primary language / runtime:** <e.g. Python 3.12>
- **Entry point:** <path>

## 2. Tech Stack
- Frameworks: <e.g. discord.py, aiosqlite>
- Tooling: <ruff, mypy, pytest>
- Services / infra: <e.g. SQLite, Docker>

## 3. Commands (copy-pasteable)
```bash
# Install
<install cmd>
# Run
<run cmd>
# Test (all)
<test cmd>
# Test (single)
<single test cmd>
# Lint
<lint cmd>
# Type check
<typecheck cmd>
# Format
<format cmd>
```
> Agents MUST run lint + typecheck + tests before declaring work done.

## 4. Architecture & Layout
```
<dir tree with one-line purpose per entry>
```
- **Composition root:** <where wiring happens>
- **Data flow:** <request → service → db, etc.>

## 5. Code Conventions
- Style: <formatter, line length>
- Naming: <conventions>
- Errors: <how to raise/handle>
- No module-global singletons; inject dependencies.
- All SQL parameterized. No secrets in code/logs.

## 6. Domain Glossary
| Term | Meaning |
|------|---------|
| <term> | <definition> |

## 7. Agent Roles, Personas & Responsibilities
> Assign ownership so parallel agents don't collide. Each task names ONE owning role.

| Role / Persona | Responsibilities | Owns (paths) | Hands off to |
|----------------|------------------|--------------|--------------|
| **Architect** | Design, spec, task breakdown; no production code | `docs/`, `agents.md` | Implementer |
| **Implementer** | Write code + tests per task | `src/**` | Reviewer |
| **Reviewer** | Correctness, conventions, security pass | — (reviews) | Implementer |
| **Test / QA** | Test strategy, coverage gate, CI | `tests/**`, CI | Implementer |
| **Security** | Auth, input validation, secrets, deps | — (audits) | Implementer |
| **Docs** | README, runbooks, changelog | `*.md` | Architect |

**Handoff rules:** Implementer → Reviewer after green checks; Reviewer → Implementer with
actionable notes; never two agents editing the same path concurrently.

## 8. Guardrails (Do NOT)
- Do not commit secrets or `.env`.
- Do not add a dependency for a few lines; prefer stdlib/existing.
- Do not bypass lint/type/test gates.
- Do not edit files outside your role's `Owns` without Architect approval.

## 9. Definition of Done
- [ ] Lint + typecheck + tests green
- [ ] New logic has a test
- [ ] No secrets, no commented-out code
- [ ] Docs updated if behavior changed