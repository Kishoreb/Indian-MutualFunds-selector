"""
name_match.py
-------------
Fallback matching of mutual fund scheme NAMES, for the places where the toolkit has to tie two differently
written names to one scheme:

    * a name printed on your CDSL statement  <->  the scheme in AMFI's NAVAll.txt      (mf_holdings_screener.py)
    * the title of an AMC portfolio sheet     <->  a scheme from the AMFI scheme master  (portfolio_quality.py)

The existing exact / difflib matching always runs FIRST and is unchanged. This module is only asked when that
found nothing, or (screener only) to double-check an ISIN match whose name looks like a different fund.

HOW A FALLBACK MATCH IS DECIDED (every step must pass; nothing is guessed)
  1. Canonical form: lower case, scheme code prefix printed by CDSL removed ('8184- ...'), brackets removed,
     '&' -> 'and', 'mid cap' -> 'midcap' (same for small / large / flexi / multi), letters and digits split
     ('midcap150' -> 'midcap 150'), plan words (direct, growth, option, regular, idcw, fund, scheme ...) dropped.
  2. Similarity of the two canonical names. Two kinds, the first always available, the second optional:
       * character n-gram cosine (pure python, no model, no download). Copes with glued words that the statement
         prints ('NIPPON INDIANIFTY MIDCAP 150'), reordering, hyphenation and truncation.
       * a sentence-embedding model (sentence-transformers, which runs on PyTorch) loaded from a LOCAL folder.
         Used only if the library and the model folder exist; otherwise the module says so once and carries on
         with the n-gram similarity. The model folder is config.NAME_EMBED_MODEL (default models/name-embedder).
  3. Guard: even a high similarity is refused when the names carry conflicting facts. Embeddings and n-grams both
     see 'Axis Small Cap Fund' and 'Axis Mid Cap Fund' as nearly identical, and a wrong scheme means a wrong NAV
     history and a wrong verdict. A match is refused if
        * both names have words the other lacks (each side names something the other does not), or
        * a word the names disagree on is a number or a category/type word (small / mid / large / index / etf /
          liquid / gold / nifty ...), or
        * fewer than two words are shared.
  4. The best candidate must lead the runner-up that also passes the guard by a margin, and two candidates with the
     same canonical name make the match ambiguous (refused).
A match made this way is always labelled 'verify' by the caller and never silently trusted like an ISIN match.

SETTINGS (optional; read from config.py when present, else these defaults)
    NAME_EMBED_ENABLED      True    set False to switch the whole fallback off
    NAME_EMBED_MODEL        'models/name-embedder'   local folder holding a sentence-transformers model
    NAME_FALLBACK_MIN       0.80    minimum similarity for a fallback match
    NAME_FALLBACK_MARGIN    0.04    minimum lead over the runner-up
    NAME_CONFLICT_MAX       0.55    ISIN-vs-name check: below this similarity (and guard failed) the two names are
                                    treated as DIFFERENT schemes; at or above it the difference is only noted
The default numbers were checked against the 75 holdings of one real CDSL statement and their AMFI names (see
test_name_match.py); they are starting points for your own data, not industry constants.

Not investment advice and not a substitute for checking the ISIN.
"""

import difflib
import math
import os
import re
import sys
from collections import Counter

try:                                    # settings are optional so the module also works on its own
    import config as _config
except Exception:                       # pragma: no cover - config missing or broken
    _config = None

DEFAULTS = {
    "NAME_EMBED_ENABLED": True,
    "NAME_EMBED_MODEL": "models/name-embedder",
    "NAME_FALLBACK_MIN": 0.80,
    "NAME_FALLBACK_MARGIN": 0.04,
    "NAME_CONFLICT_MAX": 0.55,
}


def setting(name):
    return getattr(_config, name, DEFAULTS[name]) if _config is not None else DEFAULTS[name]


# ---------------------------------------------------------------------------------------------------------
# Canonical form
# ---------------------------------------------------------------------------------------------------------
PLAN_WORDS = {"direct", "plan", "growth", "option", "regular", "idcw", "dividend", "payout", "reinvestment",
              "cumulative", "fund", "funds", "scheme", "the", "an", "a", "open", "ended", "mutual", "of", "ltd",
              "limited", "erstwhile", "formerly", "previously", "segregated", "portfolio"}
_CODE_PREFIX = re.compile(r"^\s*[A-Z0-9]{1,6}(?:\s[A-Z0-9]{1,5})?\s*-\s*(?=\S)")
_CAP = re.compile(r"\b(small|mid|large|flexi|multi)[\s\-]*cap\b")
_ALNUM_SPLIT = re.compile(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])")

# words that name WHAT a fund is. If two names differ on one of these they are different funds.
CRITICAL = {
    "smallcap", "midcap", "largecap", "flexicap", "multicap", "elss", "tax", "saver", "focused", "value", "contra",
    "dividend", "yield", "liquid", "overnight", "gilt", "debt", "bond", "hybrid", "balanced", "arbitrage", "index",
    "etf", "fof", "nifty", "sensex", "bse", "nse", "momentum", "quality", "low", "vol", "volatility", "alpha",
    "equal", "weight", "infrastructure", "banking", "financial", "pharma", "healthcare", "technology", "tech",
    "digital", "consumption", "manufacturing", "psu", "gold", "silver", "commodities", "international", "global",
    "nasdaq", "emerging", "aggressive", "conservative", "savings", "retirement", "children", "short", "long",
    "medium", "duration", "ultra", "money", "market", "corporate", "credit", "floating", "fixed", "maturity",
    "series", "sdl", "gsec", "asset", "allocation", "multi", "next", "midcap150", "bluechip", "esg", "dynamic",
    "advantage", "thematic", "sectoral", "energy", "auto", "automotive", "services", "export",
    "mnc", "growth", "equity", "income", "interval", "target", "maturity",
}
CRITICAL -= {"growth", "equity"}        # 'growth' is a plan word; 'equity' appears in many ordinary names


_GLUED_PLAN = ("growth", "direct", "option")


def _strip_glued_plan_words(tok):
    for w in _GLUED_PLAN:
        if tok.endswith(w) and len(tok) - len(w) >= 3:
            return tok[:-len(w)]
        if tok.startswith(w) and len(tok) - len(w) >= 3:
            return tok[len(w):]
    return tok


def canon(name, strip_code=True) -> str:
    s = str(name or "")
    if strip_code:
        s = _CODE_PREFIX.sub("", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = _CAP.sub(r"\1cap", s)
    s = _ALNUM_SPLIT.sub(" ", s)
    return " ".join(_strip_glued_plan_words(t) for t in s.split() if t not in PLAN_WORDS)


def tokens(name, strip_code=True):
    return canon(name, strip_code).split()


# ---------------------------------------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------------------------------------
def _grams(text, ns=(3, 4)):
    """Character n-grams of the name with the spaces removed, so 'INDIASMALLCAP' and 'India Small Cap' look alike."""
    squashed = text.replace(" ", "")
    c = Counter()
    for n in ns:
        for i in range(len(squashed) - n + 1):
            c[squashed[i:i + n]] += 1
    return c


def _cos(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def ngram_similarity(a, b, strip_code_a=True, strip_code_b=False) -> float:
    """Character n-gram cosine of two names in canonical form (0..1)."""
    return _cos(_grams(canon(a, strip_code_a)), _grams(canon(b, strip_code_b)))


# ---------------------------------------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------------------------------------
def _same_token(x, y) -> bool:
    if x == y:
        return True
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    if len(short) >= 3 and long_.startswith(short) and not (short.isdigit() or long_.isdigit()):
        return True                                       # pru / prudential
    if any(ch.isdigit() for ch in x + y):
        return False                                      # numbers must match exactly
    return difflib.SequenceMatcher(None, x, y).ratio() >= 0.86


def _is_critical(tok) -> bool:
    return tok in CRITICAL or any(ch.isdigit() for ch in tok)


def _deglue(ta, tb):
    """Splits a token of `ta` that is exactly two or more consecutive tokens of `tb` run together
    ('indiasmallcap' -> 'india', 'smallcap'); the statement prints some names without the space."""
    out = []
    for t in ta:
        if t in tb or len(t) < 6:
            out.append(t)
            continue
        split = None
        for i in range(len(tb)):
            acc = ""
            for j in range(i, len(tb)):
                acc += tb[j]
                if acc == t and j > i:
                    split = tb[i:j + 1]
                    break
                if not t.startswith(acc):
                    break
            if split:
                break
        out.extend(split or [t])
    return out


def guard(a, b, strip_code_a=True, strip_code_b=False):
    """(ok, reason) - may these two names be the same scheme? Does not look at similarity."""
    ta, tb = tokens(a, strip_code_a), tokens(b, strip_code_b)
    ta, tb = _deglue(ta, tb), _deglue(tb, ta)
    ta, tb = [t for t in ta if len(t) > 1], [t for t in tb if len(t) > 1]      # single letters are initials / OCR noise
    if not ta or not tb:
        return False, "empty name"
    rest_b = list(tb)
    only_a = []
    shared = 0
    for x in ta:
        hit = next((i for i, y in enumerate(rest_b) if _same_token(x, y)), None)
        if hit is None:
            only_a.append(x)
        else:
            shared += 1
            rest_b.pop(hit)
    only_b = rest_b
    if only_a and only_b and "".join(only_a) != "".join(only_b):
        glued = difflib.SequenceMatcher(None, "".join(only_a), "".join(only_b)).ratio() >= 0.86
        if not glued:                                     # 'blue chip' vs 'bluechip' is the same word
            return False, f"each name has words the other lacks: {' '.join(only_a)} / {' '.join(only_b)}"
    odd = [t for t in only_a + only_b if _is_critical(t)]
    if odd:
        glued = only_a and only_b and difflib.SequenceMatcher(None, "".join(only_a), "".join(only_b)).ratio() >= 0.86
        if not glued:
            return False, "names differ on: " + " ".join(odd)
    if shared < 2:
        return False, "fewer than two words in common"
    return True, ""


def compare(a, b, strip_code_a=True, strip_code_b=False, embedder=None):
    """Everything the callers need about two names: {similarity, guard_ok, reason, severity}.
    severity: 'none' (same scheme as far as the names go), 'mild' (names differ but are similar: could be a rename),
    'severe' (names point to different schemes). Used to double-check an ISIN match against the printed name."""
    sim = ngram_similarity(a, b, strip_code_a, strip_code_b)
    if embedder is not None and embedder.available():
        sim = max(sim, embedder.similarity(canon(a, strip_code_a), canon(b, strip_code_b)))
    ok, reason = guard(a, b, strip_code_a, strip_code_b)
    if ok:
        severity = "none"
    elif sim < setting("NAME_CONFLICT_MAX"):
        severity = "severe"
    else:
        severity = "mild"
    return {"similarity": sim, "guard_ok": ok, "reason": reason, "severity": severity}


# ---------------------------------------------------------------------------------------------------------
# Optional sentence-embedding model (PyTorch, local folder only)
# ---------------------------------------------------------------------------------------------------------
class Embedder:
    """Wraps a sentence-transformers model stored in a local folder. Never downloads anything. If the library or
    the folder is missing, available() is False and `reason` says why; callers then use the n-gram similarity."""

    def __init__(self, path=None, model=None):
        self.path = path if path is not None else setting("NAME_EMBED_MODEL")
        self._model, self.reason, self._cache = model, "", {}
        self._tried = model is not None

    def _load(self):
        if self._tried:
            return
        self._tried = True
        path = self.path
        if not path or not os.path.isdir(path):
            self.reason = f"model folder '{path}' not found"
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(path, device="cpu")
        except Exception as exc:
            self.reason = f"could not load the model in '{path}' ({type(exc).__name__}: {str(exc)[:80]})"
            self._model = None

    def available(self) -> bool:
        self._load()
        return self._model is not None

    def vectors(self, texts):
        """L2-normalised vectors for texts (list of str) -> numpy array."""
        import numpy as np
        self._load()
        todo = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if todo:
            vecs = np.asarray(self._model.encode(todo, convert_to_numpy=True, show_progress_bar=False), dtype=float)
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            vecs = vecs / np.where(norms > 0, norms, 1.0)
            for t, v in zip(todo, vecs):
                self._cache[t] = v
        return np.vstack([self._cache[t] for t in texts])

    def similarity(self, a, b) -> float:
        v = self.vectors([a, b])
        return float(max(0.0, min(1.0, (v[0] * v[1]).sum())))


_DEFAULT = {"embedder": None, "warned": False}


def default_embedder(log=None):
    """The embedder named in the settings, created once. Returns None when the feature is switched off or the
    model cannot be used (a single note is printed, once, so you know the neural part is not running)."""
    if not setting("NAME_EMBED_ENABLED"):
        return None
    if _DEFAULT["embedder"] is None:
        _DEFAULT["embedder"] = Embedder()
    emb = _DEFAULT["embedder"]
    if not emb.available():
        if not _DEFAULT["warned"]:
            _DEFAULT["warned"] = True
            (log or (lambda s: print(s, file=sys.stderr)))(
                f"name matching: sentence-embedding model not used ({emb.reason}); using character n-gram similarity")
        return None
    return emb


# ---------------------------------------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------------------------------------
class Match:
    __slots__ = ("key", "name", "score", "runner_up", "method", "label")

    def __init__(self, key, name, score, runner_up, method):
        self.key, self.name, self.score, self.runner_up, self.method = key, name, score, runner_up, method
        self.label = f"{method} {score:.0%} (verify)"

    def __repr__(self):
        return f"Match({self.key!r}, {self.name!r}, {self.score:.3f}, {self.method})"


class NameMatcher:
    """Finds the best scheme for a name among `items` {key: display name}. Candidate vectors are built once."""

    def __init__(self, items, embedder="default", strip_code_query=True, strip_code_items=False):
        self.items = dict(items)
        self.strip_q, self.strip_i = strip_code_query, strip_code_items
        self.embedder = default_embedder() if embedder == "default" else embedder
        self._canon = {k: canon(n, strip_code_items) for k, n in self.items.items()}
        self._grams = {k: _grams(c) for k, c in self._canon.items()}
        self._vec = None
        self.last_reason = ""

    def _neural_scores(self, query_canon):
        import numpy as np
        if self._vec is None:
            keys = list(self.items)
            self._keys = keys
            self._vec = self.embedder.vectors([self._canon[k] for k in keys])
        q = self.embedder.vectors([query_canon])[0]
        return dict(zip(self._keys, (self._vec @ q).tolist()))

    def match(self, query, min_similarity=None, margin=None):
        """Best match or None (self.last_reason says why not)."""
        min_sim = setting("NAME_FALLBACK_MIN") if min_similarity is None else min_similarity
        margin = setting("NAME_FALLBACK_MARGIN") if margin is None else margin
        qc = canon(query, self.strip_q)
        self.last_reason = ""
        if not qc:
            self.last_reason = "empty name"
            return None
        qg = _grams(qc)
        use_neural = self.embedder is not None and self.embedder.available()
        scores = {k: _cos(qg, g) for k, g in self._grams.items()}
        method = "n-gram similarity"
        if use_neural:
            try:
                nscores = self._neural_scores(qc)
                scores = {k: max(scores[k], nscores.get(k, 0.0)) for k in scores}
                method = "embedding similarity"
            except Exception as exc:                      # a broken model must never break the run
                self.last_reason = f"embedding model failed ({type(exc).__name__}); used n-gram similarity"
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:8]
        passing = []
        first_refusal = ""
        for k, s in ranked:
            if s < min_sim - 0.15 and passing:
                break
            ok, why = guard(query, self.items[k], self.strip_q, self.strip_i)
            if ok:
                passing.append((k, s))
            elif not first_refusal and s >= min_sim:
                first_refusal = f"'{self.items[k]}' looked similar ({s:.0%}) but was refused: {why}"
        if not passing:
            self.last_reason = first_refusal or "no candidate is similar enough"
            return None
        top_k, top_s = passing[0]
        if top_s < min_sim:
            self.last_reason = first_refusal or f"best candidate only {top_s:.0%} similar"
            return None
        others = [s for k, s in passing[1:] if self._canon[k] != self._canon[top_k]]
        dup = [k for k, _ in passing[1:] if self._canon[k] == self._canon[top_k]]
        if dup:
            self.last_reason = "several schemes share this canonical name: " + ", ".join(str(k) for k in [top_k] + dup[:3])
            return None
        runner = max(others) if others else 0.0
        if top_s - runner < margin:
            self.last_reason = f"ambiguous: runner-up '{self.items[passing[1][0]]}' is within {margin:.0%}"
            return None
        return Match(top_k, self.items[top_k], top_s, runner, method)
