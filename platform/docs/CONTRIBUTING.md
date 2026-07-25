# Contributing Guide

## Getting Started

1. Read the [Development Guide](./DEVELOPMENT.md)
2. Understand the [Architecture](./ARCHITECTURE.md)
3. Follow the coding standards

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

| Type       | Description                    |
| ---------- | ------------------------------ |
| `feat`     | New feature                    |
| `fix`      | Bug fix                        |
| `docs`     | Documentation only             |
| `style`    | Formatting, whitespace         |
| `refactor` | Code change (no feature/fix)   |
| `perf`     | Performance improvement        |
| `test`     | Adding/fixing tests            |
| `build`    | Build system or dependencies   |
| `ci`       | CI configuration               |
| `chore`    | Maintenance tasks              |
| `revert`   | Revert a previous commit       |

### Scopes

Use the package name without `@aira/` prefix: `types`, `config`, `api`, `web`, `database`, etc.

### Examples

```
feat(api): add user registration endpoint
fix(web): resolve theme toggle not persisting
docs(config): update environment variable reference
test(security): add JWT token verification tests
```

## Pull Request Process

1. Create a feature branch from `develop`
2. Make your changes following coding standards
3. Write/update tests (minimum 80% coverage)
4. Ensure all CI checks pass: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
5. Create PR targeting `develop`
6. Request review from at least one team member
