"""Project-wide constants. One place for all tunable numbers.

Named per coding-standards: no magic numbers scattered in logic.
Values are grouped by subsystem with rationale in comments.
"""

# ---- LLM providers ------------------------------------------------------

# Quick health-check probes when auto-detecting which backend is running.
LLM_PROBE_TIMEOUT_SECONDS = 1.5

# Generation calls. Local models are slower than cloud, give them room.
LLM_LOCAL_REQUEST_TIMEOUT_SECONDS = 120
LLM_CLOUD_REQUEST_TIMEOUT_SECONDS = 60

# Default sampling. Temperature 0 for planning/classification (determinism),
# higher for chat to feel natural.
LLM_CHAT_TEMPERATURE = 0.7
LLM_PLAN_TEMPERATURE = 0.0
LLM_CHAT_MAX_TOKENS = 600
LLM_PLAN_MAX_TOKENS = 400
LLM_CLASSIFY_MAX_TOKENS = 150
LLM_NARRATE_MAX_TOKENS = 400

# ---- Orchestrator / memory ---------------------------------------------

# How many turns of conversation to keep in context. Larger = more context,
# more tokens per call. 20 = roughly a 5-minute back-and-forth.
CONVERSATION_HISTORY_LIMIT = 20

# Slice of history sent to planner/dispatcher so follow-ups like "yes do it"
# work without ballooning the prompt.
HISTORY_WINDOW_FOR_PLANNING = 6

# Short-term rolling buffer of interactions kept in memory.
SHORT_MEMORY_CAPACITY = 25

# Minimum cosine similarity to consider a long-memory entry relevant.
# Low threshold because bag-of-words cosine scores are always small.
LONG_MEMORY_SIMILARITY_THRESHOLD = 0.1
LONG_MEMORY_DEFAULT_TOP_K = 3

# ---- Automation scheduler ---------------------------------------------

# Poll interval when checking workflow conditions.
SCHEDULER_TICK_INTERVAL_SECONDS = 10.0

# ---- Tool behavior ----------------------------------------------------

# HIGH-mode scan guard: stop after this many files so a huge tree doesn't OOM.
SCAN_HIGH_MODE_FILE_CAP = 500

# How many bytes to preview per file in HIGH mode.
SCAN_PREVIEW_BYTES = 200
SCAN_PREVIEW_DISPLAY_CHARS = 100

# read_file cap - big enough for most text files, small enough to keep
# LLM context manageable.
READ_FILE_MAX_BYTES = 100_000

# ---- Web search -------------------------------------------------------

WEB_SEARCH_TIMEOUT_SECONDS = 10
WEB_SEARCH_DEFAULT_MAX_RESULTS = 5

# ---- Voice ------------------------------------------------------------

VOICE_LISTEN_TIMEOUT_SECONDS = 5.0
VOICE_PHRASE_TIME_LIMIT_SECONDS = 10.0
VOICE_AMBIENT_NOISE_DURATION_SECONDS = 0.5

# ---- MCP (Model Context Protocol) ------------------------------------

# How long to wait for a server to respond during initial connect / tool list.
# Node-based servers (npx) can take a few seconds to spin up.
MCP_CONNECT_TIMEOUT_SECONDS = 30

# Per-call timeout. Most tool calls are fast; give generous headroom for
# servers that hit external APIs (GitHub, filesystem scans, etc.).
MCP_CALL_TIMEOUT_SECONDS = 60
