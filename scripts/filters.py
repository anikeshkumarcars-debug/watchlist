#!/usr/bin/env python3
"""
filters.py
----------
Single source of truth for the pre-scoring discovery filters shared by
fetch_and_score.py (daily pipeline) and expand_companies.py (discovery).

Before, the keyword/location lists were copy-pasted in both scripts with a
"keep in sync" comment — they drifted. Everything lives here now so discovery
and scoring apply identical rules, and so FDE roles get discovered *and* scored.

Two things this decides:
  1. classify_role(title) -> "pm" | "fde" | None   (which role family, if any)
  2. is_us_location(location) -> bool               (US-wide, non-US is the block)

Run `python filters.py --selftest` to check the classifier against representative
titles/locations without hitting any network or secrets.
"""

import re

# ── Role families ────────────────────────────────────────────────────────────
# The positive keyword gate is specific to product titles, so we do NOT need to
# list every non-PM function ("engineer", "analyst", ...) as an exclude — those
# titles simply never contain a PM keyword. Keeping the exclude list tiny avoids
# false drops like "Product Manager, Engineering Tools" (the old broad "engineer"
# exclude killed those because "engineer" is a substring of "engineering").

PM_KEYWORDS = [
    "product manager",      # also covers senior/technical/AI/group/staff/principal PM
    "product management",
    "senior pm",
    "pm ii", "pm i", "pm iii", "pm 2", "pm 1", "pm 3",
    "product lead",
    "product owner",        # a real title Shailvi held (GIVE)
    "product strategist",
    "product builder",
]

PM_EXCLUDE = [
    "program manager",      # defensive: only bites a title carrying both phrases
    "product marketing",
    "product counsel",
]

# FDE / Applied AI Engineer / Solutions family — first-class targets per
# AllResumes.md. Keywords are specific enough that pure SWE titles ("Software
# Engineer", "Backend Engineer") never match, so the exclude set is a light
# safety net for adjacent-but-wrong roles.
FDE_KEYWORDS = [
    "forward deployed",
    "forward-deployed",
    "applied ai engineer",
    "applied ml engineer",
    "applied engineer",
    "solutions engineer",
    "solution engineer",
    "solutions architect",
    "solution architect",
    "deployment engineer",
    "implementation engineer",
    "customer engineer",
]

FDE_EXCLUDE = [
    "sales engineer",
    "hardware engineer",
    "firmware",
    "mechanical engineer",
    "electrical engineer",
    "qa engineer",
    "test engineer",
    "security engineer",
]

# Seniority gate (both families). Soft-judge decision: hard-exclude ONLY
# exec / people-manager roles and too-junior intern/apprentice roles. Staff,
# Principal, Lead, and Group PM now pass through and are judged by the scorer.
# Word boundaries fix the old bugs ("vp " missed "VP,"; "principal pm" never
# matched "Principal Product Manager"). \bintern\b (not a prefix) so we don't
# clobber "International" / "Internal".
_SENIORITY_RE = re.compile(
    r"\bdirector\b"
    r"|\bvp\b|\bsvp\b|\bevp\b|\bavp\b|\bvice president\b"
    r"|\bhead of\b|\bchief\b|\bpresident\b"
    r"|\bintern\b|\binterns\b|\binternship\b"
    r"|\bapprentice\b|\bapprenticeship\b",
    re.I,
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def classify_role(title: str) -> str | None:
    """Return the role family a title belongs to, or None if it's off-target.

    "pm"  -> product manager / product lead (any IC seniority)
    "fde" -> forward deployed / applied AI / solutions / deployment engineer
    None  -> not a target role (wrong function, or exec/manager/intern level)
    """
    t = _norm(title)
    if not t:
        return None
    if _SENIORITY_RE.search(t):
        return None
    if any(k in t for k in PM_KEYWORDS) and not any(k in t for k in PM_EXCLUDE):
        return "pm"
    if any(k in t for k in FDE_KEYWORDS) and not any(k in t for k in FDE_EXCLUDE):
        return "fde"
    return None


# ── Location: US-wide (non-US is the only block) ─────────────────────────────
# Shailvi is open to all US locations + remote. So we KEEP by default and only
# drop when a location clearly names a non-US place and no US place is also named
# (covers "New York or London" hybrids and "Remote, US"). Empty / "Remote" /
# unknown locations are kept.

US_MARKERS = [
    "united states", "usa", "u.s.", "u.s.a", "u.s ",
    # common US hubs by name (safe as substrings)
    "new york", "san francisco", "bay area", "san jose", "mountain view",
    "palo alto", "menlo park", "sunnyvale", "seattle", "austin", "boston",
    "los angeles", "chicago", "denver", "atlanta", "washington", "san diego",
    "dallas", "houston", "miami", "philadelphia", "phoenix", "portland",
    "nashville", "raleigh", "pittsburgh", "irvine", "culver city",
]

# Comma-state forms need a trailing word boundary so ", ca" matches
# "San Francisco, CA" but NOT ", canada" / ", california".
_US_STATE_RE = re.compile(
    r",\s*(ca|wa|ny|tx|ma|il|or|co|ga|fl|va|dc|pa|nc|az|mi|oh|nj|mn|ut|tn|md|wi|nv)\b",
    re.I,
)

# Matched with word boundaries so short tokens don't hit mid-word
# (e.g. bare "uk" must not match "Milwaukee").
_NON_US_RE = re.compile(
    r"\b("
    r"united kingdom|uk|england|london|ireland|dublin|scotland"
    r"|germany|berlin|munich|hamburg|france|paris|spain|madrid|barcelona"
    r"|netherlands|amsterdam|belgium|switzerland|zurich|geneva|portugal|lisbon"
    r"|italy|rome|milan|poland|warsaw|sweden|stockholm|denmark|copenhagen"
    r"|norway|finland|austria|vienna|czech|prague|romania|greece"
    r"|canada|toronto|vancouver|montreal|ottawa|mexico"
    r"|india|bangalore|bengaluru|hyderabad|mumbai|delhi|pune|gurgaon|chennai"
    r"|singapore|australia|sydney|melbourne|new zealand|japan|tokyo"
    r"|china|beijing|shanghai|shenzhen|hong kong|taiwan|korea|seoul"
    r"|israel|tel aviv|brazil|sao paulo|argentina|colombia|chile"
    r"|dubai|abu dhabi|uae|saudi|egypt|nigeria|south africa|kenya"
    r"|emea|apac|latam|europe|european|international"
    r")\b",
    re.I,
)


def is_us_location(location: str) -> bool:
    if not location or not location.strip():
        return True
    l = location.lower()
    if _NON_US_RE.search(l):
        # A non-US place is named: keep only if a US place is also named
        # (hybrid postings like "New York or London").
        return bool(_US_STATE_RE.search(l)) or any(m in l for m in US_MARKERS)
    return True


# ── Self-test ────────────────────────────────────────────────────────────────

def _selftest() -> int:
    role_cases = [
        ("Forward Deployed Engineer", "fde"),
        ("Forward Deployed Software Engineer", "fde"),
        ("Applied AI Engineer", "fde"),
        ("Solutions Architect, AI", "fde"),
        ("Deployment Engineer", "fde"),
        ("Sales Engineer", None),
        ("Staff Product Manager", "pm"),
        ("Principal Product Manager", "pm"),
        ("Group Product Manager", "pm"),
        ("Senior Product Manager, AI", "pm"),
        ("Technical Product Manager", "pm"),
        ("Product Manager, Engineering Tools", "pm"),   # old broad-"engineer" bug
        ("Director of Product", None),
        ("VP, Product", None),
        ("Head of Product", None),
        ("Product Management Internship", None),
        ("Software Engineer", None),
        ("Product Designer", None),
        ("International Product Manager", "pm"),         # must NOT hit intern/non-US
    ]
    loc_cases = [
        ("", True),
        ("Remote", True),
        ("San Francisco, CA", True),
        ("Denver, CO", True),
        ("Denver, Colorado", True),
        ("New York", True),
        ("Remote - US", True),
        ("Milwaukee, WI", True),           # must not trip bare "uk"
        ("London, UK", False),
        ("Remote - EMEA", False),
        ("Bengaluru, India", False),
        ("Toronto, Canada", False),
        ("New York or London", True),      # hybrid: US named -> keep
    ]

    failures = 0
    for title, want in role_cases:
        got = classify_role(title)
        ok = got == want
        failures += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] classify_role({title!r}) = {got!r} (want {want!r})")
    for loc, want in loc_cases:
        got = is_us_location(loc)
        ok = got == want
        failures += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] is_us_location({loc!r}) = {got} (want {want})")

    print(f"\n{'ALL PASS' if not failures else str(failures) + ' FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print("Usage: python filters.py --selftest")
