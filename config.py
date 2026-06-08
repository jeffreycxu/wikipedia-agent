import os
from dotenv import load_dotenv

load_dotenv()

# Model settings
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TARGET_MODEL = "claude-sonnet-4-6"
JUDGE_MODEL = "claude-opus-4-7"

TEMPERATURE = 0.3

# Other settings
MAX_FETCHED_PAGES = 3
MAX_CONTENT_CHARS = 40_000
TOP_K_CHUNKS = 10
MAX_TOOL_CALLS = 5
WIKI_MAX_RETRIES = 3
WIKI_BACKOFF_BASE = 5          # seconds; non-429 retry backoff: 5s, 10s, 20s
WIKI_RATE_LIMIT_WAIT = 60      # seconds to wait after a 429 before retrying
WIKI_RATE_LIMIT_INTERVAL = 2.0  # minimum seconds between Wikipedia API requests
