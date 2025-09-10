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
  - OPENAI_API_KEY (required for /ai/complete endpoint)
  - OPENAI_MODEL (optional; default "gpt-4o-mini")

Security:
- Passwords are hashed (passlib[bcrypt]).
- JWT is signed with HS256 (PyJWT).

AI Assistant:
- POST /ai/complete (auth required)
  Request JSON example:
    {
      "prompt": "Draft an update summary for the latest sprint",
      "project_id": "uuid-optional",
      "task_id": "uuid-optional",
      "stream": false,
      "model": "optional model override"
    }
  Behavior:
  - Uses JWT active_org_id to enforce org-level access.
  - Validates project_id/task_id belong to the active organization and to each other when both provided.
  - Pulls project/task summaries (plus recent tasks for the project) to provide context to the model.
  - Calls OpenAI using OPENAI_API_KEY and returns the completion.
  - When "stream": true, the endpoint returns text/plain with incremental chunks (simple plain text streaming).

Environment for AI:
- OPENAI_API_KEY must be set in environment (do not commit).
- Optional OPENAI_MODEL to set default model; can be overridden per request via the "model" field.

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

AI Assistant:
- POST /ai/complete (auth required)
  Request JSON:
    {
      "prompt": "string",
      "project_id": "uuid-optional",
      "task_id": "uuid-optional",
      "stream": false,
      "model": "optional model override"
    }
  Behavior:
  - Uses JWT active_org_id to enforce org-level access.
  - If project_id is provided, validates it belongs to active org and includes project summary in context.
  - If task_id is provided, validates it belongs to active org (and project if provided), includes task summary.
  - Calls OpenAI using OPENAI_API_KEY and returns completion.
  - When "stream": true, returns text/plain with incremental chunks (simple plain text streaming).
  Response (non-stream): { "content": "...", "model": "gpt-4o-mini", "project_id": "...", "task_id": "..." }

Environment:
- Ensure OPENAI_API_KEY is set in the environment (do not commit to repository).
- Optional OPENAI_MODEL to set default model; can be overridden per-request via "model".
