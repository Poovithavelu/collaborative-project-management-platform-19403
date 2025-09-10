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
  - GITHUB_CLIENT_ID (required for GitHub OAuth)
  - GITHUB_CLIENT_SECRET (required for GitHub OAuth)
  - GITHUB_OAUTH_CALLBACK_URL (optional; override inferred callback URL, e.g., https://api.example.com/github/callback)
  - GITHUB_OAUTH_SCOPE (optional; default: "repo read:org user:email")
  - SITE_URL (optional; used to redirect after successful GitHub connection)

Security:
- Passwords are hashed (passlib[bcrypt]).
- JWT is signed with HS256 (PyJWT).

Database:
- asyncpg pool is used.
- On startup, minimal tables are created if missing: users, organizations, memberships.

Notes:
- Do not commit .env. Request these secrets from the environment orchestrator.

GitHub Integration:
- GET /github/connect (auth required): Redirects to GitHub to authorize access. Stores a CSRF 'state'.
- GET /github/callback: Handles GitHub redirect, verifies 'state', exchanges 'code' for access token, and stores it per-organization.

Database tables created:
- github_oauth_states(state, user_id, org_id, created_at, consumed)
- github_tokens(org_id, access_token, token_type, scope, gh_user_login, gh_user_id, created_at, updated_at)

Security:
- Access tokens are stored server-side per organization, not returned to clients. The 'state' parameter prevents CSRF.
