# Development Guide

## Environment Setup

### 1. Install Node.js

Use [nvm](https://github.com/nvm-sh/nvm) to manage Node versions:

```bash
nvm install 20
nvm use 20
```

### 2. Install pnpm

```bash
corepack enable
corepack prepare pnpm@10.14.0 --activate
```

### 3. Install Dependencies

```bash
cd platform
pnpm install
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your local settings
```

### 5. Start Infrastructure

```bash
pnpm docker:up
```

This starts PostgreSQL and Redis containers.

### 6. Setup Database

```bash
pnpm db:generate   # Generate Prisma client
pnpm db:migrate    # Apply migrations
pnpm db:seed       # Seed initial data
```

### 7. Start Development

```bash
pnpm dev
```

This starts both the API (port 3001) and web frontend (port 3000) with hot reload.

---

## Coding Standards

### TypeScript

- **Strict mode** enabled globally
- Use `type` imports: `import type { Foo } from './foo';`
- No `any` — use `unknown` and type narrowing
- All functions must have explicit return types
- Use `const` assertions where applicable

### Naming Conventions

| Element       | Convention       | Example              |
| ------------- | ---------------- | -------------------- |
| Files         | kebab-case       | `user-service.ts`    |
| Classes       | PascalCase       | `UserService`        |
| Interfaces    | PascalCase       | `UserRepository`     |
| Types         | PascalCase       | `CreateUserDto`      |
| Functions     | camelCase        | `findUserById`       |
| Constants     | SCREAMING_SNAKE  | `MAX_RETRY_COUNT`    |
| Enums         | PascalCase       | `UserRole`           |
| DB Tables     | snake_case       | `refresh_tokens`     |

### Git Workflow

- **Conventional Commits** enforced via commitlint
- Branches: `feat/`, `fix/`, `chore/`, `docs/`
- All PRs require passing CI checks

### Testing

- Unit tests alongside source: `*.spec.ts` or `*.test.ts`
- Integration tests in `__tests__/` directories
- Minimum 80% coverage target
- Use factories from `@aira/testing` for test data

---

## Monorepo Architecture

### Package Dependencies

```
@aira/types        ← no internal deps (leaf package)
@aira/constants    ← no internal deps (leaf package)
@aira/validation   ← no internal deps
@aira/utils        ← no internal deps
@aira/config       ← types, validation
@aira/logger       ← types
@aira/security     ← types, config
@aira/api-client   ← types, constants
@aira/database     ← types, logger
@aira/testing      ← types
@aira/api          ← types, config, logger, constants, security, validation
@aira/web          ← types, constants, api-client
```

### Adding a New Package

1. Create directory under `packages/`
2. Add `package.json` with `@aira/` scope
3. Add `tsconfig.json` extending `../../tsconfig.base.json`
4. Add source files under `src/`
5. Export from `src/index.ts`
6. Run `pnpm install` from root to link

### Turborepo Caching

Builds are cached by Turborepo. To clear cache:

```bash
pnpm clean
```
