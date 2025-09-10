# CollabTask Backend API

This service provides authentication and organization membership with FastAPI.

Endpoints:
- POST /auth/register: Register a new user, create an organization and membership. Returns JWT.
- POST /auth/login: Login with email and password. Returns JWT including active_org_id.
- GET /auth/me: Get current user profile, memberships, and active organization.
- POST /auth/orgs/switch: Switch the active organization (must be a member). Returns new JWT.

Environment:
- Copy .env.example to .env and set required variables:
  - JWT_SECRET (required)
  - JWT_ALGORITHM (default HS256)
  - JWT_EXPIRES_MINUTES (default 120)
  - POSTGRES_URL or POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB/POSTGRES_HOST/POSTGRES_PORT
  - CORS_ALLOW_ORIGINS

Security:
- Passwords are hashed (passlib[bcrypt]).
- JWT is signed with HS256 (PyJWT).

Database:
- asyncpg pool is used.
- On startup, minimal tables are created if missing: users, organizations, memberships.

Notes:
- Do not commit .env. Request these secrets from the environment orchestrator.
