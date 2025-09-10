# CollabTask Backend API

This service provides authentication and organization membership with FastAPI.

Endpoints:
- POST /auth/register: Register a new user, create an organization and membership. Returns JWT.
- POST /auth/login: Login with email and password. Returns JWT including active_org_id.
- GET /auth/me: Get current user profile, memberships, and active organization.
- POST /auth/orgs/switch: Switch the active organization (must be a member). Returns new JWT.
- POST /uploads/project (multipart/form-data): Upload file and attach to a project (fields: project_id, file)
- POST /uploads/task (multipart/form-data): Upload file and attach to a task (fields: task_id, file)
- POST /billing/checkout-session: Create Stripe checkout session (JSON: price_id, success_url, cancel_url)
- POST /billing/customer-portal: Create Stripe customer portal link (JSON: return_url)
- POST /billing/webhook: Stripe webhooks receiver

Environment:
- Copy .env.example to .env and set required variables:
  - JWT_SECRET (required)
  - JWT_ALGORITHM (default HS256)
  - JWT_EXPIRES_MINUTES (default 120)
  - POSTGRES_URL or POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB/POSTGRES_HOST/POSTGRES_PORT
  - CORS_ALLOW_ORIGINS
  - STRIPE_API_KEY (required for billing endpoints)
  - STRIPE_WEBHOOK_SECRET (optional for verifying webhooks)
  - STRIPE_BILLING_PORTAL_CONFIG_ID (optional)

Security:
- Passwords are hashed (passlib[bcrypt]).
- JWT is signed with HS256 (PyJWT).

Database:
- asyncpg pool is used.
- On startup, minimal tables are created if missing: users, organizations, memberships.

Notes:
- Do not commit .env. Request these secrets from the environment orchestrator.
