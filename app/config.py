"""Runtime configuration — read once from the environment (.env)."""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/pageindex")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
# Only use a base URL if one is actually set. An empty ANTHROPIC_BASE_URL in the
# environment would otherwise be read by the SDK and break the request URL.
_base = os.getenv("ANTHROPIC_BASE_URL", "").strip()
ANTHROPIC_BASE_URL = _base or None
if not _base:
    os.environ.pop("ANTHROPIC_BASE_URL", None)
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "pageindex-sandbox")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "Page-Index-Demo contact@example.com")
