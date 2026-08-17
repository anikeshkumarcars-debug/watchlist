#!/usr/bin/env python3
"""
filters.py
----------
Single source of truth for the pre-scoring discovery filters shared by
fetch_and_score.py (daily pipeline) and expand_companies.py (discovery).

Before, the keyword/location lists were copy-pasted in both scripts with a
"keep in sync" comment — they drifted. Everything lives here now so discovery
and scoring apply identical rules, and so BizOps roles get discovered *and*
scored.

Two things this decides:
  1. classify_role(title) -> "strategy" | "bizops" | None  (which role family, if any)
  2. is_ca_location(location) -> bool                       (Toronto/GTA or remote-Canada; else blocked)

Run `python filters.py --selftest` to check the classifier against representative
titles/locations without hitting any network or secrets.
"""

import re

# ── Role families ────────────────────────────────────────────────────────────
# The positive keyword gate is specific to strategy/ops titles, so we do NOT
# need to list every unrelated function ("engineer", "designer", ...) as an
# exclude — those titles simply never contain a strategy/bizops keyword.

STRATEGY_KEYWORDS = [
    "corporate strategy",
    "business strategy",
    "strategy manager",
    "strategy associate",
    "strategy analyst",
    "strategy consultant",
    "strategy & operations",
    "strategy and operations",
    "corporate development",
    "strategic planning",
    "growth strategy",
]

STRATEGY_EXCLUDE = [
    "marketing strategist",   # marketing function, not corporate strategy
]

# BizOps / RevOps family — the natural extension of Anikesh's consulting +
# revenue-operations background.
#
# IMPORTANT: every keyword here is a QUALIFIED phrase ("business operations",
# not bare "operations manager"). An early version listed bare "operations
# manager" / "operations analyst" / "operations associate" and a live scan of
# ~12.5k boards showed what that actually catches: "Kitchen Operations
# Associate, DashMart", "Overseas Operations Manager (P2P)", "Variable Schedule
# Operations Associate". Those are frontline/physical ops, not business ops.
# Since every kept posting costs a Claude scoring call, this trades a little
# recall for a lot of precision — widen deliberately if the board looks thin.
BIZOPS_KEYWORDS = [
    "business operations",
    "biz ops",
    "bizops",
    "revenue operations",
    "revops",
    "sales operations",
    "gtm operations",
    "go-to-market operations",
    "commercial operations",
    "product operations",
    "operations strategy",
    "strategic operations",
]

# Ops functions that are a different job family entirely. These bite even when
# a BIZOPS_KEYWORDS phrase is present (e.g. "People Operations Business
# Partner"), so they're checked as a veto.
BIZOPS_EXCLUDE = [
    "people operations", "payroll", "hr operations", "human resources",
    "it operations", "security operations", "network operations",
    "clinical operations", "flight operations", "trading operations",
    "warehouse", "kitchen", "plant operations", "field operations",
    "fleet operations", "restaurant", "store operations", "retail operations",
    "manufacturing operations", "logistics", "supply chain", "datacenter",
    "data center",
]

# Seniority gate (both families). Hard-exclude roles that are out of reach at
# ~2 years of experience, plus too-junior intern/apprentice roles.
#
# "Senior Manager" and "Principal" are dropped here deliberately: in both
# strategy and BizOps those titles normally carry 5-8+ years and direct
# reports, which is a level above this candidate. They used to pass through to
# the scorer, which meant paying for a Claude call to reject them. Dropping on
# the title is free and matches the stated constraint.
#
# Still passing through (judged by the scorer, not the title): Manager,
# Senior Analyst, Senior Associate, Lead. "Lead" in particular is genuinely
# ambiguous — "Strategy & Operations Lead" at a 30-person startup is often an
# IC role — so it gets judged on the JD rather than the word.
#
# Word boundaries fix the old bugs ("vp " missed "VP,"). \bintern\b (not a
# prefix) so we don't clobber "International" / "Internal".
_SENIORITY_RE = re.compile(
    r"\bdirector\b"
    r"|\bvp\b|\bsvp\b|\bevp\b|\bavp\b|\bvice president\b"
    r"|\bhead of\b|\bchief\b|\bpresident\b"
    # "Senior <anything> Manager" — catches "Senior Manager, RevOps" and
    # "Senior Strategy & Operations Manager" alike. A bare "Senior Analyst" or
    # "Senior Associate" has no "manager" token, so it still passes.
    r"|\bsenior\b.*\bmanager\b|\bsr\.?\b.*\bmanager\b|\bsenior mgr\b"
    r"|\bprincipal\b"
    r"|\bintern\b|\binterns\b|\binternship\b"
    r"|\bapprentice\b|\bapprenticeship\b",
    re.I,
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def classify_role(title: str) -> str | None:
    """Return the role family a title belongs to, or None if it's off-target.

    "strategy" -> corporate strategy / strategy consulting / corp dev
    "bizops"   -> business/revenue/sales operations, ops analyst/manager
    None       -> not a target role (wrong function, or exec/intern level)

    Note: "Chief of Staff" is deliberately not a keyword — it collides with
    the \\bchief\\b exec-seniority exclusion below, and realistically sits
    above a 2-YOE target level anyway.
    """
    t = _norm(title)
    if not t:
        return None
    if _SENIORITY_RE.search(t):
        return None
    if any(k in t for k in STRATEGY_KEYWORDS) and not any(k in t for k in STRATEGY_EXCLUDE):
        return "strategy"
    if any(k in t for k in BIZOPS_KEYWORDS) and not any(k in t for k in BIZOPS_EXCLUDE):
        return "bizops"
    return None


# ── Location: Toronto/GTA or remote-Canada (ALLOW-LIST — deny by default) ───
# Anikesh is based in Toronto and open to GTA-based roles or roles remote
# within Canada — NOT other Canadian cities on-site (Vancouver, Montreal, ...)
# and NOT any US/international location.
#
# IMPORTANT: this is an ALLOW-list (deny by default). The predecessor to this
# filter was a US-wide block-list ("keep unless it names a known-foreign
# place"), which is the right shape when the target is a whole country but
# badly wrong for a single metro: a live scan of ~12.5k boards showed Madrid,
# Seoul, Bogotá, Phoenix, Buenos Aires and São Paulo all sailing through
# simply because they weren't on the block list. Anything that names a place
# we don't recognize as GTA/Canadian is now dropped.

GTA_MARKERS = [
    "toronto", "gta", "greater toronto",
    "mississauga", "markham", "vaughan", "brampton", "scarborough",
    "north york", "etobicoke", "oakville", "richmond hill", "york region",
    "ontario", ", on ", ", on,", "on, canada",
]

# Recognized-but-not-a-fit: a real Canadian city that isn't GTA. Kept as a
# distinct list purely for readability — the outcome is still "drop" unless
# the posting is also flagged remote.
OTHER_CA_CITY_MARKERS = [
    "vancouver", "montreal", "montréal", "calgary", "edmonton", "ottawa",
    "winnipeg", "halifax", "quebec", "québec", "victoria", "saskatoon",
    "regina", "kitchener", "waterloo", "london, on", "hamilton",
]

_CANADA_RE = re.compile(r"\bcanada\b|\bcanadian\b", re.I)
_REMOTE_RE = re.compile(r"\bremote\b|\bwork from home\b|\banywhere\b", re.I)

# Generic multi-location / unspecified placeholders (common on Workday). We
# can't tell from these alone, so they're kept and left for the scorer to
# judge from the JD rather than silently dropping a possible Toronto role.
_AMBIGUOUS_RE = re.compile(
    r"^\s*(\d+\s+locations?|multiple locations?|various|headquarter\w*|hybrid|flexible)\s*$",
    re.I,
)

# Explicitly-foreign markers. Only used to veto an otherwise-remote posting
# ("Remote - US"); a location naming none of these is still denied unless it
# matches an allow-list entry above.
_NON_CA_RE = re.compile(
    r"\b("
    r"united states|usa|u\.s\.|u\.s\.a|us|us only|us-based"
    r"|new york|san francisco|bay area|seattle|austin|boston|los angeles"
    r"|chicago|denver|atlanta|washington|dallas|houston|miami|phoenix"
    r"|united kingdom|uk|england|london|ireland|dublin|scotland"
    r"|germany|berlin|france|paris|spain|madrid|netherlands|amsterdam"
    r"|india|bangalore|bengaluru|hyderabad|mumbai|delhi|pune"
    r"|singapore|australia|sydney|melbourne|mexico|brazil|colombia|argentina"
    r"|china|beijing|shanghai|hong kong|japan|tokyo|korea|seoul"
    r"|portugal|lisbon|poland|romania|ukraine|turkey|israel|philippines"
    r"|vietnam|thailand|bangkok|malaysia|indonesia|costa rica|chile|peru"
    r"|nigeria|kenya|egypt|south africa|munich|berlin|zurich|stockholm"
    r"|utah|texas|florida|arizona|colorado|georgia|virginia|ohio"
    r"|emea|apac|latam|europe|european|international"
    r")\b",
    re.I,
)


def is_ca_location(location: str) -> bool:
    """True only for Toronto/GTA, remote-Canada, or genuinely unspecified."""
    if not location or not location.strip():
        return True                      # unknown — let the scorer judge from the JD
    l = location.lower()

    if _AMBIGUOUS_RE.match(l):
        return True                      # "2 Locations" / "Multiple Locations"

    # Toronto/GTA named anywhere wins, even in a hybrid posting
    # ("Toronto or Vancouver", "New York; Toronto").
    if any(m in l for m in GTA_MARKERS):
        return True

    # Remote postings: keep unless they name a foreign region.
    if _REMOTE_RE.search(l):
        if _NON_CA_RE.search(l):
            return False                 # "Remote - US", "Remote (EMEA)"
        return True                      # bare "Remote" / "Remote - Canada"

    # Canada named without a city, and not a non-GTA city -> nationwide posting.
    if _CANADA_RE.search(l) and not any(m in l for m in OTHER_CA_CITY_MARKERS):
        return True

    # Everything else names a specific place that isn't GTA -> deny.
    return False


# ── Self-test ────────────────────────────────────────────────────────────────

def _selftest() -> int:
    role_cases = [
        ("Corporate Strategy Manager", "strategy"),
        ("Strategy & Operations Associate", "strategy"),
        ("Senior Strategy Analyst", "strategy"),
        ("Corporate Development Associate", "strategy"),
        ("Strategy Consultant", "strategy"),
        ("Business Operations Manager", "bizops"),
        ("Revenue Operations Analyst", "bizops"),
        ("Sales Operations Associate", "bizops"),
        ("RevOps Manager", "bizops"),
        ("Commercial Operations Analyst", "bizops"),
        ("Product Operations Manager", "bizops"),
        # Level gate: ~2 YOE, so "Senior <x> Manager" / "Principal" are out of
        # reach, but Manager / Senior Analyst / Senior Associate / Lead stay in.
        ("Senior Manager, Revenue Operations", None),
        ("Senior Strategy & Operations Manager, Wholesale", None),
        ("Senior Business Operations Manager", None),
        ("Sr. Manager, Business Operations", None),
        ("Principal, Strategy and Operations", None),
        ("Strategy & Operations Manager", "strategy"),
        ("Business Operations Manager", "bizops"),
        ("Senior Strategy Analyst", "strategy"),
        ("Senior Revenue Operations Analyst", "bizops"),
        ("Strategy & Operations Associate", "strategy"),
        ("Revenue Operations Lead", "bizops"),
        # Real titles a live 12.5k-board scan surfaced under the old, looser
        # bare-"operations manager" keywords. All must now be dropped.
        ("Kitchen Operations Associate, DashMart", None),
        ("Overseas Operations Manager (P2P)", None),
        ("Variable Schedule Operations Associate", None),
        ("Operations Manager", None),                    # bare: too ambiguous
        ("Operations Associate", None),
        ("Workday Payroll and People Operations Analyst", None),
        ("Security Operations Analyst", None),
        ("Supply Chain Operations Manager", None),
        ("Warehouse Operations Associate", None),        # excluded physical-ops
        ("Marketing Strategist", None),                  # excluded, marketing fn
        ("Director of Strategy", None),
        ("VP, Business Operations", None),
        ("Head of Strategy", None),
        ("Chief of Staff", None),                        # deliberately unlisted
        ("Strategy Internship", None),
        ("Software Engineer", None),
        ("Product Designer", None),
        ("International Strategy Manager", "strategy"),  # must NOT hit intern/non-CA
    ]
    loc_cases = [
        ("", True),
        ("Remote", True),
        ("Toronto, ON", True),
        ("Toronto, Ontario", True),
        ("Toronto, Ontario, Canada", True),
        ("Mississauga, ON", True),
        ("Etobicoke, Ontario, Canada", True),
        ("Remote - Canada", True),
        ("Canada", True),
        ("2 Locations", True),              # Workday placeholder -> scorer judges
        ("Multiple Locations", True),
        ("Vancouver, BC", False),           # real Canadian city, not GTA/remote
        ("Montreal, QC", False),
        ("Remote - US", False),
        ("Remote (EMEA)", False),
        ("London, UK", False),
        ("Bengaluru, India", False),
        ("Toronto or Vancouver", True),     # hybrid: GTA named -> keep
        # Real leaks the old block-list logic allowed through (deny-by-default
        # is what fixes these — none of them are on any block list).
        ("Madrid", False),
        ("Seoul", False),
        ("Bogota, Colombia", False),
        ("Hawthorne, CA", False),
        ("Somerville, MA", False),
        ("Buenos Aires", False),
        ("Bastrop, TX", False),
        ("Salt Lake City, UT", False),
        ("Belo Horizonte, MG", False),
        ("Malaysia", False),
        ("Bangkok, Thailand", False),
    ]

    failures = 0
    for title, want in role_cases:
        got = classify_role(title)
        ok = got == want
        failures += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] classify_role({title!r}) = {got!r} (want {want!r})")
    for loc, want in loc_cases:
        got = is_ca_location(loc)
        ok = got == want
        failures += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] is_ca_location({loc!r}) = {got} (want {want})")

    print(f"\n{'ALL PASS' if not failures else str(failures) + ' FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print("Usage: python filters.py --selftest")
