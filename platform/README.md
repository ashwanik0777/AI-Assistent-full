# AIRA Platform

> **Artificial Intelligent Responsive Assistant** — Enterprise AI Platform

[![CI](https://github.com/your-org/aira-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/aira-platform/actions/workflows/ci.yml)

## Architecture

AIRA v1.5 Final — Frozen architecture with federated runtime, compliance governance, and multi-region support.

## Quick Start

### Prerequisites

- **Node.js** ≥ 20.0.0
- **pnpm** ≥ 9.0.0
- **Docker** & **Docker Compose**

### Setup

```bash
# Clone and enter the platform directory
cd platform

# Install dependencies
pnpm install

# Copy environment configuration
cp .env.example .env

# Start infrastructure (PostgreSQL, Redis)
pnpm docker:up

# Generate Prisma client
pnpm db:generate

# Run database migrations
pnpm db:migrate

# Seed the database
pnpm db:seed

# Start development servers (API + Web)
pnpm dev
```

### Access Points

| Service       | URL                          |
| ------------- | ---------------------------- |
| Frontend      | http://localhost:3000         |
| API           | http://localhost:3001         |
| API Docs      | http://localhost:3001/docs    |
| Health Check  | http://localhost:3001/health  |
| Prisma Studio | `pnpm db:studio`             |

## Project Structure

```
platform/
├── apps/
│   ├── api/          # NestJS backend
│   └── web/          # Next.js frontend
├── packages/
│   ├── api-client/   # Typed HTTP client
│   ├── config/       # Environment & feature flags
│   ├── constants/    # Shared constants & enums
│   ├── database/     # Prisma ORM & repositories
│   ├── logger/       # Structured logging (pino)
│   ├── security/     # JWT, hashing, sanitisation
│   ├── testing/      # Test utilities & factories
│   ├── types/        # Shared TypeScript types
│   ├── utils/        # Common utility functions
│   └── validation/   # Zod schemas & validators
├── docker/           # Docker & Compose configs
├── docs/             # Documentation
└── .github/          # CI/CD workflows
```

## Scripts

| Command             | Description                        |
| ------------------- | ---------------------------------- |
| `pnpm dev`          | Start all dev servers              |
| `pnpm build`        | Build all packages and apps        |
| `pnpm test`         | Run all tests                      |
| `pnpm lint`         | Lint all packages                  |
| `pnpm typecheck`    | Type-check all packages            |
| `pnpm format`       | Format all files                   |
| `pnpm docker:up`    | Start Docker infrastructure        |
| `pnpm docker:down`  | Stop Docker infrastructure         |
| `pnpm db:migrate`   | Run database migrations            |
| `pnpm db:seed`      | Seed the database                  |
| `pnpm db:studio`    | Open Prisma Studio                 |

## Tech Stack

| Layer      | Technology                     |
| ---------- | ------------------------------ |
| Frontend   | Next.js, React, Tailwind CSS   |
| Backend    | NestJS, Express                |
| Database   | PostgreSQL, Prisma             |
| Cache      | Redis                          |
| Monorepo   | Turborepo, pnpm workspaces     |
| Testing    | Vitest, Supertest              |
| CI/CD      | GitHub Actions                 |
| Container  | Docker, Docker Compose         |
| Validation | Zod                            |
| Auth       | JWT (jose)                     |
| Logging    | pino                           |

## License

UNLICENSED — Proprietary
