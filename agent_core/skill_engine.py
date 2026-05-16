"""
SkillEngine — indexes 400+ skills and matches the best ones to every request.

Strategy
--------
1. On first call to load(), parse every SKILL.md under skills_dir.
2. Build a keyword set per skill: slug tokens + description tokens + trigger
   phrases extracted from "When to Use" / "Trigger" / "Use when" sections.
3. At query time, score each skill by keyword overlap + slug/trigger boosts.
4. Return top-N skills above a confidence threshold.
5. Cache the index to skills_dir/_skill_index.json — rebuilt automatically
   whenever any SKILL.md is newer than the cache.

Usage
-----
    from agent_core.skill_engine import SkillEngine
    engine = SkillEngine(r"C:\\path\\to\\Skills")
    engine.load()                           # parse + cache (fast on re-runs)
    matches = engine.match("write a python script", top_n=3)
    for m in matches:
        print(m.slug, m.score, m.description[:60])
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Stop-words — filtered out before keyword matching
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "as", "by", "is", "it", "its", "that", "this", "are",
    "was", "were", "be", "been", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can", "not",
    "from", "use", "when", "how", "what", "which", "who", "you", "your",
    "any", "all", "if", "then", "than", "so", "also", "more", "other",
    "into", "just", "about", "after", "before", "between", "through",
    "only", "both", "each", "such", "get", "set", "new", "add", "make",
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SkillEntry:
    """Internal representation of a single indexed skill."""
    slug: str
    name: str
    description: str
    keywords: list[str]           # deduplicated, sorted keyword tokens
    trigger_phrases: list[str]    # short phrases from "When to Use" sections
    path: str


@dataclass
class SkillMatch:
    """A skill returned by match() with its relevance score."""
    slug: str
    name: str
    description: str
    score: float                  # 0.0 – 1.0
    path: str


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class SkillEngine:
    """
    Build and query a keyword index over a directory of SKILL.md files.

    Thread safety: load() is not thread-safe; call it once at startup before
    spawning request-handling threads.
    """

    INDEX_FILENAME = "_skill_index.json"
    INDEX_VERSION  = 2  # bump when index schema changes

    def __init__(self, skills_dir: str) -> None:
        self.skills_dir  = os.path.normpath(skills_dir)
        self._skills: list[SkillEntry] = []
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, force_rebuild: bool = False) -> int:
        """
        Load the skill index.

        Tries the JSON cache first; rebuilds from disk if the cache is
        missing, outdated, or force_rebuild is True.

        Returns the number of skills indexed.
        """
        if not os.path.isdir(self.skills_dir):
            return 0

        index_path = os.path.join(self.skills_dir, self.INDEX_FILENAME)

        if not force_rebuild and self._try_load_cache(index_path):
            self._loaded = True
            return len(self._skills)

        self._build_index()
        self._save_cache(index_path)
        self._loaded = True
        return len(self._skills)

    def match(
        self,
        query: str,
        top_n: int = 5,
        min_score: float = 0.12,
    ) -> list[SkillMatch]:
        """
        Return up to top_n SkillMatch objects most relevant to query.

        Scores each skill by:
          - keyword overlap ratio   (primary signal)
          - slug-word match boost   (+0.30 when slug words appear in query)
          - trigger phrase boost    (+0.25 when a trigger phrase is a substring)

        Skills scoring below min_score are excluded.
        """
        if not self._loaded:
            self.load()
        if not self._skills or not query:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_lower = query.lower()

        scored: list[tuple[float, SkillEntry]] = []
        for entry in self._skills:
            score = self._score(query_tokens, query_lower, entry)
            if score >= min_score:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            SkillMatch(
                slug=entry.slug,
                name=entry.name,
                description=entry.description,
                score=round(score, 3),
                path=entry.path,
            )
            for score, entry in scored[:top_n]
        ]

    def skill_count(self) -> int:
        """Number of skills currently indexed."""
        return len(self._skills)

    def rebuild(self) -> int:
        """Force a full rebuild of the index from disk."""
        return self.load(force_rebuild=True)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score(
        self,
        query_tokens: set[str],
        query_lower: str,
        entry: SkillEntry,
    ) -> float:
        kw_set = set(entry.keywords)

        # Primary: fraction of query tokens that appear in skill keywords
        overlap = len(query_tokens & kw_set) / max(len(query_tokens), 1)

        # Boost: slug tokens directly present in query
        slug_tokens = set(_tokenize(entry.slug))
        slug_boost  = 0.30 if (slug_tokens and slug_tokens & query_tokens) else 0.0

        # Boost: trigger phrase appears as substring of query
        trigger_boost = 0.0
        for phrase in entry.trigger_phrases:
            if phrase and phrase.lower() in query_lower:
                trigger_boost = 0.25
                break

        return min(overlap + slug_boost + trigger_boost, 1.0)

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        self._skills = []
        for root, dirs, files in os.walk(self.skills_dir):
            # Skip internal files / hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith(("_", "."))]
            for fname in files:
                if fname != "SKILL.md":
                    continue
                path  = os.path.join(root, fname)
                entry = self._parse_skill(path)
                if entry:
                    self._skills.append(entry)
        self._skills.sort(key=lambda e: e.slug)

    def _parse_skill(self, path: str) -> Optional[SkillEntry]:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            return None

        slug        = os.path.basename(os.path.dirname(path))
        name        = slug
        description = ""
        body        = content

        # Parse YAML frontmatter
        if content.startswith("---"):
            fm_end = content.find("---", 3)
            if fm_end != -1:
                fm      = content[3:fm_end]
                body    = content[fm_end + 3:]
                name_m  = re.search(r"^name:\s*(.+)$",        fm, re.MULTILINE)
                desc_m  = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)

                if name_m:
                    name = name_m.group(1).strip().strip('"\'')

                if desc_m:
                    raw = desc_m.group(1).strip()
                    # Handle YAML block scalars (">", "|", etc.) — read first body line
                    if raw in (">", "|", "|-", ">-", ">+", "|+"):
                        for line in body.strip().splitlines():
                            line = line.strip()
                            if line and not line.startswith("#"):
                                description = line.strip('"\'')
                                break
                    else:
                        description = raw.strip('"\'')

        # Extract trigger phrases from "When to Use" / "Trigger" sections
        trigger_phrases = _extract_trigger_phrases(body)

        # Build keyword set
        keywords = _build_keywords(slug, name, description, trigger_phrases, body)

        return SkillEntry(
            slug=slug,
            name=name,
            description=description,
            keywords=keywords,
            trigger_phrases=trigger_phrases,
            path=path,
        )

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _try_load_cache(self, index_path: str) -> bool:
        """
        Load from JSON cache if it's still fresh.

        Freshness check: cache mtime must be newer than every SKILL.md.
        Returns True on success, False if a rebuild is needed.
        """
        if not os.path.isfile(index_path):
            return False
        try:
            with open(index_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return False

        if data.get("version") != self.INDEX_VERSION:
            return False

        cache_mtime = os.path.getmtime(index_path)
        for root, dirs, files in os.walk(self.skills_dir):
            dirs[:] = [d for d in dirs if not d.startswith(("_", "."))]
            for fname in files:
                if fname == "SKILL.md":
                    if os.path.getmtime(os.path.join(root, fname)) > cache_mtime:
                        return False

        self._skills = [
            SkillEntry(
                slug             = s["slug"],
                name             = s["name"],
                description      = s["description"],
                keywords         = s["keywords"],
                trigger_phrases  = s.get("trigger_phrases", []),
                path             = s["path"],
            )
            for s in data.get("skills", [])
        ]
        return bool(self._skills)

    def _save_cache(self, index_path: str) -> None:
        try:
            data = {
                "version"    : self.INDEX_VERSION,
                "built_at"   : time.time(),
                "skills_dir" : self.skills_dir,
                "count"      : len(self._skills),
                "skills"     : [
                    {
                        "slug"            : e.slug,
                        "name"            : e.name,
                        "description"     : e.description,
                        "keywords"        : e.keywords,
                        "trigger_phrases" : e.trigger_phrases,
                        "path"            : e.path,
                    }
                    for e in self._skills
                ],
            }
            with open(index_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except OSError:
            pass  # Cache write failure is non-fatal


# ---------------------------------------------------------------------------
# Helpers (module-level so tests can import them directly)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """
    Lowercase, split on non-alphanumeric boundaries, remove stop-words.
    Tokens shorter than 3 characters are discarded.
    """
    tokens = re.findall(r"[a-z][a-z0-9]*", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def _extract_trigger_phrases(body: str) -> list[str]:
    """
    Pull bullet-point items from 'When to Use', 'Trigger', 'Use when'
    markdown sections in the skill body.
    """
    pattern = re.compile(
        r"(?:##?\s*(?:When\s+to\s+Use|Triggers?|Use\s+when|Invoke\s+when|"
        r"Primary\s+use|Trigger\s+on|Use\s+for)[^\n]*\n)(.*?)(?=\n##|\Z)",
        re.S | re.I,
    )
    phrases: list[str] = []
    for match in pattern.finditer(body):
        section = match.group(1)
        bullets = re.findall(r"[-*•]\s*(.+)", section)
        for b in bullets[:12]:
            phrase = b.strip()[:100]
            if phrase:
                phrases.append(phrase)
    return phrases


def _build_keywords(
    slug: str,
    name: str,
    description: str,
    trigger_phrases: list[str],
    body: str,
) -> list[str]:
    """
    Aggregate keyword tokens from all available signal sources.
    Returns a sorted, deduplicated list.
    """
    tokens: set[str] = set()

    # Slug tokens — highest signal (e.g., "python-builder" → "python", "builder")
    for part in re.split(r"[-_]", slug):
        if len(part) >= 3:
            tokens.add(part.lower())
    tokens.update(_tokenize(slug))

    # Name and description
    tokens.update(_tokenize(name))
    tokens.update(_tokenize(description))

    # Trigger phrases
    for phrase in trigger_phrases:
        tokens.update(_tokenize(phrase))

    # Body excerpt (first 1500 chars of Markdown after frontmatter, headers only)
    headers = re.findall(r"^#{1,3}\s+(.+)$", body[:2000], re.MULTILINE)
    for hdr in headers:
        tokens.update(_tokenize(hdr))

    # Remove short tokens (re-check after set operations)
    tokens = {t for t in tokens if len(t) >= 3}

    return sorted(tokens)


# ---------------------------------------------------------------------------
# Module-level singleton helper
# ---------------------------------------------------------------------------

_DEFAULT_ENGINE: Optional[SkillEngine] = None


def get_default_engine() -> Optional[SkillEngine]:
    """Return the module-level default engine (None until init_default() called)."""
    return _DEFAULT_ENGINE


def init_default(skills_dir: str) -> SkillEngine:
    """
    Initialise (or re-initialise) the module-level default engine.
    Called once at server startup by the OrchestratorAgent.
    """
    global _DEFAULT_ENGINE
    _DEFAULT_ENGINE = SkillEngine(skills_dir)
    _DEFAULT_ENGINE.load()
    return _DEFAULT_ENGINE
