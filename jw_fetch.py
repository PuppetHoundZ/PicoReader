"""
jw_fetch.py

Optional PicoReader plugin: download JW.org EPUB publications directly
onto the device, using the same public media API JW.org's own official
apps use (b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS) plus the
jw.org "What's New" RSS feed to auto-detect the newest Watchtower Study
Edition and Meeting Workbook issue without needing to know or guess a date.

PRIVATE PLUGIN -- per the person's explicit instruction, this file is
NOT to be published to a public GitHub repo alongside gutenberg_fetch.py.
Keep it local-only. See AI NOTES in main.py for the full legal reasoning
(jw.org Terms of Use, checked in-conversation, not guessed).

All pub codes below were verified LIVE against the real API before being
added here (not guessed) -- see main.py's AI NOTES for the verification
method if any of these ever need re-checking after a JW.org catalog change.

HOW THIS PLUGIN DIFFERS FROM gutenberg_fetch.py:
  gutenberg_fetch.py queries a real search API (Gutendex) with free-text
  queries and gets back paginated results. This plugin works differently:
  - The catalog is small and fixed (a curated list of publications we know
    exist), so there's no search or pagination -- everything fits one page.
  - Downloads are a TWO-STEP process: first we call GETPUBMEDIALINKS to
    resolve the current download URL for a publication (URLs can change),
    then we fetch that URL. gutenberg_fetch.py only needs one step because
    Gutendex already gives us a direct EPUB URL in the catalog response.
  - Periodical issues (Watchtower, Workbook) need an YYYYMM issue code.
    We use the RSS feed to detect the actual latest issue, with a
    same-month fallback guess if the feed can't be reached.

PLUGIN CONTRACT -- same as gutenberg_fetch.py. See that file's docstring
for the full interface. list_items() here ignores `query`/`page` (the
catalog is small and fixed, no pagination needed) and always returns
has_next=False.

No pip dependencies -- stdlib urllib only. See gutenberg_fetch.py's
docstring for why this matters on muOS hardware.

BACK-ISSUES (v4): Watchtower ("w") lists every issue back to Jan 2016 via
generate_monthly_back_issues() -- safe, confirmed monthly with zero gaps
the whole range. Meeting Workbook ("mwb") gets its OWN generator,
generate_mwb_back_issues() -- Kaleb caught that v2 wrongly treated it as
pure-monthly too; live-verified it was actually monthly only through
Dec 2020, then changed to bi-monthly (odd months only, even months 404)
from Jan 2021 on. See MWB_BIMONTHLY_START.
Awake! ("g") does NOT use a generator -- its frequency changed twice
(6/yr Feb-Dec even months 2016-17, 3/yr Mar/Jul/Nov 2018-21, 1/yr
2022-present), so a per-year count alone can't derive correct
issue=YYYYMM codes. Instead AWAKE_BACK_ISSUES (v4, new) hard-codes the
full 2016-2025 back-issue list (28 issues) -- each one individually
confirmed live against GETPUBMEDIALINKS (HTTP 200 + EPUB file present)
before being added, same bar as everything else in this file. The
frequency changes were independently corroborated by Wikipedia's Awake!
article ("As of January 2016, it was published every two months and
was further reduced to three issues per year as of January 2018. In
2022, publication was reduced to one new issue per year") -- matches
our live results exactly. Titles sourced from jw.org's own magazine
pages. See AWAKE_BACK_ISSUES below for the full list and how to extend
it when a new issue comes out.
Public Watchtower ("wp", v5, new): full back-issue list now implemented,
same spirit as Awake!'s but with THREE eras instead of two (jw.org/
Wikipedia's own publishing history, confirmed live against
GETPUBMEDIALINKS issue-by-issue for every month below):
  2016-2017: bi-monthly, ODD months only (Jan/Mar/May/Jul/Sep/Nov).
  2018-2021: 3/year, Jan/May/Sep only.
  2022-present: 1/year, an irregular month that changes every year
    (2022 May, 2023 May, 2024 Jul, 2025 Sep, 2026 Sep so far) -- exactly
    like Awake!, no formula, so WP_ANNUAL_ISSUES hard-codes each year's
    real month, individually confirmed live, same bar as AWAKE_BACK_ISSUES.
No EPUB exists before Jan 2016 (confirmed 404 for 2015 dates) -- same
floor as "w"/"mwb".
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse

# ---------------------------------------------------------------------------
# Plugin identity and capability flags
# ---------------------------------------------------------------------------

PLUGIN_NAME = "JW.org"

# SUPPORTS_MANUAL_CODE tells main.py to show a Y-button code-entry screen.
# This is distinct from SUPPORTS_SEARCH (gutenberg_fetch.py): we're not
# filtering a catalog, we're doing a direct live lookup of one specific
# exact code the person already knows -- for publications not in the
# curated STATIC_PUBLICATIONS list below. The on-validate path checks the
# code against the live API BEFORE leaving the entry screen, so a typo
# shows a clear error and lets the person fix it immediately rather than
# bouncing to the results list with nothing in it.
SUPPORTS_MANUAL_CODE = True

# SUPPORTS_CATEGORIES tells main.py to show a category picker (see
# CATEGORIES above) before the browse list, instead of dumping the whole
# catalog at once -- Kaleb's request, since the full catalog spans very
# different kinds of publications (Bibles, tracts, periodicals...).
# Selecting a category calls list_items(category=...); search (Y) still
# works as normal, scoped to whichever category is currently open.
SUPPORTS_CATEGORIES = True

# Shown on-screen under the manual-code input box. main.py reads this via
# getattr() so it's optional/plugin-owned -- main.py's text-entry code has
# no JW-specific knowledge, keeping concerns cleanly separated.
# Codes here are all verified LIVE against the real API (same standard as
# STATIC_PUBLICATIONS -- nothing is guessed or assumed).
#
# Awake! GOTCHA worth remembering: its "issue" is a real YYYYMM release
# month, but the on-site "No. N YYYY" label does NOT map to that year/month
# directly. Confirmed live: "Awake! No. 1 2025" is actually issue=202511
# (November 2025), not 202501. Since Awake! only publishes ~1x/year now
# (irregular timing), there's no reliable way to guess its current issue.
# Manual code entry with a known issue is the practical approach for now.
# To find the right issue= value, check jw.org/en/library/magazines/ and
# look at the download links for the specific issue you want.
MANUAL_CODE_HINT = ("Format: CODE SPACE YYYYMM  |  e.g. w 202001 = Jan 2020 Study WT  |  "
                     "e.g. mwb 201806 = Jun 2018 Workbook  |  e.g. g 202511 = Awake! No. 1 2025  |  "
                     "e.g. g 202411 = Awake! No. 1 2024")
# Was the abbreviation-style "w=Watchtower g=Awake! mwb=Workbook es=Daily
# Text" -- didn't communicate that a SPACE + YYYYMM issue is required for
# periodicals (Kaleb couldn't tell from it what to actually type). Now
# shows one full worked example per format, plus TWO Awake! examples since
# its issue number is the least intuitive (see GOTCHA above -- "No. 1
# YYYY" is issue YYYY11, i.e. released in November of the SAME labeled
# year, not January or the prior year as you'd guess). Both g 202511
# (2025) and g 202411 (2024) verified live against GETPUBMEDIALINKS
# (real EPUB returned for each, confirmed via jw.org's own download links
# AND a direct API call, not guessed from the pattern of a single data
# point). A third, g 202311 (Awake! No. 1 2023, "Can Our Planet
# Survive?"), is also live-verified and available if a 2023 example is
# ever wanted instead/in addition -- not included here yet to keep this
# hint from growing past what fits comfortably above the keyboard grid.
# Verified this still wraps cleanly (all words visible, no dropped/
# clipped text) and the on-screen keyboard grid still fits below it at
# every Font Size step 14-32pt on the code-entry screen in main.py.

# ---------------------------------------------------------------------------
# API configuration
# ---------------------------------------------------------------------------

# JW.org's own public media API -- the same endpoint their official apps
# use. No authentication required, but this is not a documented public API;
# use it respectfully (reasonable timeouts, no hammering).
# Reference: confirmed via network inspection of official JW apps.
API_BASE = "https://b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"

# v0.1.106: jw.org's own "mediator" API -- what the site's front-end
# itself calls to populate a video category page (e.g. the JW
# Broadcasting nav link is really just a client-side route,
# #en/categories/VODStudio, backed by this endpoint -- confirmed via
# direct fetch of that page: the static HTML has no video listing at
# all, just nav chrome, because the real list loads from here). Same
# jw-cdn.org domain as API_BASE above, still jw.org's own
# infrastructure, not a third party. Category key confirmed live:
# StudioMonthlyPrograms is JW Broadcasting's monthly programs list,
# newest first, 65 items as of this writing, each with a naturalKey
# (e.g. "pub-jwb-139_E_1_VIDEO") and a flat "files" list (not grouped
# by track under files[LANG][MP4] the way GETPUBMEDIALINKS is) -- one
# entry per quality, already exactly what's needed to build a
# downloadable item without a second API call.
MEDIATOR_CATEGORY_URL = "https://b.jw-cdn.org/apis/mediator/v1/categories/{lang}/{key}"

# RSS feed used to detect the actual latest Watchtower/Workbook issue.
# This is a publicly available feed linked from jw.org itself. We parse
# the title strings to extract month/year and convert to YYYYMM issue codes.
WHATS_NEW_RSS = "https://www.jw.org/en/whats-new/rss/WhatsNewWebArticles/feed.xml"
# v0.1.105: jw.org renamed this feed (was .../WhatsNewArticles/feed.xml).
# Found because Kaleb pulled the live feed directly and its <link>/
# self-referencing atom:link both showed "WhatsNewWebArticles" instead of
# our old "WhatsNewArticles" -- confirmed live: old URL now 404s, new URL
# is a real 200 with real items. This had been silently breaking
# check_new_issues() (falls back to current_issue_guess() on any
# failure, so it never surfaced as an error -- just quietly stopped
# finding the real current issue).

# v0.1.107: jw.org's general news feed -- Governing Body Update videos
# are published as NEWS RELEASES (jw.org/en/news/region/global/...),
# not filed under the Video Library category tree at all (checked --
# no dedicated category for them there). Confirmed live this feed does
# carry them (title starts "NEWS RELEASES | <year> Governing Body
# Update #N").
NEWS_RSS = "https://www.jw.org/en/news/rss/FullNewsRSS/feed.xml"

REQUEST_TIMEOUT = 15
USER_AGENT = "PicoReader/1.0 (muOS EPUB reader; personal, non-commercial)"

# Language code used in all API calls. "E" = English.
# The API accepts standard two-letter codes for other languages.
LANG = "E"

# ---------------------------------------------------------------------------
# Publication catalog
# ---------------------------------------------------------------------------

# Category names, in menu order -- Kaleb's requested grouping.
# v0.1.89: CATEGORY_WHATS_NEW restores the RSS "scan for recent
# publications" view that became unreachable once SUPPORTS_CATEGORIES
# routing was added (main.py's open_downloader() always sends this
# plugin straight to the category picker now, so the old flat
# category=None view -- where every RSS-detected "(new)" issue across
# every category surfaced together -- never got called anymore). The
# RSS detection itself (check_new_issues()) was never removed; it just
# lost its only UI entry point. This pseudo-category is a real entry in
# CATEGORIES so it shows up in the normal picker, but list_items()
# special-cases it below to return ONLY the RSS-detected "(new)" hits,
# across every category, instead of one category's full catalog.
CATEGORY_WHATS_NEW = "What's New (RSS)"
CATEGORY_BIBLES = "Bibles"
CATEGORY_BOOKS = "Books & Brochures"
CATEGORY_TRACTS = "Tracts"
CATEGORY_WATCHTOWER = "Watchtower (Public & Study)"
CATEGORY_AWAKE = "Awake!"
CATEGORY_WORKBOOKS = "Meeting Workbooks"
# v0.1.110: CATEGORY_VIDEOS is a pseudo-category, same principle as
# CATEGORY_WHATS_NEW -- a real entry in CATEGORIES so it shows up in the
# normal category picker. Moved here per Kaleb: the four video features
# (Enjoy Life Forever, JW Broadcasting, Governing Body Updates, The Good
# News According to Jesus) used to each be their own separate line in
# the Library popup menu, cluttering it -- now they're one "Videos"
# entry that opens a small sub-picker (main.py's
# SCREEN_DOWNLOAD_VIDEO_SOURCES / draw_download_video_sources()).
# Doesn't route through list_items() below at all -- main.py
# special-cases selecting it.
CATEGORY_VIDEOS = "Videos"
CATEGORIES = [CATEGORY_WHATS_NEW, CATEGORY_BIBLES, CATEGORY_BOOKS, CATEGORY_TRACTS,
              CATEGORY_WATCHTOWER, CATEGORY_AWAKE, CATEGORY_WORKBOOKS, CATEGORY_VIDEOS]

# Fixed-code publications that don't need an issue parameter.
# Format: (pub_code, display_title, extra_params_dict_or_None, category)
# extra_params: passed directly to GETPUBMEDIALINKS alongside pub= and
# langwritten=. Some publications (e.g. the plain NWT) need fileformat=EPUB
# explicitly or the API returns a 400 error -- see _resolve_download_url()
# and lookup_pub_code() for the retry logic that handles this.
# ALL codes here were verified LIVE before being added. Titles for the
# codes below sourced from wol.jw.org's official "Abbreviations of
# Publication Titles" page (https://wol.jw.org/en/wol/d/r1/lp-e/1200270068)
# and jw.org's Tracts & Invitations page (https://www.jw.org/en/library/tracts/).
STATIC_PUBLICATIONS = [
    ("nwt",   "New World Translation (2013 Revision)", {"fileformat": "EPUB"}, CATEGORY_BIBLES),
    ("bi12",  "New World Translation (1984 Edition)", None, CATEGORY_BIBLES),
    ("lffi",  "Enjoy Life Forever! -- Introductory Bible Lessons", None, CATEGORY_BOOKS),
    ("lff",   "Enjoy Life Forever! -- An Interactive Bible Course", None, CATEGORY_BOOKS),
    ("sjjls", '"Sing Out Joyfully" to Jehovah', None, CATEGORY_BOOKS),
    ("od",    "Organized to Do Jehovah's Will", None, CATEGORY_BOOKS),
    ("wcg",   "Walk Courageously With God", None, CATEGORY_BOOKS),
    ("lfb",   "Lessons You Can Learn From the Bible", None, CATEGORY_BOOKS),
    ("jy",    "Jesus -- The Way, the Truth, the Life", None, CATEGORY_BOOKS),
    ("cl",    "Draw Close to Jehovah", None, CATEGORY_BOOKS),
    ("rr",    "Pure Worship of Jehovah -- Restored At Last!", None, CATEGORY_BOOKS),
    # -- added per Kaleb's request --
    ("be",    "Benefit From Theocratic Ministry School Education", None, CATEGORY_BOOKS),
    ("cf",    '"Come Be My Follower"', None, CATEGORY_BOOKS),
    ("jd",    "Live With Jehovah's Day in Mind", None, CATEGORY_BOOKS),
    ("ia",    "Imitate Their Faith", None, CATEGORY_BOOKS),
    ("jr",    "God's Word for Us Through Jeremiah", None, CATEGORY_BOOKS),
    ("bt",    '"Bearing Thorough Witness" About God\'s Kingdom', None, CATEGORY_BOOKS),
    ("mbs",   "Memorial Bible Reading Schedule", None, CATEGORY_BOOKS),
    ("yb11",  "2011 Yearbook of Jehovah's Witnesses", None, CATEGORY_BOOKS),
    ("yb12",  "2012 Yearbook of Jehovah's Witnesses", None, CATEGORY_BOOKS),
    ("yb13",  "2013 Yearbook of Jehovah's Witnesses", None, CATEGORY_BOOKS),
    ("yb14",  "2014 Yearbook of Jehovah's Witnesses", None, CATEGORY_BOOKS),
    ("yb15",  "2015 Yearbook of Jehovah's Witnesses", None, CATEGORY_BOOKS),
    ("yb16",  "2016 Yearbook of Jehovah's Witnesses", None, CATEGORY_BOOKS),
    ("yb17",  "2017 Yearbook of Jehovah's Witnesses", None, CATEGORY_BOOKS),
    # Tracts -- these are short (a few pages) and jw.org may only offer
    # some of them as PDF rather than EPUB; if a download fails here,
    # that's most likely why (not a bug in this plugin).
    ("t-ftr", "Can We Enjoy Life Forever?", None, CATEGORY_TRACTS),
    ("t-fam", "How Can You Have a Happy Family?", None, CATEGORY_TRACTS),
    ("t-god", "Who Is the True God?", None, CATEGORY_TRACTS),
    ("t-pry", "Is Anyone Listening to Our Prayers?", None, CATEGORY_TRACTS),
    ("t-jss", "Does Jesus' Advice Work Today?", None, CATEGORY_TRACTS),
    ("t-kng", "How Will God's Kingdom Solve Our Problems?", None, CATEGORY_TRACTS),
    ("t-sfr", "Is Living Without Pain or Sadness Possible?", None, CATEGORY_TRACTS),
    ("t-dth", "Will You Ever See Your Loved Ones Who Have Died?", None, CATEGORY_TRACTS),
    ("t-rlg", "Do All Religions Please God?", None, CATEGORY_TRACTS),
]

# Periodicals that need an `issue=YYYYMM` parameter.
# For these, we try the RSS feed first (most accurate), then fall back to
# a same-month guess via current_issue_guess(). The daily text (es) is a
# special case: its code is year-specific (es26 for 2026, es27 for 2027)
# rather than using an issue parameter, so it's handled separately below.
# Format: (pub_code, display_title, category)
# "wp" (public Watchtower) and "g" (Awake!) confirmed live on jw.org's own
# magazines page (https://www.jw.org/en/library/magazines/) -- both now
# publish only ~1x/year (public Watchtower reduced to 1 issue/year as of
# 2022; Awake! has published irregularly, ~1x/year, for a while).
#
# Historical EPUB availability (verified live against GETPUBMEDIALINKS,
# not guessed): "w" and "mwb" resolve for issue=YYYYMM back to January
# 2016 (w_E_201601, mwb_E_201601 both confirmed) but 404 for 2015 and
# earlier (w_E_201501, w_E_201510, w_E_201512, mwb_E_201512 all tried and
# failed) -- EPUB format for these two periodicals doesn't appear to
# exist before 2016. "g" and "wp" issue dates can't be reliably guessed
# at all (their real publish months are irregular) -- use the manual
# pub-code entry (Y Enter Code) with a specific known issue instead of
# relying on the "this month, guess" fallback for those two.
PERIODICALS = [
    ("w",   "Watchtower -- Study Edition", CATEGORY_WATCHTOWER),
    ("wp",  "Watchtower -- Public Edition", CATEGORY_WATCHTOWER),
    ("g",   "Awake!", CATEGORY_AWAKE),
    ("mwb",  "Meeting Workbook", CATEGORY_WORKBOOKS),
    # "mwbr" (found on jw.org's Meeting Workbooks library page) could NOT
    # be verified live -- tried 8+ plausible issue=YYYYMM guesses against
    # the real GETPUBMEDIALINKS API (including current/recent months) and
    # every one 404'd. Either it needs a different issue-code convention
    # than mwb, or it isn't downloadable this way at all. Left commented
    # out until confirmed -- this catalog's own standard is "verified
    # LIVE before being added," and this doesn't meet that bar yet.
    # ("mwbr", "References for Life and Ministry Meeting Workbook", CATEGORY_WORKBOOKS),
    ("es",  "Examining the Scriptures Daily (current year)", CATEGORY_BOOKS),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_json(url):
    """Fetch a URL and parse the response as JSON.
    Raises urllib.error.URLError, TimeoutError, ValueError, or OSError --
    callers handle these. Same pattern as gutenberg_fetch.py."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _extract_epub(data):
    """Pull the first EPUB entry out of a GETPUBMEDIALINKS response.

    The API response structure is:
      data["files"][LANG]["EPUB"] -> list of file objects
    Each file object has a ["file"]["url"] we can download.
    Returns None if the path doesn't exist or the list is empty -- the
    caller decides what to do (usually retry with fileformat=EPUB)."""
    try:
        epubs = data["files"][LANG]["EPUB"]
    except (KeyError, TypeError):
        return None
    if not epubs:
        return None
    return epubs[0]


def _wp_valid_issue(issue):
    """Rounds an arbitrary YYYYMM guess down to the nearest ACTUAL valid
    Public Watchtower issue month, using the same era rules
    generate_wp_back_issues() models (bi-monthly 2016+, tri-annual
    2018+, annual-with-irregular-month 2022+ per WP_ANNUAL_ISSUES).
    Needed for the same reason _mwb_valid_issue() is: current_issue_
    guess() just returns "this calendar month", which is wrong for wp
    almost every month once it went annual with a hard-coded, irregular
    per-year month. If the current year's issue isn't in WP_ANNUAL_
    ISSUES yet (not published/confirmed), falls back to the most recent
    year that IS in the table."""
    y, m = int(issue[:4]), int(issue[4:6])
    if (y, m) >= WP_ANNUAL_START:
        candidates = [yy for yy in WP_ANNUAL_ISSUES if yy < y or (yy == y and WP_ANNUAL_ISSUES[yy] <= m)]
        py = max(candidates) if candidates else max(WP_ANNUAL_ISSUES)
        return f"{py}{WP_ANNUAL_ISSUES[py]:02d}"
    elif (y, m) >= WP_TRIANNUAL_START:
        for mm in (9, 5, 1):
            if m >= mm:
                return f"{y}{mm:02d}"
        return f"{y - 1}09"
    else:
        if m % 2 == 0:
            m -= 1  # always valid: m was 2-12 (even), so m-1 is 1-11 (odd)
        return f"{y}{m:02d}"


def _g_valid_issue(_issue=None):
    """Best available guess for Awake!'s current issue. Unlike mwb/wp,
    there's no formula to derive this from -- Awake! now publishes
    roughly once a year at an irregular month with no pattern (see
    AWAKE_BACK_ISSUES) -- so current_issue_guess()'s calendar-month
    guess would be wrong almost every month of the year. Simplest
    correct answer: the newest confirmed entry already in
    AWAKE_BACK_ISSUES (list is newest-first). Ignores its argument;
    kept for the same call signature as _mwb_valid_issue()/
    _wp_valid_issue() so all three can be dispatched identically."""
    return AWAKE_BACK_ISSUES[0][0]


def current_issue_guess():
    """This month as YYYYMM -- a fallback issue code for periodicals when
    the RSS feed can't be reached. JW.org typically publishes a month or
    two ahead of the calendar, so this guess may be one issue behind the
    actual latest. check_new_issues() via RSS is preferred when available."""
    return time.strftime("%Y%m")


def current_year_es_code():
    """Returns the pub code for this year's daily text booklet.
    The pattern (confirmed live) is "es" + 2-digit year: es26 for 2026,
    es27 for 2027, etc. Unlike other periodicals, this doesn't use an
    issue= parameter -- the year is baked into the pub code itself."""
    return "es" + time.strftime("%y")


# Earliest confirmed-live EPUB issue for "w" (Study Watchtower) -- see the
# PERIODICALS comment above: w_E_201601 confirmed reachable, w_E_201512
# confirmed 404. Safe to generate every month from here to "now" because
# "w" has published monthly with NO gaps or frequency changes across this
# entire range (confirmed live).
EARLIEST_MONTHLY_ISSUE = (2016, 1)

# Pubs safe for generate_monthly_back_issues() -- i.e. confirmed monthly
# with zero gaps/frequency changes since EARLIEST_MONTHLY_ISSUE. Maps
# pub code -> display title. "mwb" is deliberately NOT here -- it
# changed frequency in 2021 (see generate_mwb_back_issues() below) and
# needs its own generator. Do NOT add "g"/"wp" either without first
# confirming their exact per-year issue months (count/year alone isn't
# enough -- see MANUAL_CODE_HINT/GOTCHA above for why).
MONTHLY_BACK_ISSUE_PUBS = {
    "w": "Watchtower -- Study Edition",
}

# Awake! ("g") back issues, 2016-2025 -- hard-coded, NOT generated, because
# Awake!'s publishing frequency changed twice in this range (see the
# BACK-ISSUES note in the module docstring above for the full history).
# Every (issue, title) pair below was individually confirmed live against
# GETPUBMEDIALINKS (HTTP 200 + a real EPUB file present in the response)
# before being added -- same verification bar as STATIC_PUBLICATIONS.
# Topic titles sourced from jw.org's own magazine library pages
# (jw.org/en/library/magazines/awake-noN-YYYY-month/) to match each
# issue number to its real subject.
# Newest first. To add a new issue when one is released:
#   1) find its real month from jw.org/en/library/magazines/
#   2) confirm issue=YYYYMM returns HTTP 200 with an EPUB file via
#      GETPUBMEDIALINKS (same two-step check used for every row here)
#   3) only then add the row below.
AWAKE_BACK_ISSUES = [
    ("202511", "No. 1 2025 -- Coping With Rising Prices"),
    ("202411", "No. 1 2024 -- What Has Happened to Respect?"),
    ("202311", "No. 1 2023 -- Can Our Planet Survive?--Reasons for Hope"),
    ("202207", "No. 1 2022 -- A World in Turmoil--How You Can Cope"),
    ("202111", "No. 3 2021 -- Should You Believe in a Creator?--You Decide"),
    ("202107", "No. 2 2021 -- Technology--Your Master or Your Servant?"),
    ("202103", "No. 1 2021 -- Wisdom for Life and Happiness"),
    ("202011", "No. 3 2020 -- Is There a Cure for Prejudice?"),
    ("202007", "No. 2 2020 -- 5 Questions About Suffering Answered"),
    ("202003", "No. 1 2020 -- Find Relief From Stress"),
    ("201911", "No. 3 2019 -- Can the Bible Make Your Life Better?"),
    ("201907", "No. 2 2019 -- Six Lessons Children Need to Learn"),
    ("201903", "No. 1 2019 -- Will We Ever Feel Safe and Secure?"),
    ("201811", "No. 3 2018 -- Help for Those Who Grieve"),
    ("201807", "No. 2 2018 -- 12 Secrets of Successful Families"),
    ("201803", "No. 1 2018 -- The Way of Happiness"),
    ("201712", "No. 6 2017 -- Is the World out of Control?"),
    ("201710", "No. 5 2017 -- When Disaster Strikes"),
    ("201708", "No. 4 2017 -- Are You Doing Too Much?"),
    ("201706", "No. 3 2017 -- Is the Bible Really From God?"),
    ("201704", "No. 2 2017 -- What Is Behind the Supernatural?"),
    ("201702", "No. 1 2017 -- Teen Depression--Why? What Can Help?"),
    ("201612", "No. 6 2016 -- Disease--How to Reduce the Risk"),
    ("201610", "No. 5 2016 -- Did Jesus Really Exist?"),
    ("201608", "No. 4 2016 -- How to Harness Your Habits"),
    ("201606", "No. 3 2016 -- Breaking the Language Barrier"),
    ("201604", "No. 2 2016 -- Is the Bible Just a Good Book?"),
    ("201602", "No. 1 2016 -- Attitude Makes a Difference!"),
]


def _month_range_desc(start_year, start_month, end_year, end_month):
    """Yields (year, month) tuples from (end_year, end_month) back down to
    (start_year, start_month) inclusive, descending (newest first) -- the
    order back-issue lists should display in."""
    y, m = end_year, end_month
    while (y, m) >= (start_year, start_month):
        yield (y, m)
        m -= 1
        if m == 0:
            m = 12
            y -= 1


def generate_monthly_back_issues(pub, newest_issue=None):
    """Full back-issue list, one per month, from EARLIEST_MONTHLY_ISSUE
    (Jan 2016) up to newest_issue (defaults to this month via
    current_issue_guess() if not given -- pass the RSS-confirmed issue
    from check_new_issues() when available for accuracy).
    pub must be a key in MONTHLY_BACK_ISSUE_PUBS ("w" currently) --
    raises ValueError otherwise, since this generation strategy is only
    safe for pubs confirmed monthly with no gaps (see comment above
    MONTHLY_BACK_ISSUE_PUBS)."""
    if pub not in MONTHLY_BACK_ISSUE_PUBS:
        raise ValueError(f"generate_monthly_back_issues: {pub!r} is not confirmed "
                          f"monthly-safe (only {sorted(MONTHLY_BACK_ISSUE_PUBS)} are)")
    title_base = MONTHLY_BACK_ISSUE_PUBS[pub]
    if newest_issue:
        ny, nm = int(newest_issue[:4]), int(newest_issue[4:6])
    else:
        guess = current_issue_guess()
        ny, nm = int(guess[:4]), int(guess[4:6])
    items = []
    months_full = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    for y, m in _month_range_desc(EARLIEST_MONTHLY_ISSUE[0], EARLIEST_MONTHLY_ISSUE[1], ny, nm):
        issue = f"{y}{m:02d}"
        items.append({
            "title":    f"{title_base} ({months_full[m - 1]} {y})",
            "subtitle": f"pub: {pub}  issue: {issue}",
            "filename": f"{pub}_{LANG}_{issue}.epub",
            "_pub":     pub,
            "_extra":   {"issue": issue},
        })
    return items


# Meeting Workbook ("mwb") frequency CHANGED in 2021 -- Kaleb caught this
# after testing: it was NOT monthly the whole way back to 2016 like "w"
# is. Live-verified directly against GETPUBMEDIALINKS (not guessed):
#   2016-01 through 2020-12: every month has a real issue (12/year).
#   2021-01 onward: each workbook spans TWO months -- only odd months
#     (Jan/Mar/May/Jul/Sep/Nov) have a real issue; even months 404
#     (spot-checked 202102/202104/202106/202108/202110/202112, all 404,
#     and 202202/202204/202402 also 404, confirming the pattern holds
#     through at least 2024). The transition is a clean year boundary --
#     202101 is odd/real, 202012 (the month before) is real too (still
#     in the monthly era).
# generate_monthly_back_issues() would have generated a bogus even-month
# entry for every year 2021+ that 404s if selected -- this dedicated
# generator models both eras correctly instead.
MWB_BIMONTHLY_START = (2021, 1)


def _mwb_valid_issue(issue):
    """Rounds an arbitrary YYYYMM guess down to the nearest valid Meeting
    Workbook issue month -- i.e. in the bi-monthly era (2021+, see
    MWB_BIMONTHLY_START) an even month isn't a real issue, so step back
    one month to the preceding (valid, odd) one. Needed because
    current_issue_guess() just returns "this calendar month", which is
    wrong for mwb roughly half the time since the 2021 frequency change."""
    y, m = int(issue[:4]), int(issue[4:6])
    if (y, m) >= MWB_BIMONTHLY_START and m % 2 == 0:
        m -= 1  # always valid: m was 2-12 (even), so m-1 is 1-11 (odd), same year
    return f"{y}{m:02d}"


def generate_mwb_back_issues(newest_issue=None):
    """Full Meeting Workbook back-issue list, monthly from Jan 2016
    through Dec 2020, then odd-months-only (bi-monthly) from Jan 2021
    onward -- see MWB_BIMONTHLY_START comment above for why. newest_issue
    defaults to this month via current_issue_guess() if not given (pass
    the RSS-confirmed issue from check_new_issues() when available)."""
    if newest_issue:
        ny, nm = int(newest_issue[:4]), int(newest_issue[4:6])
    else:
        guess = current_issue_guess()
        ny, nm = int(guess[:4]), int(guess[4:6])
    items = []
    months_full = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    for y, m in _month_range_desc(EARLIEST_MONTHLY_ISSUE[0], EARLIEST_MONTHLY_ISSUE[1], ny, nm):
        if (y, m) >= MWB_BIMONTHLY_START and m % 2 == 0:
            continue  # even month in the bi-monthly era -- not a real issue
        issue = f"{y}{m:02d}"
        items.append({
            "title":    f"Meeting Workbook ({months_full[m - 1]} {y})",
            "subtitle": f"pub: mwb  issue: {issue}",
            "filename": f"mwb_{LANG}_{issue}.epub",
            "_pub":     "mwb",
            "_extra":   {"issue": issue},
        })
    return items


# Public Watchtower ("wp") back-issue eras -- see BACK-ISSUES note in the
# module docstring for the full history and how each boundary/month was
# confirmed. Three distinct eras, oldest to newest:
WP_BIMONTHLY_START = (2016, 1)   # odd months only: Jan/Mar/May/Jul/Sep/Nov
WP_TRIANNUAL_START = (2018, 1)   # Jan/May/Sep only
WP_ANNUAL_START = (2022, 1)      # 1/year, month varies -- see table below

# One issue per year from 2022 on -- month is irregular (like Awake!'s
# "No. 1" issue), so it can't be derived and must be hard-coded. Each
# entry individually confirmed live via GETPUBMEDIALINKS before being
# added, same bar as AWAKE_BACK_ISSUES. To add a new year: find the month
# from jw.org/en/library/magazines/, confirm issue=YYYYMM returns a real
# EPUB, then add the row.
WP_ANNUAL_ISSUES = {
    2022: 5,
    2023: 5,
    2024: 7,
    2025: 9,
    2026: 9,
}


def generate_wp_back_issues(newest_issue=None):
    """Full Public Watchtower back-issue list, Jan 2016 through newest_issue
    (defaults to this month via current_issue_guess() if not given -- pass
    the RSS-confirmed issue from check_new_issues() when available).
    Models all three publishing eras -- see the constants above and the
    module docstring's BACK-ISSUES note for how each was confirmed."""
    if newest_issue:
        ny, nm = int(newest_issue[:4]), int(newest_issue[4:6])
    else:
        guess = current_issue_guess()
        ny, nm = int(guess[:4]), int(guess[4:6])
    items = []
    months_full = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    for y, m in _month_range_desc(WP_BIMONTHLY_START[0], WP_BIMONTHLY_START[1], ny, nm):
        if (y, m) >= WP_ANNUAL_START:
            if y not in WP_ANNUAL_ISSUES or m != WP_ANNUAL_ISSUES[y]:
                continue
        elif (y, m) >= WP_TRIANNUAL_START:
            if m not in (1, 5, 9):
                continue
        else:
            if m % 2 == 0:
                continue  # even month in the bi-monthly era -- not a real issue
        issue = f"{y}{m:02d}"
        items.append({
            "title":    f"Watchtower -- Public Edition ({months_full[m - 1]} {y})",
            "subtitle": f"pub: wp  issue: {issue}",
            "filename": f"wp_{LANG}_{issue}.epub",
            "_pub":     "wp",
            "_extra":   {"issue": issue},
        })
    return items


def check_new_issues():
    """Parse the jw.org What's New RSS feed to find the actual latest
    Watchtower Study Edition and Meeting Workbook issue codes.

    Why RSS instead of just guessing? JW.org publishes issues ahead of
    the calendar month, so same-month guessing is unreliable. The RSS
    feed titles contain the month and year ("THE WATCHTOWER-STUDY EDITION
    | September 2026"), which we convert to YYYYMM issue codes.

    Key gotcha: bi-monthly Workbook titles like "November-December 2026"
    must resolve to the FIRST month (mwb_E_202611, not 202612) -- that's
    the actual issue code confirmed live. The regex matches but discards
    the second month.

    Returns a list of (pub_code, title, issue_YYYYMM) tuples, deduplicated.
    Best-effort only: returns [] if the feed can't be reached -- never
    raises, so the calling code can always fall back to current_issue_guess()
    without extra error handling."""
    req = urllib.request.Request(WHATS_NEW_RSS, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []  # network failure -- caller falls back to guess

    # Build a month-name -> month-number lookup for all 12 months
    months = {m: i + 1 for i, m in enumerate([
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"])}
    month_re = "|".join(months.keys())

    found = {}
    for m in re.finditer(r"<title>(.*?)</title>", text, re.S):
        title = m.group(1).strip()
        # Match "Month YYYY" or "Month-Month YYYY" (bi-monthly), capture
        # only the first month. Unicode dashes (\u2013 en-dash, \u2014
        # em-dash) are included because RSS feeds sometimes use them.
        date_m = re.search(
            rf"({month_re})(?:[\s\u2013\u2014-]+(?:{month_re}))?\s+(\d{{4}})",
            title)
        if not date_m:
            continue
        mon, year = date_m.group(1), date_m.group(2)
        issue = f"{year}{months[mon]:02d}"
        if "WATCHTOWER" in title.upper() and "STUDY" in title.upper():
            key = ("w", issue)
            found[key] = title
        elif "WATCHTOWER" in title.upper():
            key = ("wp", issue)
            found[key] = title
        elif "AWAKE" in title.upper():
            key = ("g", issue)
            found[key] = title
        elif "WORKBOOK" in title.upper():
            key = ("mwb", issue)
            found[key] = title

    return [(pub, title, issue) for (pub, issue), title in found.items()]


# ---------------------------------------------------------------------------
# Required plugin functions
# ---------------------------------------------------------------------------

def list_items(query=None, page=1, category=None):
    """Build and return the catalog of available JW.org publications,
    optionally scoped to one category (see CATEGORIES) and/or filtered by
    a search query (simple case-insensitive substring match on title --
    the catalog is small and local, so no need for anything fancier).

    Unlike gutenberg_fetch.py, this doesn't call an API here -- the catalog
    is assembled locally from STATIC_PUBLICATIONS and PERIODICALS, with the
    RSS feed used only to determine the current periodical issue codes.
    The actual download URL is resolved lazily in download() via
    _resolve_download_url() -- we don't need it for the browse list.

    page is ignored: the catalog (even a single category) is small enough
    to show in full. has_next is always False.

    Catalog assembly order:
    1. Static publications (books, courses -- no issue needed)
    2. New issues found via RSS (labeled "(new)")
    3. Periodicals not already covered by RSS (labeled "(this month, guess)")
    4. Daily text (special case: year-specific pub code, no issue param)"""
    items = []

    # v0.1.110: CATEGORY_VIDEOS is routed straight to the video-source
    # picker (SCREEN_DOWNLOAD_VIDEO_SOURCES) by main.py before this
    # function is ever called -- it isn't a real publication grouping.
    # Defensive no-op only, in case a future caller reaches here anyway.
    if category == CATEGORY_VIDEOS:
        return [], False, None

    # v0.1.89: "What's New (RSS)" is a pseudo-category, not a real
    # publication grouping -- it returns ONLY what check_new_issues()
    # actually detected via RSS, across every category, and skips the
    # static-publications/guessed-periodical/back-issue steps below
    # entirely. This is the flat "what's actually new" view that existed
    # before SUPPORTS_CATEGORIES routing made it unreachable.
    if category == CATEGORY_WHATS_NEW:
        new_issues = check_new_issues()
        if not new_issues:
            return [], False, None
        for pub, title, issue in new_issues:
            items.append({
                "title":    f"{title} (new)",
                "subtitle": f"pub: {pub}  issue: {issue}",
                "filename": f"{pub}_{LANG}_{issue}.epub",
                "_pub":     pub,
                "_extra":   {"issue": issue},
            })
        if query:
            q = query.lower()
            items = [it for it in items if q in it["title"].lower()]
        return items, False, None

    # Step 1: static publications
    # These are books/courses that don't change issue-to-issue. The item
    # dict doesn't include a _download_url because we resolve it at download
    # time -- the URL can change and we want the freshest link each time.
    for pub, title, extra, cat in STATIC_PUBLICATIONS:
        if category and cat != category:
            continue
        items.append({
            "title":    title,
            "subtitle": f"pub: {pub}",
            "filename": f"{pub}_{LANG}.epub",
            "_pub":     pub,
            "_extra":   extra,   # passed to GETPUBMEDIALINKS at download time
        })

    # Step 2: RSS-detected new issues
    # If the feed is reachable, these are the actual currently-published
    # issues -- more accurate than guessing from the calendar.
    pub_to_category = {pub: cat for pub, _t, cat in PERIODICALS}
    new_issues = check_new_issues()
    if category:
        new_issues = [ni for ni in new_issues if pub_to_category.get(ni[0]) == category]
    covered = {(pub, issue) for pub, _t, issue in new_issues}
    for pub, title, issue in new_issues:
        items.append({
            "title":    f"{title} (new)",
            "subtitle": f"pub: {pub}  issue: {issue}",
            "filename": f"{pub}_{LANG}_{issue}.epub",
            "_pub":     pub,
            "_extra":   {"issue": issue},
        })

    # Step 3 & 4: periodicals not yet covered + daily text
    for pub, title, cat in PERIODICALS:
        if category and cat != category:
            continue
        if pub == "es":
            # Daily text: year-baked-into-code pattern (es26, es27, ...)
            code = current_year_es_code()
            items.append({
                "title":    title,
                "subtitle": f"pub: {code}",
                "filename": f"{code}_{LANG}.epub",
                "_pub":     code,
                "_extra":   None,
            })
            continue
        issue = current_issue_guess()
        if pub == "mwb":
            issue = _mwb_valid_issue(issue)
        elif pub == "wp":
            issue = _wp_valid_issue(issue)
        elif pub == "g":
            issue = _g_valid_issue(issue)
        if (pub, issue) in covered:
            continue  # already listed via RSS above -- don't duplicate
        items.append({
            "title":    f"{title} (this month, guess)",
            "subtitle": f"pub: {pub}  issue: {issue}",
            "filename": f"{pub}_{LANG}_{issue}.epub",
            "_pub":     pub,
            "_extra":   {"issue": issue},
        })

    # Step 5: full back-issue lists for pubs with a safe, verified
    # generator. Only generated when actually browsing that pub's own
    # category (not the "all categories" view) -- ~120 entries is fine
    # for THIS list (see main.py's draw_download_browse, which already
    # windows/scrolls rather than rendering everything), but would be
    # noise mixed into every other category's results. "wp"/"g"
    # deliberately excluded -- see MONTHLY_BACK_ISSUE_PUBS's comment for
    # why (count/year alone isn't enough to generate their issue months
    # safely).
    # Note: CATEGORY_WATCHTOWER holds BOTH "w" (Study) and "wp" (Public)
    # -- each needs its own back-issue pass below since they use
    # different generators/eras, unlike the 1:1 category:pub mapping this
    # dict used to be.
    category_pubs = {
        CATEGORY_WATCHTOWER: ("w", "wp"),
        CATEGORY_WORKBOOKS:  ("mwb",),
    }
    for pub in category_pubs.get(category, ()):
        newest = next((issue for p, _t, issue in new_issues if p == pub), None)
        covered = {(pub, newest)} if newest else set()
        # also skip the (this month, guess) entry from step 3/4 above, if
        # that's what ended up in the list instead of an RSS hit
        guess = current_issue_guess()
        if pub == "mwb":
            guess = _mwb_valid_issue(guess)
        elif pub == "wp":
            guess = _wp_valid_issue(guess)
        covered.add((pub, guess))
        if pub == "mwb":
            gen = generate_mwb_back_issues(newest_issue=newest)
        elif pub == "wp":
            gen = generate_wp_back_issues(newest_issue=newest)
        else:
            gen = generate_monthly_back_issues(pub, newest_issue=newest)
        for item in gen:
            issue = item["_extra"]["issue"]
            if (pub, issue) in covered:
                continue  # already listed above (new/guess) -- don't duplicate
            items.append(item)

    # Awake! ("g") back issues -- hard-coded list (AWAKE_BACK_ISSUES), not
    # a generator (see module docstring for why). Only shown when actually
    # browsing the Awake! category, same as w/mwb above -- 28 entries would
    # be noise mixed into every other category's results.
    if category == CATEGORY_AWAKE:
        covered_g = {("g", issue) for p, _t, issue in new_issues if p == "g"}
        covered_g.add(("g", _g_valid_issue()))
        for issue, title in AWAKE_BACK_ISSUES:
            if ("g", issue) in covered_g:
                continue  # already listed above (new/guess) -- don't duplicate
            items.append({
                "title":    title,
                "subtitle": f"pub: g  issue: {issue}",
                "filename": f"g_{LANG}_{issue}.epub",
                "_pub":     "g",
                "_extra":   {"issue": issue},
            })

    if query:
        q = query.strip().lower()
        items = [it for it in items if q in it["title"].lower()]

    return items, False, None


def lookup_pub_code(code, issue=None):
    """Manual pub-code lookup for publications NOT in STATIC_PUBLICATIONS.

    Called by main.py when the user confirms a code on the Y-button manual-
    entry screen. Unlike list_items(), this performs a LIVE API round-trip
    immediately -- the point is to catch typos on the entry screen with a
    clear error ("not found") rather than only failing later at download time.

    Two-attempt strategy (why it's needed):
      Some publications (confirmed: the plain NWT "nwt") return HTTP 400
      from GETPUBMEDIALINKS unless fileformat=EPUB is explicit. A single
      attempt without fileformat would always fail for these. So:
        Attempt 1: without fileformat (works for most pubs)
        Attempt 2: with fileformat=EPUB (fallback for pubs that need it)
      If attempt 1 raises HTTPError 400, we fall through to attempt 2
      rather than giving up. This was a real bug before being fixed: the
      original code returned on the first error and never reached the retry.

    Returns (item_dict, None) on success, (None, error_string) on failure."""
    code = (code or "").strip().lower()
    if not code:
        return None, "Enter a publication code"
    if len(code) > 40:
        return None, "That doesn't look like a publication code"

    params = {"pub": code, "langwritten": LANG, "output": "json"}
    if issue:
        params["issue"] = issue.strip()

    def _try(p):
        """One attempt at the API. Returns (data_dict, None) on success or
        (None, error_string) on failure. error_string "INVALID_CODE" is a
        sentinel meaning the API returned 400 (unknown pub code) -- distinct
        from a real network error so we can give a better message."""
        try:
            return _get_json(API_BASE + "?" + urllib.parse.urlencode(p)), None
        except urllib.error.HTTPError as e:
            if e.code == 400:
                # 400 means the pub code isn't recognized by the API
                # (confirmed live) -- NOT a network problem. We use
                # "INVALID_CODE" so the outer function can distinguish
                # "needs retry with fileformat=EPUB" from "bad code".
                return None, "INVALID_CODE"
            return None, f"Server error ({e.code})"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return None, f"Network error: {e}"
        except ValueError as e:
            return None, f"Bad response from server: {e}"

    # Attempt 1: no fileformat param
    data, err = _try(params)
    epub = _extract_epub(data) if isinstance(data, dict) else None

    if not epub:
        # Attempt 2: explicit fileformat=EPUB (fallback for pubs like NWT)
        retry_params = dict(params, fileformat="EPUB")
        data2, err2 = _try(retry_params)
        epub2 = _extract_epub(data2) if isinstance(data2, dict) else None
        if epub2:
            data, epub, err = data2, epub2, None
        elif err2 is None:
            # Retry got a real response but still no epub -- use its data
            # (more specific / informative) over the first attempt's result
            err, data = None, data2

    if not epub:
        if isinstance(data, dict) and data.get("pubName"):
            return None, f'"{data["pubName"]}" has no EPUB available'
        if err and err != "INVALID_CODE":
            return None, err
        return None, f'"{code}" not found (check the code and try again)'

    title = data.get("pubName", code)
    fname_suffix = f"_{issue.strip()}" if issue else ""
    return {
        "title":    title,
        "subtitle": f"pub: {code}" + (f"  issue: {issue.strip()}" if issue else ""),
        "filename": f"{code}_{LANG}{fname_suffix}.epub",
        "_pub":     code,
        "_extra":   ({"issue": issue.strip()} if issue else None),
    }, None


def _resolve_download_url(item):
    """Resolve the current EPUB download URL for an item at download time.

    WHY resolve at download time instead of storing the URL in list_items()?
    JW.org's CDN URLs are time-limited and can change between catalog builds
    and actual download. Calling GETPUBMEDIALINKS fresh at download time
    always gives us a valid, current URL.

    Constructs the API request from item["_pub"] and item["_extra"] (which
    carries the issue= param for periodicals, or fileformat=EPUB for pubs
    that need it). Returns (url_string, None) on success or (None, error)."""
    params = {"pub": item["_pub"], "langwritten": LANG, "output": "json"}
    if item.get("_extra"):
        params.update(item["_extra"])
    url = API_BASE + "?" + "&".join(
        f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return None, str(e)
    epub = _extract_epub(data)
    if not epub:
        return None, f'"{data.get("pubName", item["title"])}" has no EPUB available'
    return epub["file"]["url"], None


# ---------------------------------------------------------------------------
# Video downloads (v0.1.92)
# ---------------------------------------------------------------------------
# Separate from the EPUB catalog above: videos are looked up by pub code
# (e.g. "lffv" for Enjoy Life Forever videos) via the SAME GETPUBMEDIALINKS
# endpoint, just with fileformat=MP4 instead of EPUB. Confirmed live
# structure (real response inspected, not guessed):
#   data["files"][LANG]["MP4"] -> list of track objects, EACH TRACK
#   REPEATED ONCE PER RESOLUTION (e.g. same "track" number appears at
#   both "240p" and "720p" -- these are NOT duplicates, they're
#   different files for the same video). Each entry has:
#     "title"  -- human-readable video title (used for the saved filename)
#     "label"  -- resolution string, e.g. "240p", "480p", "720p"
#     "track"  -- track number (groups resolutions of the same video)
#     "file": {"url": ...}
#     "filesize" -- bytes
#
# Kaleb confirmed 480p plays back fine on the RG CubeXX-H (already tested
# via CTupe) and fits the 720x720 screen well -- so PREFERRED_VIDEO_LABEL
# below is "480p", falling back to the next closest if a given video
# doesn't have that rendition (not every video is transcoded at every
# resolution).
#
# Videos are saved with the real TITLE as the filename (sanitized), not
# the pub-code-based CDN filename (e.g. "lffv_E_011_r480P.mp4") -- so they
# sit sensibly alongside a person's other video files instead of showing
# a cryptic name. See _sanitize_video_filename().

PREFERRED_VIDEO_LABEL = "480p"
# Fallback order if the preferred label isn't available for a given track --
# closest-to-preferred first.
VIDEO_LABEL_FALLBACK = ["480p", "360p", "720p", "240p"]


def _sanitize_video_filename(title):
    """Turn a real video title into a safe filename. Strips characters
    that are risky across filesystems (/, :, ?, *, etc.) and JW.org's
    typographic punctuation (em dash, curly quotes), collapses repeated
    spaces, and trims to a sane length. Never returns an empty string --
    falls back to "video" if sanitizing would strip everything."""
    bad_chars = '/\\:*?"<>|'
    cleaned = "".join(c for c in title if c not in bad_chars)
    cleaned = cleaned.replace("\u2014", "-").replace("\u2013", "-")
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = " ".join(cleaned.split())  # collapse whitespace runs
    cleaned = cleaned.strip(" .")       # trailing dot/space breaks on some FSes
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rstrip()
    return cleaned or "video"


def _extract_video_tracks(data):
    """Group data["files"][LANG]["MP4"] entries by track number, picking
    ONE rendition per track per VIDEO_LABEL_FALLBACK order. Returns a
    list of dicts: {"title", "url", "label", "filesize", "track"}.
    Returns [] if the path doesn't exist (e.g. this pub has no videos)."""
    try:
        entries = data["files"][LANG]["MP4"]
    except (KeyError, TypeError):
        return []

    by_track = {}
    for entry in entries:
        track = entry.get("track")
        label = entry.get("label")
        by_track.setdefault(track, {})[label] = entry

    tracks = []
    for track, by_label in by_track.items():
        chosen = None
        for label in VIDEO_LABEL_FALLBACK:
            if label in by_label:
                chosen = by_label[label]
                break
        if chosen is None:  # unknown label naming -- just take any one
            chosen = next(iter(by_label.values()))
        try:
            url = chosen["file"]["url"]
        except (KeyError, TypeError):
            continue
        tracks.append({
            "title":    chosen.get("title", f"video_{track}"),
            "url":      url,
            "label":    chosen.get("label", "?"),
            "filesize": chosen.get("filesize", 0),
            "track":    track,
        })
    tracks.sort(key=lambda t: (t["track"] if t["track"] is not None else 0))
    return tracks


def check_new_gb_updates(limit=3):
    """v0.1.107: Kaleb asked about a Governing Body Updates category
    after list_broadcast_items(). These aren't in the Video Library
    category tree at all (checked VideoOnDemand's full subcategory
    list -- no dedicated key) -- they're published as NEWS RELEASES
    instead. Confirmed via Kaleb's own test link
    (finder?lank=docid-1112024061_1_VIDEO) that resolve_video_link()
    already handles the resolve step fine; what's new here is finding
    them in the first place.

    Pipeline: fetch NEWS_RSS, keep items whose title contains
    "Governing Body Update", then fetch each matching article page and
    extract its docid from the GETPUBMEDIALINKS URL jw.org embeds
    directly in the page for its own media (onurl="...GETPUBMEDIALINKS
    ?docid=NNNN...") -- confirmed this is a clean, unique target (the
    page also contains unrelated docid= links in the footer for
    Copyright/Terms/Privacy, so the regex specifically requires the
    GETPUBMEDIALINKS prefix to avoid grabbing those). Each docid then
    resolves through the existing _resolve_docid_video() -- same
    function the in-text docid video links already use.

    Returns (items, error_message) in the same shape as
    list_broadcast_items(). limit caps how many recent matching articles
    to fetch/resolve (each is a separate page fetch, so kept small)."""
    req = urllib.request.Request(NEWS_RSS, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            feed_text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return [], str(e)

    matches = []
    for it in re.finditer(r"<item>(.*?)</item>", feed_text, re.S):
        block = it.group(1)
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        if title_m and link_m and "Governing Body Update" in title_m.group(1):
            matches.append((title_m.group(1).strip(), link_m.group(1).strip()))
        if len(matches) >= limit:
            break
    if not matches:
        return [], "No Governing Body Update articles in the current feed window"

    items = []
    for _title, link in matches:
        req = urllib.request.Request(link, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                page = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        docid_m = re.search(r"GETPUBMEDIALINKS\?docid=(\d+)", page)
        if not docid_m:
            continue
        item, err = _resolve_docid_video(docid_m.group(1))
        if item:
            items.append(item)
    if not items:
        return [], "Found Governing Body Update articles but couldn't resolve any video"
    return items, None


def _list_mediator_category_items(category_key, default_title, limit=None):
    """v0.1.109: shared logic behind list_broadcast_items() and
    list_good_news_items() -- both just point this at a different
    MEDIATOR_CATEGORY_URL key. Pulled out once a second category
    (SeriesGoodNews) needed the exact same media-list-to-item-list
    conversion, rather than duplicating it a second time. Returns
    (items, error_message) in the shape ready for download_video():
    {"title", "subtitle", "filename", "_video_url", "track",
    "_published"}. No track-grouping needed (unlike GETPUBMEDIALINKS/
    _extract_video_tracks) -- each media entry already IS one specific
    video (naturalKey encodes it), with a flat per-quality "files" list."""
    url = MEDIATOR_CATEGORY_URL.format(lang=LANG, key=category_key)
    req = urllib.request.Request(url + "?detailed=1&clientType=www",
                                 headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return [], str(e)

    media = data.get("category", {}).get("media", [])
    if not media:
        return [], "No videos found"
    media.sort(key=lambda m: m.get("firstPublished", ""), reverse=True)
    if limit:
        media = media[:limit]

    items = []
    for m in media:
        files = m.get("files", [])
        by_label = {f.get("label"): f for f in files}
        chosen = next((by_label[l] for l in VIDEO_LABEL_FALLBACK if l in by_label), None)
        if chosen is None and files:
            chosen = files[0]
        if not chosen or not chosen.get("progressiveDownloadURL"):
            continue
        title = m.get("title", default_title)
        safe_name = _sanitize_video_filename(title)
        size_mb = chosen.get("filesize", 0) / (1024 * 1024) if chosen.get("filesize") else 0
        published = m.get("firstPublished", "")
        items.append({
            "title":       title,
            "subtitle":    f'{chosen.get("label","?")}  ~{size_mb:.0f} MB  ({published[:10]})',
            "filename":    f"{safe_name} ({chosen.get('label','?')}).mp4",
            "_video_url":  chosen["progressiveDownloadURL"],
            "track":       m.get("naturalKey"),
            "_published":  published,
        })
    return items, None


def list_broadcast_items(limit=12):
    """v0.1.106: Kaleb asked for a "check for new videos" feature; no
    dedicated official RSS feed exists for videos (the general
    WHATS_NEW_RSS feed doesn't reliably surface them -- checked a real
    snapshot, zero video items in it), so per Kaleb's direction this
    polls jw.org's own JW Broadcasting monthly-programs category
    directly instead (MEDIATOR_CATEGORY_URL, key="StudioMonthlyPrograms")
    -- confirmed this is what jw.org's own site itself fetches to
    populate that category page (the page's static HTML has no listing
    at all, it's a client-side route). Still 100% jw.org's own
    infrastructure (b.jw-cdn.org), not a third party. limit caps how
    many of the (currently 65) programs to return, newest first --
    Kaleb's interest is "what's new," not the full archive;
    list_video_items() remains the way to browse everything for a
    given pub. v0.1.109: logic moved into shared
    _list_mediator_category_items()."""
    return _list_mediator_category_items("StudioMonthlyPrograms", "JW Broadcasting", limit)


def list_good_news_items():
    """v0.1.109: Kaleb asked to add "The Good News According to Jesus"
    (the dramatized episode series about Jesus's life/teachings) as a
    category -- found via the same VideoOnDemand > Series category tree
    already explored for Governing Body Updates (SeriesGoodNews key).
    Confirmed live: 6 episodes as of this writing (pub "gnj"), e.g.
    Episode 1: "The True Light of the World". Small, slow-growing
    catalog (new episodes roughly a few times a year) -- no limit
    needed, just return all of them, newest first."""
    return _list_mediator_category_items("SeriesGoodNews", "The Good News According to Jesus")


def list_video_items(pub, issue=None):
    """Fetch and return the video catalog for a video pub code (e.g. "lffv")
    as a list of item dicts ready for main.py's download-list UI:
    {"title", "subtitle", "filename", "_video_url", "track"}.

    v0.1.101: added optional issue (YYYYMM string) -- monthly-broadcast
    pubs like "jwbai" 400 Bad Request without it. Confirmed live: pub=
    jwbai with no issue -> HTTP 400; pub=jwbai&issue=201507 -> resolves
    fine. One-off pubs (e.g. "lffv") don't use issue and ignore it if
    passed (the API param is simply omitted when issue is None).

    v0.1.94: two changes per Kaleb --
    (1) "(With Audio Descriptions)" tracks are separate real videos in
        the API (own track number, own file), not a variant flag -- but
        Kaleb doesn't want them cluttering the list, so they're filtered
        out here by title substring match.
    (2) filename now includes the resolution label, e.g.
        "Never Give Up Hope! (480p).mp4" -- so the label is visible
        directly in ROMS/movies without opening the file.

    Returns (items, error_message). error_message is None on success."""
    params = {"pub": pub, "langwritten": LANG, "fileformat": "MP4",
              "alllangs": "0", "output": "json"}
    if issue:
        params["issue"] = issue
    url = API_BASE + "?" + "&".join(
        f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return [], str(e)

    tracks = _extract_video_tracks(data)
    if not tracks:
        return [], f'"{pub}" has no videos available'

    items = []
    for t in tracks:
        if "with audio description" in t["title"].lower():
            continue  # v0.1.94: Kaleb doesn't want these in the list
        safe_name = _sanitize_video_filename(t["title"])
        size_mb = t["filesize"] / (1024 * 1024) if t["filesize"] else 0
        items.append({
            "title":       t["title"],
            "subtitle":    f'{t["label"]}  ~{size_mb:.0f} MB',
            "filename":    f"{safe_name} ({t['label']}).mp4",
            "_video_url":  t["url"],
            "track":       t["track"],  # v0.1.98: needed to match an
                                         # in-text "lank=pub-X_NN_VIDEO"
                                         # link back to the right item.
        })
    return items, None


_VIDEO_LINK_RE = re.compile(
    r"lank=pub-([A-Za-z0-9-]+)_(?:(\d{6})_)?(x|\d+)_VIDEO", re.IGNORECASE)
_VIDEO_DOCID_RE = re.compile(r"lank=docid-(\d+)_(\d+)_VIDEO", re.IGNORECASE)


def parse_video_link(href):
    """v0.1.98: does this in-text link (from epub_engine's kind="external"
    LinkSpan) point at a JW video? Formats confirmed via full scans of
    real epubs (wcg_E.epub: 43 links / 11 pub families; lff_E.epub: 430
    links / 14 pub families):
      - lffi_E.epub: "...finder?lank=pub-lffv_11_VIDEO&wtlocale=E"
        (pub + track, no issue)
      - wcg_E.epub: "...lank=pub-jwbai_201507_1_VIDEO..."
        (pub + 6-digit YYYYMM issue + track -- a monthly broadcast pub)
      - wcg_E.epub: "...lank=pub-jwb-102_7_VIDEO..." (pub code itself
        contains a HYPHEN -- JW Broadcasting's numbered-episode style)
      - v0.1.104, lff_E.epub: "...lank=pub-ivfa1_x_VIDEO..." (track is
        the literal letter "x", not a number -- confirmed live these are
        all single-video pubs, e.g. pub=ivfa1 has exactly one track
        regardless, so "x" means "there's only one, don't disambiguate")
      - v0.1.104, lff_E.epub: "...lank=docid-1112024020_1_VIDEO&ts=..."
        (a completely different addressing scheme -- by docid, not pub
        code -- confirmed the API accepts docid= as its own param,
        separate from pub=; the trailing ts=HH:MM:SS-HH:MM:SS is a
        play-range within the video, not a separate file, so we just
        download the whole video same as any other link)
    Returns (kind, pub_or_docid, issue, track):
      - kind="pub": normal case, pub_or_docid is the pub code, track is
        an int, or the literal string "x" for single-video pubs.
      - kind="docid": pub_or_docid is the docid string, issue/track None.
      - kind=None if href doesn't match any known video-link pattern.
    Does NOT hit the network -- just regex matching on the href string."""
    m = _VIDEO_DOCID_RE.search(href or "")
    if m:
        return "docid", m.group(1), None, None
    m = _VIDEO_LINK_RE.search(href or "")
    if not m:
        return None, None, None, None
    pub, issue, track = m.group(1), m.group(2), m.group(3)
    track = track if track.lower() == "x" else int(track)
    return "pub", pub, issue, track


def resolve_video_link(href):
    """v0.1.98: full resolve for an in-text video link -- parse_video_link()
    then one GETPUBMEDIALINKS call to find the actual video. Returns
    (item, error_message); item is a dict from list_video_items() (or an
    equivalent one built from a docid lookup) ready for download_video(),
    or None on failure.

    v0.1.104: branches on parse_video_link()'s new "kind":
      - "docid": a completely different lookup (GETPUBMEDIALINKS?docid=
        instead of pub=) -- confirmed live this returns its own
        self-contained file list, no separate pub/track matching needed.
      - "pub" with track="x": confirmed live these pubs have exactly one
        video regardless of track number, so just take the first/only
        item instead of matching a specific track.
      - "pub" with a real track number: unchanged from before."""
    kind, ident, issue, track = parse_video_link(href)
    if kind is None:
        return None, "Not a recognized video link"
    if kind == "docid":
        return _resolve_docid_video(ident)
    items, err = list_video_items(ident, issue=issue)
    if err:
        return None, err
    if track == "x":
        return (items[0], None) if items else (None, f'"{ident}" has no videos available')
    for item in items:
        if item.get("track") == track:
            return item, None
    return None, f'Video track {track} not found in "{ident}"'


def _resolve_docid_video(docid):
    """v0.1.104: resolve a docid-based video link (see parse_video_link's
    docstring). GETPUBMEDIALINKS accepts docid as its own top-level param
    (confirmed live -- separate from pub=) and returns a self-contained
    file list for that specific video; the trailing ts=HH:MM:SS-HH:MM:SS
    some of these links carry is a play-range within the video, not a
    separate file, so we download the whole thing same as any other
    link."""
    params = {"docid": docid, "langwritten": LANG, "fileformat": "MP4",
              "alllangs": "0", "output": "json"}
    url = API_BASE + "?" + "&".join(
        f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return None, str(e)
    tracks = _extract_video_tracks(data)
    if not tracks:
        return None, f'docid "{docid}" has no videos available'
    # Prefer the standard 480p rendition same as list_video_items does
    # implicitly via _extract_video_tracks' own ordering; just take the
    # first non-audio-description track here since a docid link always
    # points at exactly one specific video, not a list to pick from.
    t = tracks[0]
    safe_name = _sanitize_video_filename(t["title"])
    size_mb = t["filesize"] / (1024 * 1024) if t["filesize"] else 0
    return {
        "title": t["title"],
        "subtitle": f'{t["label"]}  ~{size_mb:.0f} MB',
        "filename": f"{safe_name} ({t['label']}).mp4",
        "_video_url": t["url"],
        "track": t.get("track"),
    }, None


def find_movies_dir():
    """Locate muOS's native Media Player content folder (ROMS/movies),
    SD1/SD2 aware -- same principle as mux_launch.sh never hardcoding a
    single storage path (see main.py AI NOTES). Checks both real muOS
    mount points and returns the first that exists; falls back to the
    SD1 path (creating it) if neither is found yet, since a video
    download should still succeed on a fresh setup rather than fail.

    v0.1.92: confirmed the "movies" folder name and location against
    Kaleb's own device screenshot (/mnt/sdcard/ROMS/movies)."""
    candidates = [
        "/mnt/sdcard/ROMS/movies",
        "/mnt/mmc/ROMS/movies",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    # Neither exists yet -- default to SD1 and create it so the very
    # first video download on a fresh card still works.
    fallback = candidates[0]
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        pass
    return fallback


def download_video(item, dest_dir):
    """Download the video for `item` (from list_video_items()) into
    dest_dir (normally find_movies_dir()'s result). Same streaming +
    .part-file + atomic-rename pattern as download() below -- see that
    function's docstring for why each piece matters.

    Returns (ok, message, dest_path) -- same contract as download()."""
    dest_path = os.path.join(dest_dir, item["filename"])
    if os.path.exists(dest_path):
        return False, f'"{item["filename"]}" already downloaded', dest_path

    video_url = item.get("_video_url")
    if not video_url:
        return False, "No video URL resolved for this item", None

    tmp_path = dest_path + ".part"
    req = urllib.request.Request(video_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)  # 64 KB chunks -- flat RAM use
                    if not chunk:
                        break
                    f.write(chunk)
        os.replace(tmp_path, dest_path)  # atomic rename
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False, f"Download failed: {e}", None

    return True, f'Downloaded "{item["title"]}" to ROMS/movies', dest_path


def download(item, dest_dir):
    """Download the EPUB for `item` into `dest_dir`.

    Two-step process (different from gutenberg_fetch.py's single-step):
      Step 1: call _resolve_download_url() to get a fresh CDN URL from
              GETPUBMEDIALINKS (URLs are time-limited and can change).
      Step 2: stream the EPUB from that URL in 64 KB chunks.

    The streaming + .part temp file pattern is the same as gutenberg_fetch:
    - .part file prevents a corrupt/partial epub appearing in the library
    - 64 KB chunks keep RAM use flat regardless of file size
    - atomic os.replace() is safe even if the process is interrupted

    Called on a background thread by main.py -- never block the UI thread
    with network I/O.

    Returns (ok, message, dest_path) -- same contract as gutenberg_fetch."""
    dest_path = os.path.join(dest_dir, item["filename"])
    if os.path.exists(dest_path):
        return False, f'"{item["filename"]}" already in Library', dest_path

    # Step 1: resolve current CDN URL
    epub_url, err = _resolve_download_url(item)
    if err:
        return False, err, None
    if not epub_url:
        return False, "Could not resolve a download link", None

    # Step 2: stream download
    tmp_path = dest_path + ".part"
    req = urllib.request.Request(epub_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)  # 64 KB chunks -- flat RAM use
                    if not chunk:
                        break
                    f.write(chunk)
        os.replace(tmp_path, dest_path)  # atomic rename
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False, f"Download failed: {e}", None

    return True, f'Downloaded "{item["title"]}"', dest_path
