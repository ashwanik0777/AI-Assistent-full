# Deployment Guide

## Environments

| Environment  | Purpose                        | Database              |
| ------------ | ------------------------------ | --------------------- |
| Development  | Local development              | Local PostgreSQL      |
| Testing      | CI/CD automated testing        | Ephemeral containers  |
| Staging      | Pre-production validation      | Managed PostgreSQL    |
| Production   | Live platform                  | Managed PostgreSQL    |

## Docker Deployment

### Build Images

```bash
# Build API image
docker build -f docker/api.Dockerfile -t aira-api:latest .

# Build Web image
docker build -f docker/web.Dockerfile -t aira-web:latest .
```

### Environment Variables

All required environment variables are documented in `.env.example`. In production:

- Use a secrets manager (AWS Secrets Manager, Vault, etc.)
- Never commit `.env` files
- Rotate `JWT_SECRET` regularly
- Use strong, unique `DATABASE_URL` credentials

## Database Migrations

### Development

```bash
pnpm db:migrate
```

### Production

```bash
npx prisma migrate deploy
```

Always review generated migration SQL before applying to production.

## Health Checks

| Endpoint         | Purpose           | Expected Response |
| ---------------- | ----------------- | ----------------- |
| `GET /health`    | General health    | `200 OK`          |
| `GET /health/ready` | Readiness probe | `200 OK`          |
| `GET /health/live`  | Liveness probe  | `200 OK`          |
