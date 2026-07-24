"""Team-name matching tuned for cross-source soccer reconciliation.

The original difflib ratio matcher had two failure modes visible in the
Edge Factory audit:

  * Prefix-key collisions ("Guangzhou" matches both Guangzhou E-Power and
    Guangzhou FC on the same day; "Hebei Kungfu" vs "Hebei Kung Fu" missed
    because of whitespace/hyphen differences).
  * Token-order shuffles and stop-word differences ("Manchester United"
    vs "Man United" vs "Man Utd").

This module keeps the original ``match_teams`` entry point for
backwards compatibility but adds:

  * Better normalization (more stopwords, abbreviation expansion, U21/U23/B/W
    flag preservation).
  * Token-set ratio instead of pure sequence ratio, which is robust to word
    order differences and partial extra tokens.
  * A league+date scoped high-level matcher :func:`match_match` used by the
    join layer to disambiguate same-named teams on the same day.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Set, Tuple

import difflib


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Words that appear frequently as prefixes/suffixes in team names but don't
# distinguish teams.  City/United/Real are NOT in here because they DO
# distinguish (e.g. Manchester City vs Manchester United, Real Madrid vs Real
# Sociedad vs Real Betis).
_STOPWORDS: Set[str] = {
    "fc", "cf", "sc", "afc", "ac", "as", "rc", "rcd", "cd", "fk", "sk",
    "ifk", "aik", "bsc", "sv", "bk", "hb", "ab", "ag", "ss", "us", "ssd",
    "club", "team", "football", "futebol", "futbol", "calcio",
    "sports",
    "the", "and", "of", "de", "del", "di", "du", "des", "da", "dos", "das",
    "el", "al", "la", "les", "le", "los", "las",
    # Deliberately NOT in here (they distinguish well-known rival pairs):
    # - real (Madrid vs Sociedad vs Betis)
    # - sporting (CP vs Gijón vs Huelva)
    # - athletic (Bilbao)  vs atletico (Madrid) — different words after NFKD
    # - city / united (Manchester pairs; Bristol pairs; many others)
    # - inter (Inter Milan vs AC Milan; Internacional vs others)
    # - rovers / town / wanderers / palace
}

# Abbreviations -> canonical form. Keys are already-lowercase / stripped.
_ABBREV: Dict[str, str] = {
    "utd": "united",
    "man": "manchester",
    "manc": "manchester",
    "spurs": "tottenham",
    "westham": "west ham",
    "avfc": "aston villa",
    "bvb": "borussia dortmund",
    "rma": "real madrid",
    "fcb": "barcelona",
    "mufc": "manchester united",
    "mcfc": "manchester city",
    "lfc": "liverpool",
    "cfc": "chelsea",
    "thfc": "tottenham",
    "nffc": "nottingham forest",
    "coyi": "west ham",  # fan acronym; harmless
    "psg": "paris saint germain",
    # Common anglicised / local dual forms (anglicised -> local so both
    # sources collapse to the same token; we pick the local form because
    # Forebet and SoccerStats lean European).
    "munich": "munchen",
    "rome": "roma",
    "genoa": "genova",
    "turin": "torino",
    "florence": "firenze",
    "cologne": "koln",
    "hanover": "hannover",
    "nuremberg": "nurnberg",
    "brunswick": "braunschweig",
    # NOTE: "milan" is NOT mapped to "milano" — AC Milan is universally
    # "Milan" in English sources and Inter is "Inter Milan" (not "Inter
    # Milano" in English), so keeping "milan" avoids spurious divergence.
    # Chinese dual-transliterations (pinyin vs postal/other)
    "kejia": "hakka",
}

# Suffixes that denote reserve / youth / women sides. Both sides of a
# candidate pair must agree on these or we reject.
_RESERVE_MARKERS: Tuple[str, ...] = (
    "u21", "u22", "u23", "u19", "u18", "u17", "ii", "iii", "b", "w", "women",
    "reserves", "reserve", "youth",
)


def normalize_team_name(name: str) -> str:
    """Aggressive, deterministic team-name normalization.

    Lowercases, strips diacritics and punctuation, tokenizes, expands a
    small abbreviation list, and removes corporate/stopword prefixes. The
    reserve/women markers are KEPT (so U21 sides don't collide with senior
    sides).
    """
    if not name:
        return ""
    s = name.lower()
    # Decompose diacritics and strip combining marks
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    # Treat hyphens/apostrophes as spaces so "E-Power" -> "e power",
    # "Kung-fu" -> "kung fu", "O'Neil" -> "o neil".
    s = re.sub(r"[^a-z0-9\s+]", " ", s)
    s = s.replace("+", " ")
    tokens: List[str] = []
    for raw in s.split():
        tok = raw.strip()
        if not tok:
            continue
        # Expand a few common abbreviations
        tok = _ABBREV.get(tok, tok)
        for t in tok.split():
            t = t.strip()
            if not t:
                continue
            if t in _STOPWORDS:
                continue
            tokens.append(t)
    return " ".join(tokens)


def reserve_suffix(normalized: str) -> Optional[str]:
    """Return the reserve/women marker if one is present, else None."""
    tokens = normalized.split()
    for tok in tokens:
        if tok in _RESERVE_MARKERS:
            return tok
    return None


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def _canonical_tokens(s: str) -> List[str]:
    return [t for t in normalize_team_name(s).split() if t]


def _squash_for_compare(a_tokens: List[str], b_tokens: List[str]) -> Tuple[str, str]:
    """Align tokens across two team names to make them more comparable.

    Handles two cases that pure token-set ratio misses:

    1. Concatenated vs split tokens ("kungfu" vs "kung fu", "west ham" vs
       "westham") — merge the split tokens on one side when they equal a
       single token on the other.
    2. Initials ("Nottingham F." vs "Nottingham Forest") — if one side has a
       single-character token that is the first character of a same-position
       long token on the other side, expand it to the long token.

    Returns two space-joined strings ready for ratio comparison.
    """
    a = list(a_tokens)
    b = list(b_tokens)

    # Pass 1: concatenation merges (both directions, iteratively).
    def _merge_one(shorter: List[str], longer: List[str]) -> bool:
        set_longer = set(longer)
        for window in (2, 3):
            for i in range(len(shorter) - window + 1):
                merged = "".join(shorter[i:i + window])
                if len(merged) >= 4 and merged in set_longer:
                    shorter[i:i + window] = [merged]
                    return True
        return False

    for _ in range(3):
        did = False
        if _merge_one(a, b):
            did = True
        if _merge_one(b, a):
            did = True
        if not did:
            break

    # Pass 2: single-char initial expansion.
    def _expand_initials(has_initial: List[str], full: List[str]) -> bool:
        if len(has_initial) != len(full):
            return False
        changed = False
        for i, t in enumerate(has_initial):
            if len(t) == 1 and t.isalpha() and len(full[i]) >= 3 and full[i].startswith(t):
                has_initial[i] = full[i]
                changed = True
        return changed

    # Only expand initials if token counts match after pass 1 (position matters)
    if len(a) == len(b):
        _expand_initials(a, b)
        _expand_initials(b, a)

    return " ".join(a), " ".join(b)


def _token_set_ratio(a: str, b: str) -> float:
    """Token-set ratio, with a disambiguator penalty.

    The classic token-set ratio gives 1.0 whenever one side's tokens are a
    subset of the other's (e.g. "Milan" ⊂ "Inter Milan"), which wrongly
    matches rival clubs.  We penalise by the *length* of the non-shared
    tokens relative to total tokens, so "Guangzhou" ⊂ "Guangzhou E-Power"
    (one extra short token "e" gets discarded by prefix logic later) still
    scores high, but "Milan" vs "Inter Milan" (one extra meaningful token
    "inter") is knocked down.
    """
    toks_a = set(a.split())
    toks_b = set(b.split())
    if not toks_a or not toks_b:
        return 0.0
    inter = toks_a & toks_b
    a_minus_b = toks_a - toks_b
    b_minus_a = toks_b - toks_a
    inter_str = " ".join(sorted(inter))
    ab_str = (inter_str + " " + " ".join(sorted(a_minus_b))).strip()
    ba_str = (inter_str + " " + " ".join(sorted(b_minus_a))).strip()
    sm = difflib.SequenceMatcher(None)
    ratios = []
    for x, y in ((inter_str, ab_str), (inter_str, ba_str), (ab_str, ba_str)):
        if not x or not y:
            continue
        sm.set_seqs(x, y)
        ratios.append(sm.ratio())
    raw = max(ratios) if ratios else 0.0
    # Penalty: extra tokens that are "meaningful" (len>=3) on both sides
    # reduce the score.  E.g. Milan vs Inter Milan -> extras=0 vs 1 (one side
    # has extras, the other doesn't), we scale by (|inter| / (|inter| +
    # extras_on_shorter_side+)).
    meaningful_extras_a = sum(1 for t in a_minus_b if len(t) >= 3)
    meaningful_extras_b = sum(1 for t in b_minus_a if len(t) >= 3)
    # Only penalise when one side has something the other doesn't AND the
    # intersection isn't already the full name.
    # Tokens that, if they appear as an "extra" on one side only, are a
    # strong sign the names refer to DIFFERENT clubs in the same city.
    _STRONG_DISAMBIGUATORS = {
        # Cross-city rivals that share a city token.  These only trigger the
        # heavy penalty when extras exist on BOTH sides (e.g. "Man City" vs
        # "Man United").  Single-side extras (subset, like "West Ham" ⊂ "West
        # Ham United") use the soft penalty because there is no same-city
        # alternative being offered.
        "city", "united", "real", "inter", "sporting", "athletic",
        "atletico", "atletic", "hotspur", "spurs", "albion", "rovers",
        "wanderers", "villa", "palace", "forest", "north", "south",
        "east", "west",
    }
    # Tokens that identify a rival prefix even in the subset case (bare city
    # name vs prefixed club), e.g. "Milan" (ambiguous: AC vs Inter) but NOT
    # "Madrid" (Atlético has a different token altogether, not "real") or
    # "West Ham" (there is no other West Ham).
    _RIVAL_PREFIXES = {"inter", "sporting"}
    extra_tokens = a_minus_b | b_minus_a
    both_sides_extras = meaningful_extras_a > 0 and meaningful_extras_b > 0
    strong_hit_both = both_sides_extras and any(t in _STRONG_DISAMBIGUATORS for t in extra_tokens)
    # Rival-prefix subset case: when one side is just "<city>" and the other
    # side prefixes it with "Inter"/"Sporting" (clubs that share a city with
    # a non-prefixed cousin: Inter/AC Milan, Sporting/Benfica).  We soften
    # but still pass through — pair-level match_match is the real defense.
    small_base = len(inter) <= 2 and all(len(t) <= 8 for t in inter)
    rival_prefix_subset = (not both_sides_extras) and small_base and any(
        t in _RIVAL_PREFIXES for t in extra_tokens
    )

    if meaningful_extras_a or meaningful_extras_b:
        longer_extras = max(meaningful_extras_a, meaningful_extras_b)
        if strong_hit_both:
            penalty = 0.45
        elif rival_prefix_subset:
            penalty = 0.18
        elif both_sides_extras:
            penalty = 0.20 * longer_extras
        else:
            penalty = 0.04 * longer_extras
        raw = max(0.0, raw - penalty)
    return raw


def _prefix_recall(a: str, b: str) -> float:
    """What fraction of a's tokens are prefix-matched in b (and vice versa).

    Catches the "Guangzhou" vs "Guangzhou E-Power" case — the shorter name's
    tokens are all present as prefixes of some token in the longer name.
    """
    toks_a = a.split()
    toks_b = b.split()
    if not toks_a or not toks_b:
        return 0.0

    def _all_prefix(needles: List[str], hay: List[str]) -> float:
        if not needles:
            return 0.0
        hits = 0
        for n in needles:
            if any(h.startswith(n) or n.startswith(h) for h in hay if len(h) >= 3 and len(n) >= 3):
                hits += 1
        return hits / len(needles)

    return min(1.0, max(_all_prefix(toks_a, toks_b), _all_prefix(toks_b, toks_a)))


def similarity(s1: str, s2: str) -> float:
    """Combined token-set + prefix similarity in [0,1]."""
    n1 = normalize_team_name(s1)
    n2 = normalize_team_name(s2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0
    toks1 = n1.split()
    toks2 = n2.split()
    c1, c2 = _squash_for_compare(toks1, toks2)
    ts = _token_set_ratio(c1, c2)
    pr = _prefix_recall(c1, c2)
    return max(ts, 0.7 * ts + 0.3 * pr)


def match_teams(team_a: str, team_b: str,
                aliases: Optional[Dict[str, str]] = None,
                threshold: float = 0.82,
                ambiguous_threshold: float = 0.60
                ) -> Tuple[bool, float, str]:
    """Match two team names. Returns ``(is_match, confidence, reason)``.

    Default thresholds are slightly looser than the previous 0.85/0.65
    split, justified by the stronger token-set similarity metric reducing
    false positives that the old pure SequenceMatcher produced at 0.85.
    """
    aliases = aliases or {}
    n1 = normalize_team_name(team_a)
    n2 = normalize_team_name(team_b)

    if not n1 or not n2:
        return False, 0.0, "Missing names"

    if n1 == n2:
        return True, 1.0, "Exact match after normalization"

    if aliases.get(n1) == n2 or aliases.get(n2) == n1:
        return True, 1.0, "Alias match"

    # Reserve / women / B-team mismatch is a hard reject.
    r1, r2 = reserve_suffix(n1), reserve_suffix(n2)
    if r1 != r2:
        return False, 0.0, f"Mismatched reserve marker: {r1!r} vs {r2!r}"

    sim = similarity(team_a, team_b)

    # Single-token short names need a near-exact match to avoid false
    # positives (e.g. "Braga" vs "Bragantino").
    if len(n1.split()) == 1 and len(n2.split()) == 1:
        minlen = min(len(n1), len(n2))
        if minlen >= 5 and n1[:minlen] != n2[:minlen] and sim < 0.9:
            return False, sim, "Short single-token name; prefix mismatch"

    # Generic-prefix false-positive guard: if both names share a leading token
    # but the remaining tokens are ALL short (≤3 chars) and different, treat
    # as ambiguous — e.g. "Sporting CP" vs "Sporting Gijón", "Man City" vs
    # "Man Utd" (handled above since city/united >3 chars), "FC Porto" vs
    # "FC Paços".
    toks1 = n1.split()
    toks2 = n2.split()
    if len(toks1) >= 2 and len(toks2) >= 2:
        shared_prefix = 0
        for t1, t2 in zip(toks1, toks2):
            if t1 == t2:
                shared_prefix += 1
            else:
                break
        if shared_prefix >= 1 and shared_prefix < min(len(toks1), len(toks2)):
            rest1 = [t for t in toks1[shared_prefix:] if len(t) >= 2]
            rest2 = [t for t in toks2[shared_prefix:] if len(t) >= 2]
            all_short_distinct = (
                rest1 and rest2
                and all(len(t) <= 3 for t in rest1 + rest2)
                and not set(rest1) & set(rest2)
            )
            if all_short_distinct:
                # Cap similarity to the ambiguous band.
                sim = min(sim, ambiguous_threshold + 0.04)
                return False, round(sim, 3), "Shared prefix only; remainder short & distinct"

    if sim >= threshold:
        return True, sim, "Fuzzy match"
    if sim >= ambiguous_threshold:
        return False, sim, "Ambiguous match"
    return False, sim, "No match"


# ---------------------------------------------------------------------------
# Cross-source MATCH-level matching
# ---------------------------------------------------------------------------


def match_match(home_a: str, away_a: str,
                home_b: str, away_b: str,
                *, aliases: Optional[Dict[str, str]] = None,
                ) -> Tuple[bool, float, str]:
    """Match two matches' home/away pairs independently, not swapped.

    The Edge-Factory audit showed cross-matching home<->away is a rare but
    catastrophic failure mode. We require BOTH sides to match above
    threshold and never swap.
    """
    h_match, h_sim, h_reason = match_teams(home_a, home_b, aliases=aliases)
    a_match, a_sim, a_reason = match_teams(away_a, away_b, aliases=aliases)
    if not h_match:
        return False, round(h_sim, 3), f"Home no-match: {h_reason}"
    if not a_match:
        return False, round(a_sim, 3), f"Away no-match: {a_reason}"
    # Soft-penalise asymmetric confidence (one side exact, other weak fuzzy).
    combined = 0.5 * (h_sim + a_sim)
    if min(h_sim, a_sim) < 0.75:
        return False, round(combined, 3), "Weak match on one side"
    return True, round(combined, 3), "Paired match"


def match_match_permissive(home_a: str, away_a: str,
                           home_b: str, away_b: str,
                           candidates: Optional[Iterable[Tuple[str, str, str]]] = None,
                           *, aliases: Optional[Dict[str, str]] = None,
                           ) -> Tuple[bool, float, str, Optional[str]]:
    """Like :func:`match_match` but allows home/away swap if the
    non-swapped pairing fails AND only one pairing wins.

    ``candidates`` is an optional iterable of ``(home_b, away_b, candidate_id)``
    to disambiguate among multiple possible matches on the same day. When
    provided we return the best-scoring candidate that beats all others by
    a margin, or quarantines if two tie too closely.

    Returns ``(is_match, confidence, reason, matched_id)``.
    """
    # Forward (correct orientation) first
    ok, sim, reason = match_match(home_a, away_a, home_b, away_b, aliases=aliases)
    if ok:
        return True, sim, reason, None
    if candidates is None:
        return False, sim, reason, None

    # Score every candidate and pick the unique best if it clears a margin.
    best: Optional[Tuple[float, str, str, str]] = None
    second_best = -1.0
    for ch, ca, cid in candidates:
        ok_c, sim_c, reason_c = match_match(home_a, away_a, ch, ca, aliases=aliases)
        if not ok_c:
            # try swapped
            ok_s, sim_s, reason_s = match_match(home_a, away_a, ca, ch, aliases=aliases)
            if ok_s:
                sim_c, reason_c = sim_s, f"Swapped: {reason_s}"
            else:
                sim_c = max(sim_c, sim_s)
        if sim_c > second_best:
            if best is None or sim_c > best[0]:
                if best is not None:
                    second_best = best[0]
                best = (sim_c, cid, reason_c, ch + " vs " + ca)
            else:
                second_best = sim_c
    if best is None or best[0] < 0.82:
        return False, best[0] if best else 0.0, "No candidate cleared threshold", None
    margin = best[0] - second_best
    if margin < 0.05:
        return False, round(best[0], 3), f"Ambiguous (margin {margin:.3f})", None
    return True, round(best[0], 3), best[2], best[1]
