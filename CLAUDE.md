# CLAUDE.md

This file provides guidance for AI assistants (Claude and others) working in this repository.

## Project Overview

**Repository**: `jrgrafisk/ambrotos`

> This repository is in initial setup. Update this section as the project takes shape, describing its purpose, core functionality, and target users.

## Repository Structure

> Document the directory layout here as the project grows. Example:
>
> ```
> ambrotos/
> ├── src/           # Main source code
> ├── tests/         # Test suites
> ├── docs/          # Documentation
> └── scripts/       # Build and utility scripts
> ```

## Development Setup

> Add setup instructions here. Include prerequisites, installation steps, and environment configuration.

### Prerequisites

- List required tools and runtimes
- List required environment variables

### Installation

```bash
# Example — replace with actual steps
git clone <repo-url>
cd ambrotos
# install dependencies
```

### Environment Variables

Document required environment variables in `.env.example` and list critical ones here.

## Build and Run

> Replace with actual commands once the build system is established.

```bash
# Build
# Run
# Start dev server
```

## Testing

> Document the test framework, how to run tests, and what coverage targets exist.

```bash
# Run all tests
# Run a specific test
# Run with coverage
```

### Test Conventions

- Tests live adjacent to source files or in a top-level `tests/` directory (decide and document this)
- Test file naming convention: `*.test.<ext>` or `*_test.<ext>` (choose one)
- All new features require corresponding tests
- Do not commit with failing tests

## Code Style and Conventions

> Fill in language-specific conventions once the tech stack is decided.

### General

- Keep functions small and focused; prefer composition over deep nesting
- Prefer explicit over implicit; avoid magic values — use named constants
- Write self-documenting code; add comments only where logic is non-obvious
- Delete dead code rather than commenting it out

### Naming

- Use descriptive names; avoid abbreviations except well-known ones (`id`, `url`, `ctx`)
- Consistent casing per language conventions (e.g., `snake_case` for Python, `camelCase` for JS/TS)

### Error Handling

- Handle errors explicitly; do not swallow exceptions silently
- Validate at system boundaries (user input, external APIs); trust internal code

## Git Workflow

### Branches

- `main` — stable, production-ready code; protected
- `claude/<description>-<session-id>` — AI-assisted feature branches
- Feature branches: `feat/<short-description>`
- Bug fixes: `fix/<short-description>`

### Commit Messages

Use the imperative mood and keep the subject line under 72 characters:

```
<type>: <short summary>

[Optional body explaining the why, not the what]
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `build`, `ci`

Examples:
```
feat: add user authentication middleware
fix: prevent null pointer in session handler
docs: update setup instructions in CLAUDE.md
```

### Pull Requests

- Keep PRs small and focused on a single concern
- Include a description of what changed and why
- Link related issues
- All CI checks must pass before merging

## CI/CD

> Document pipelines here once configured (GitHub Actions, CircleCI, etc.).

Expected checks per PR:
- Lint
- Type check (if applicable)
- Tests
- Build

## Security

- Never commit secrets, credentials, or API keys — use environment variables
- Add sensitive file patterns to `.gitignore`
- Validate and sanitize all external input
- Keep dependencies up to date; audit regularly

## Dependencies

> List critical dependencies and their purpose here once the project has them. For each:
> - What it does
> - Why it was chosen over alternatives
> - Any important configuration or usage notes

## Adding New Features

1. Create a feature branch from `main`
2. Write tests first (or alongside the implementation)
3. Implement the feature following existing conventions
4. Ensure all tests pass and linting is clean
5. Open a PR with a clear description

## Common Pitfalls

> Document gotchas, non-obvious behaviors, or past mistakes here as the project evolves.

## Updating This File

Keep CLAUDE.md current as the project evolves:
- When the tech stack is chosen, fill in build/test/lint commands
- When directory structure stabilizes, document it
- When new conventions are adopted, record them here
- When gotchas are discovered, add them to Common Pitfalls
