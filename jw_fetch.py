"""
jw_fetch.py

Current version: v26.07.15.15 (matches main.py's date-based scheme,
YY.MM.DD.XX). Inline "# vYY.MM.DD.XX" comments document non-obvious
behavior near the relevant code, same convention as main.py.

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
Awake! ("g") does NOT use a generator for its 2016+ era -- its frequency
changed twice (6/yr Feb-Dec even months 2016-17, 3/yr Mar/Jul/Nov
2018-21, 1/yr 2022-present), so a per-year count alone can't derive
correct issue=YYYYMM codes. Instead AWAKE_BACK_ISSUES (v4, new) hard-codes
the full 2016-2025 back-issue list (28 issues) -- each one individually
confirmed live against GETPUBMEDIALINKS (HTTP 200 + EPUB file present)
before being added, same bar as everything else in this file. The
frequency changes were independently corroborated by Wikipedia's Awake!
article ("As of January 2016, it was published every two months and
was further reduced to three issues per year as of January 2018. In
2022, publication was reduced to one new issue per year") -- matches
our live results exactly. Titles sourced from jw.org's own magazine
pages. See AWAKE_BACK_ISSUES below for the full list and how to extend
it when a new issue comes out.
Awake! ALSO has an earlier confirmed-monthly era, Sept 2011 through Dec
2015 (v6, new, per Kaleb's request to go back to 2011) -- EVERY month
in this range individually checked (not spot-checked) against
GETPUBMEDIALINKS: Aug 2011 and earlier all 404 (EPUB doesn't exist),
Sept 2011 through Dec 2015 all HTTP 200 with a real EPUB file, zero
gaps across all 52 months. Genuinely safe for the same monthly-
generator approach "w" uses -- see generate_awake_monthly_issues() and
AWAKE_MONTHLY_START/END. Plain "Awake! (Month Year)" titles here (no
custom per-issue cover-story title needed, unlike the irregular 2016+
list) since this era really is one issue every month.
Watchtower ("w") and Public Watchtower ("wp") do NOT have this earlier
era -- checked EVERY month, not spot-checked, for both pub codes across
the full 2011-2015 range: 100% 404 for both, no exceptions. The EPUB
file format itself doesn't exist on JW.org's CDN before Jan 2016 for
either Watchtower edition, even though the print magazine was
certainly published monthly back then -- this is a real limitation of
what JW.org's own servers offer, not a gap in this plugin's code. If a
future check ever finds an exception, this note is the place to update.
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

import base64
import html
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

# SUPPORTS_SEARCH tells main.py to show the existing generic Y-button
# search box (same one gutenberg_fetch.py uses) and call
# list_items(query=...) with what's typed. v0.1.161+: this is now a REAL
# live search against jw.org's own search service (see search_jw() below)
# instead of a local substring filter -- confirmed live to find real,
# resolvable EPUBs for arbitrary topics (Bible books, doctrine subjects,
# dated periodicals like "daily text", etc.), not just exact pub titles.
#
# Scoped to PUBLICATIONS ONLY, not videos: main.py's generic
# SUPPORTS_SEARCH -> download() path has no route to download_video()/
# ROMS/movies (that's a separate, dedicated screen -- see
# SCREEN_DOWNLOAD_VIDEO_SOURCES). Returning a video-shaped item here
# would silently fail against the wrong download() function. A real
# "search videos by free text" UI would need a main.py change; per
# Kaleb's instruction this plugin stays search-UI-self-contained, so
# video results are simply excluded from list_items(query=...) results
# rather than half-wired. See search_jw()'s own docstring if a future
# session revisits adding a dedicated video-search screen.
SUPPORTS_SEARCH = True

# v0.1.162: VIDEO_SOURCES -- lets main.py build the "Videos" picker
# screen (Download Books > JW > Videos) WITHOUT hardcoding any JW-specific
# titles or pub codes itself. Previously main.py had a hardcoded 4-item
# label list PLUS a matching elif chain PLUS four near-duplicate App
# methods, one per source -- all of that collapses to one generic loop +
# one generic loader method now that the plugin declares this list.
#
# Each entry:
#   "label"  str   -- shown in the picker, exactly as before
#   "loader" str   -- name of a function on THIS module, called with
#                     "args" as keyword arguments, returning the same
#                     (items, error_message) shape list_video_items() etc.
#                     already return. main.py calls it via getattr(), so
#                     it never needs to know the function names up front.
#   "args"   dict  -- kwargs passed to the loader (e.g. {"pub": "lffv"})
#   "search" bool  -- True marks the live free-text search entry instead
#                     of a fixed loader; main.py special-cases only this
#                     one flag (opens its existing text-entry screen,
#                     calls search_jw(query, filter="videos") itself --
#                     that part is genuinely main.py's job, it owns the
#                     text-entry UI).
#
# Order matches the original hardcoded list (Kaleb's original menu
# order), with "Search Videos" added at the end, same as before.
VIDEO_SOURCES = [
    # v26.07.15.15 (Kaleb's bug-check request -- "make sure everything
    # is categorized identically to JW.org"): re-checked the real
    # VODSeries listing directly (same method that caught Love People
    # last round) and found two more real Series children we'd left
    # flat -- "Enjoy Life Forever" (SeriesLFFVideos, confirmed
    # byte-identical live to the pub=lffv content already used here --
    # same 91 items either way, so the loader mechanism didn't need to
    # change, just its placement) and "The Good News According to
    # Jesus" (SeriesGoodNews). Both moved into the Series folder below.
    #
    # v26.07.15.11 (Kaleb's request -- "move or rename any of the ones
    # we already have that are named the same on JW.org for
    # consistency"): re-checked the real jw.org category tree and found
    # several existing entries were correctly NAMED but sitting in the
    # wrong place, plus one that was flat-out mislabeled:
    #   - The flat entry that used to be called "JW Broadcasting" was
    #     always loading StudioMonthlyPrograms -- but confirmed live,
    #     jw.org's OWN category named "JW Broadcasting" (VODStudio) is
    #     the PARENT of 4 real children: Featured Videos, Monthly
    #     Programs, Talks, News and Announcements. What we had was
    #     really "Monthly Programs" wearing its parent's name. Renamed
    #     to match, and nested under a real "JW Broadcasting" folder
    #     alongside "Talks" (which was correctly named but flat,
    #     standing in for its real sibling relationship).
    #   - "Weekly Meetings" and "Meetings, Assemblies, and Conventions"
    #     were both correctly named but flat -- their real parent,
    #     confirmed live, is "Our Meetings and Ministry" (VODMinistry).
    #   - "Original Songs" (the video one) was correctly named but
    #     flat -- its real parent, confirmed live, is "Music"
    #     (VODMusicVideos).
    #   - "Morning Worship" was correctly named but flat -- its real
    #     parent, confirmed live, is "Programs and Events"
    #     (VODProgramsEvents).
    # v26.07.15.12 (Kaleb's follow-up questions, both correct):
    #   - "Love People -- Make Disciples" DOES have a real parent after
    #     all -- v26.07.15.11's claim it was standalone was wrong; that
    #     check only ever looked for a "SeriesXxx"-prefixed key, never
    #     fetched the real VODSeries category listing itself. Doing
    #     that now shows VODLovePeople listed as one of Series's 32 real
    #     children (key doesn't follow the SeriesXxx naming convention,
    #     but the parent/child relationship is real and confirmed live)
    #     -- moved into the "Series" folder below.
    #   - Governing Body Updates' real "broadcast equivalent" is "News
    #     and Announcements" (StudioNewsReports, JW Broadcasting's 4th
    #     real child) -- added below as its own real, UNFILTERED entry
    #     (80 items) alongside Monthly Programs/Talks. The existing
    #     "Governing Body Updates" flat entry is our own curated filter
    #     of this exact same category (GB-titled videos only, 56 of the
    #     80) -- kept as its own entry too since it's still a useful
    #     quick view, not retired; Kaleb can decide whether to drop it
    #     now that the real unfiltered category is one tap away.
    {"label": "JW Broadcasting",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Monthly Programs", "key": "StudioMonthlyPrograms"},
         {"label": "Talks", "key": "StudioTalks"},
         {"label": "News and Announcements", "key": "StudioNewsReports"},
     ]},
    {"label": "Our Meetings and Ministry",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Weekly Meetings", "key": "VODMinistryMidweekMeeting"},
         {"label": "Meetings, Assemblies, and Conventions", "key": "MeetingsConventions"},
     ]},
    {"label": "Music",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Original Songs", "key": "VODOriginalSongs"},
     ]},
    {"label": "Programs and Events",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Morning Worship", "key": "VODPgmEvtMorningWorship"},
     ]},
    {"label": "Governing Body Updates",
     "loader": "check_new_gb_updates", "args": {}},
    # v26.07.15.09 (Kaleb's follow-up -- changed mind, wants these
    # nested rather than flat, "series categories only"): the 18
    # remaining requested categories all genuinely have a "SeriesXxx"
    # key on jw.org's own tree, so they go in one "Series" entry with a
    # "subcategories" list -- opens SCREEN_DOWNLOAD_VIDEO_SERIES (new
    # picker in main.py, same pattern as the Bible-book sub-picker
    # already used for Audio) instead of calling a loader directly.
    # Each subcategory entry's own "key"/"label" get merged into this
    # entry's "loader"/"args" once chosen -- see main.py's
    # SCREEN_DOWNLOAD_VIDEO_SERIES button handling.
    {"label": "Series",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Become Jehovah's Friend -- Video Lessons", "key": "SeriesBJFLessons"},
         {"label": "Dig for Treasures", "key": "SeriesDigForTreasures"},
         {"label": "Essential Bible Teachings", "key": "SeriesBibleTeachings"},
         {"label": "For a Happy Marriage", "key": "SeriesHappyMarriage"},
         {"label": "Full-Time Service Builds Christian Qualities", "key": "SeriesFullTimeService"},
         {"label": "Imitate Their Faith", "key": "SeriesImitateFaith"},
         {"label": "Introduction to Bible Books", "key": "SeriesBibleBooks"},
         {"label": "Iron Sharpens Iron", "key": "SeriesIronSharpens"},
         {"label": "Learn From Jehovah's Friends", "key": "SeriesJehovahsFriends"},
         {"label": "Learn From Them", "key": "SeriesLearnFromThem"},
         {"label": "Lessons From The Watchtower", "key": "SeriesWTLessons"},
         {"label": "My Teen Life", "key": "SeriesMyTeenLife"},
         {"label": "Neeta and Jade", "key": "SeriesNeetaJade"},
         {"label": "Organizational Accomplishments", "key": "SeriesOrgAccomplishments"},
         {"label": "Our History in Motion", "key": "SeriesOurHistory"},
         {"label": "The Bible Changes Lives", "key": "SeriesBibleChangesLives"},
         {"label": "Truth Transforms Lives", "key": "SeriesTruthTransforms"},
         {"label": "Whiteboard Animations", "key": "SeriesWhiteboard"},
         {"label": "Love People -- Make Disciples", "key": "VODLovePeople"},
         {"label": "Enjoy Life Forever", "key": "SeriesLFFVideos"},
         {"label": "The Good News According to Jesus", "loader": "list_good_news_items", "args": {}},
     ]},
    # v26.07.15.10 (Kaleb's request -- "add categories as long as they
    # are identical to what the actual category is on JW.org"): 6 more
    # real top-level jw.org video categories, each with its own real
    # sub-categories, all confirmed live this session via the same
    # category-key + media-count check as everything above. Organized
    # as real nested folders (same generic "subcategories" mechanism as
    # "Series" above, zero main.py changes needed) because this genuinely
    # mirrors jw.org's own tree structure -- these aren't folders I
    # invented, they're the real parent/child relationship on the site.
    #
    # Two deliberately NOT included, both confirmed live this session:
    #   - "Books of the Bible" (VODBible key "BibleBooks", 67 items) is
    #     BYTE-IDENTICAL to "Introduction to Bible Books" already under
    #     Series above (same 67 titles, confirmed via direct set
    #     comparison) -- jw.org itself cross-lists the same category
    #     under two different parents. Adding it again here would be a
    #     true duplicate menu entry, not new content, so it's skipped.
    #   - "The Good News According to Jesus" (VODMovies key
    #     "DramasGoodNews", 9 items) and "Video Lessons" (VODChildren
    #     key "BJF", 69 items) both substantially OVERLAP (not
    #     identical) with categories already added higher up -- the
    #     existing 6-episode Good News entry's episodes are all inside
    #     this 9-item version plus 3 extras; the existing 60-item Become
    #     Jehovah's Friend entry's videos are 59/60 inside this 69-item
    #     version plus extras. Left out pending Kaleb's call on whether
    #     the extra handful of bonus videos is worth a near-duplicate
    #     menu entry -- see conversation, not silently included or
    #     silently dropped.
    {"label": "Children",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Video Lessons", "key": "BJF"},
         {"label": "Songs", "key": "ChildrenSongs"},
         {"label": "Dramas", "key": "ChildrenMovies"},
     ]},
    {"label": "Teenagers",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Spiritual Growth", "key": "TeenSpiritualGrowth"},
         {"label": "Social Life", "key": "TeenSocialLife"},
         {"label": "Goals", "key": "TeenGoals"},
         {"label": "Interviews and Experiences", "key": "TeenWhatPeersSay"},
         {"label": "Dramas", "key": "TeenMovies"},
     ]},
    {"label": "Family",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Family Challenges", "key": "FamilyChallenges"},
         {"label": "Dating and Marriage", "key": "FamilyDatingMarriage"},
         {"label": "Family Worship", "key": "FamilyWorship"},
         {"label": "Dramas", "key": "FamilyMovies"},
     ]},
    {"label": "Our Activities",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Translation", "key": "VODActivitiesTranslation"},
         {"label": "Audio and Video Production", "key": "VODActivitiesAVProduction"},
         {"label": "Publishing and Distribution", "key": "VODActivitiesPrintingShipping"},
         {"label": "Construction", "key": "VODActivitiesConstruction"},
         {"label": "Relief Work", "key": "VODActivitiesReliefWork"},
         {"label": "Theocratic Schools and Training", "key": "VODActivitiesTheoSchools"},
         {"label": "Special Events", "key": "VODActivitiesSpecialEvents"},
     ]},
    {"label": "The Bible",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Bible Reading and Study", "key": "VODBibleReadingStudy"},
         {"label": "Bible Teachings", "key": "VODBibleTeachings"},
         {"label": "Bible Accounts", "key": "VODBibleAccounts"},
         {"label": "People, Places, and Things", "key": "VODBibleMedia"},
         {"label": "Bible Translations", "key": "VODBibleTranslations"},
         {"label": "Apply Bible Principles", "key": "VODBiblePrinciples"},
         {"label": "Creation", "key": "VODBibleCreation"},
     ]},
    {"label": "Interviews and Experiences",
     "loader": "list_mediator_category", "args": {},
     "subcategories": [
         {"label": "Truth Transforms Lives", "key": "VODIntExpTransformations"},
         {"label": "Blessings of Sacred Service", "key": "VODIntExpBlessings"},
         {"label": "Enduring Trials", "key": "VODIntExpEndurance"},
         {"label": "Young People", "key": "VODIntExpYouth"},
         {"label": "Science", "key": "OriginsLife"},
         {"label": "From Our Archives", "key": "VODIntExpArchives"},
     ]},
    {"label": "Search Videos", "search": True},
]

# v26.07.10.01: AUDIO_SOURCES -- same registry pattern as VIDEO_SOURCES
# just above, for main.py's "Audio" picker (Download Books > JW > Audio).
# Two real sources, both confirmed live against GETPUBMEDIALINKS with
# fileformat=MP3 this session:
#   "Watchtower Study Audio (This Week)" -- resolves the RSS-confirmed
#     latest Study Edition issue itself (list_watchtower_study_audio()),
#     no further picker needed, same "just works" shape as the video
#     sources above.
#   "Bible Reading Audio (NWT)" -- unlike every VIDEO_SOURCES entry,
#     this pub needs a booknum (which of the 66 Bible books) before it
#     can list anything -- there's no single "latest" to resolve. Marked
#     "books": True (new flag, same spirit as "search": True) so
#     main.py knows to open its own book-picker sub-screen first
#     (SCREEN_DOWNLOAD_AUDIO_BOOKS) instead of calling a loader directly;
#     the chosen book's booknum is then passed to list_audio_items() via
#     "loader"/"args" the same as any other source.
AUDIO_SOURCES = [
    {"label": "Watchtower Study Audio (This Week)",
     "loader": "list_watchtower_study_audio", "args": {}},
    {"label": "Songbook -- Sing Out Joyfully to Jehovah",
     "loader": "list_audio_items", "args": {"pub": "sjjm"}},
    # v26.07.15.04 (Kaleb's request): confirmed live via jw.org's own
    # finder link that Original Songs also has a standalone MP3 release
    # (pub "osg"), separate from the video-only entry already under
    # VIDEO_SOURCES -- see list_original_songs_audio()'s docstring for
    # the audio-description dedup this needed.
    {"label": "Original Songs",
     "loader": "list_original_songs_audio", "args": {}},
    {"label": "Bible Reading Audio (NWT)", "books": True,
     "loader": "list_audio_items", "args": {"pub": "nwt"}},
    {"label": "Search Audio", "search": True},
]

# Standard NWT book numbering (1-66, Genesis through Revelation) -- this
# is the fixed Bible book order/numbering GETPUBMEDIALINKS' booknum=
# param uses, confirmed directly this session (booknum=1 -> "Chapter 1"
# entries under a Genesis-shaped 50-chapter list; booknum=19 -> a
# 150-chapter Psalms list). Standard, non-language-specific numbering
# (same across all NWT translations), not something that needs a
# per-entry live check the way pub codes/issue dates do.
BIBLE_BOOKS = [
    (1, "Genesis"), (2, "Exodus"), (3, "Leviticus"), (4, "Numbers"), (5, "Deuteronomy"),
    (6, "Joshua"), (7, "Judges"), (8, "Ruth"), (9, "1 Samuel"), (10, "2 Samuel"),
    (11, "1 Kings"), (12, "2 Kings"), (13, "1 Chronicles"), (14, "2 Chronicles"),
    (15, "Ezra"), (16, "Nehemiah"), (17, "Esther"), (18, "Job"), (19, "Psalms"),
    (20, "Proverbs"), (21, "Ecclesiastes"), (22, "Song of Solomon"), (23, "Isaiah"),
    (24, "Jeremiah"), (25, "Lamentations"), (26, "Ezekiel"), (27, "Daniel"),
    (28, "Hosea"), (29, "Joel"), (30, "Amos"), (31, "Obadiah"), (32, "Jonah"),
    (33, "Micah"), (34, "Nahum"), (35, "Habakkuk"), (36, "Zephaniah"), (37, "Haggai"),
    (38, "Zechariah"), (39, "Malachi"), (40, "Matthew"), (41, "Mark"), (42, "Luke"),
    (43, "John"), (44, "Acts"), (45, "Romans"), (46, "1 Corinthians"), (47, "2 Corinthians"),
    (48, "Galatians"), (49, "Ephesians"), (50, "Philippians"), (51, "Colossians"),
    (52, "1 Thessalonians"), (53, "2 Thessalonians"), (54, "1 Timothy"), (55, "2 Timothy"),
    (56, "Titus"), (57, "Philemon"), (58, "Hebrews"), (59, "James"), (60, "1 Peter"),
    (61, "2 Peter"), (62, "1 John"), (63, "2 John"), (64, "3 John"), (65, "Jude"),
    (66, "Revelation"),
]

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
CATEGORY_WHATS_NEW = "New Issues"  # v26.07.09.11: renamed from "What's
# New (RSS)" -- that label implied general JW.org news, but this only
# ever surfaces newly-detected PERIODICAL issues (Watchtower/Awake/
# Workbook) via check_new_issues(). Confirmed this was genuinely
# confusing Kaleb about what the feature does.
CATEGORY_BIBLES = "Bibles"
CATEGORY_BOOKS = "Books & Brochures"
CATEGORY_TRACTS = "Tracts"
CATEGORY_WATCHTOWER_STUDY = "Watchtower -- Study Edition"
CATEGORY_WATCHTOWER_PUBLIC = "Watchtower -- Public Edition"
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
# v26.07.10.01: CATEGORY_AUDIO -- same pseudo-category pattern as
# CATEGORY_VIDEOS just above. Kaleb's bug-report feature request:
# downloadable JW audio (MP3), saved into muOS's native GMU Music Player
# content folder (ROMS/Music -- confirmed against Kaleb's own device,
# same verification bar as find_movies_dir()'s ROMS/movies). Opens
# main.py's SCREEN_DOWNLOAD_AUDIO_SOURCES / draw_download_audio_sources()
# sub-picker, same as Videos does -- doesn't route through list_items().
CATEGORY_AUDIO = "Audio"
CATEGORIES = [CATEGORY_WHATS_NEW, CATEGORY_BIBLES, CATEGORY_BOOKS, CATEGORY_TRACTS,
              CATEGORY_WATCHTOWER_STUDY, CATEGORY_WATCHTOWER_PUBLIC, CATEGORY_AWAKE, CATEGORY_WORKBOOKS,
              CATEGORY_VIDEOS, CATEGORY_AUDIO]

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
    # v26.07.15.13 (Kaleb's request -- systematic pass through jw.org's
    # real Books/Brochures library looking for EPUB-available titles not
    # yet in this list): confirmed live via GETPUBMEDIALINKS this
    # session, real pub codes pulled directly from jw.org's own page
    # markup (not guessed). Yearbook itself stopped after 2017,
    # replaced by annual Service Year Reports -- confirmed yb70 through
    # yb10 all 404 (no EPUB ever existed for those, so the existing
    # yb11-yb17 range above was already complete) and syr17-syr21 have
    # real EPUB editions; syr22 onward tried and 404'd (PDF/JWPUB only
    # for the more recent years -- exactly the "not every publication
    # has an EPUB" pattern Kaleb flagged).
    ("syr17",  "2017 Service Year Report of Jehovah's Witnesses Worldwide", None, CATEGORY_BOOKS),
    ("syr18",  "2018 Service Year Report of Jehovah's Witnesses Worldwide", None, CATEGORY_BOOKS),
    ("syr19",  "2019 Service Year Report of Jehovah's Witnesses Worldwide", None, CATEGORY_BOOKS),
    ("syr20",  "2020 Service Year Report of Jehovah's Witnesses Worldwide", None, CATEGORY_BOOKS),
    ("syr21",  "2021 Service Year Report of Jehovah's Witnesses Worldwide", None, CATEGORY_BOOKS),
    ("lvs",   "How to Remain in God's Love", None, CATEGORY_BOOKS),
    ("bhs",   "What Can the Bible Teach Us?", None, CATEGORY_BOOKS),
    # Tried and confirmed NO EPUB this session (PDF/JWPUB only) --
    # listed here, not added above, so a future pass doesn't re-check
    # the same ones: wcgr (References for Walk Courageously With God),
    # scl (Scriptures for Christian Living), it (Insight on the
    # Scriptures), nwtstg (Bible Glossary), syr22/23/24/25.
    # v26.07.15.14 (Kaleb's follow-up -- continuing the systematic
    # pass): tried known/documented JW pub-code conventions for several
    # remaining titles. Two guesses ("rs"=Reasoning From the Scriptures,
    # "kl"=Knowledge That Leads to Everlasting Life, "uw", "dp", "is1",
    # "is2", "re", "yp1", "yp2", "w88", "g88", "kr" -- all either the
    # wrong code or genuinely no EPUB) came back 404 and were NOT
    # added. Two guesses hit real live publications, but NOT the ones
    # originally guessed -- confirmed via the API's own returned pubName
    # before adding, exactly to avoid mislabeling one publication with
    # another's title:
    #   "gt" was guessed as Theocratic Ministry School Guidebook --
    #   wrong guess, but it's actually "The Greatest Man Who Ever
    #   Lived" (confirmed live, real EPUB).
    #   "kt" was a guess for something else entirely -- it's actually
    #   "Would You Like to Know the Truth?" (confirmed live, real
    #   EPUB, older evangelism booklet).
    #   "sp" was guessed as a songbook -- it's actually "Spirits of the
    #   Dead -- Can They Help You or Harm You? Do They Really Exist?"
    #   (confirmed live, real EPUB, a brochure not a book -- filed
    #   under CATEGORY_BOOKS anyway since STATIC_PUBLICATIONS doesn't
    #   split by the exact jw.org sub-shelf, same as everything else
    #   in this list).
    ("bh",    "What Does the Bible Really Teach?", None, CATEGORY_BOOKS),
    ("gt",    "The Greatest Man Who Ever Lived", None, CATEGORY_BOOKS),
    ("kt",    "Would You Like to Know the Truth?", None, CATEGORY_BOOKS),
    ("sp",    "Spirits of the Dead -- Can They Help You or Harm You? Do They Really Exist?", None, CATEGORY_BOOKS),
    # -- added per Kaleb's request, all verified live against
    # GETPUBMEDIALINKS before being added (pub, title, EPUB availability
    # all confirmed via a real API round-trip, not guessed from the
    # download URLs Kaleb supplied) --
    ("lr",    "Learn From the Great Teacher", None, CATEGORY_BOOKS),
    ("my",    "My Book of Bible Stories", None, CATEGORY_BOOKS),
    ("th",    "Apply Yourself to Reading and Teaching", None, CATEGORY_BOOKS),
    ("rj",    "Return to Jehovah", None, CATEGORY_BOOKS),
    ("ypq",   "Answers to 10 Questions Young People Ask", None, CATEGORY_BOOKS),
    ("hf",    "Your Family Can Be Happy", None, CATEGORY_BOOKS),
    ("yc",    "Teach Your Children", None, CATEGORY_BOOKS),
    ("mb",    "My Bible Lessons", None, CATEGORY_BOOKS),
    ("hl",    "How Can You Have a Happy Life?", None, CATEGORY_BOOKS),
    ("ll",    "Listen to God and Live Forever", None, CATEGORY_BOOKS),
    ("lc",    "Was Life Created?", None, CATEGORY_BOOKS),
    ("lf",    "The Origin of Life -- Five Questions Worth Asking", None, CATEGORY_BOOKS),
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
    ("w",   "Watchtower -- Study Edition", CATEGORY_WATCHTOWER_STUDY),
    ("wp",  "Watchtower -- Public Edition", CATEGORY_WATCHTOWER_PUBLIC),
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
        # v26.07.15.02 BUG FIX (Kaleb's report -- 2025/2026 wp missing):
        # this used to require the CALENDAR month to have reached
        # WP_ANNUAL_ISSUES[y] before trusting that year's entry (e.g.
        # wouldn't use 2026:9 until the calendar hit September 2026).
        # That's wrong: WP_ANNUAL_ISSUES entries are only ever added
        # after being individually confirmed live (see comment above
        # the dict), so presence in the table already means the EPUB
        # exists NOW, regardless of calendar month -- confirmed live
        # 2026-07: issue=202609 (Sept 2026, "next" year-row) already
        # resolves via GETPUBMEDIALINKS today, months before September.
        # Same root cause as mwb's v26.07.09.14 fix: JW.org publishes
        # periodicals genuinely ahead of the calendar.
        if y in WP_ANNUAL_ISSUES:
            return f"{y}{WP_ANNUAL_ISSUES[y]:02d}"
        candidates = [yy for yy in WP_ANNUAL_ISSUES if yy < y]
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

# Awake! ("g") had an EARLIER monthly era too, before the 2016+ frequency
# changes AWAKE_BACK_ISSUES hard-codes -- confirmed live, EVERY month
# individually checked against GETPUBMEDIALINKS (not spot-checked), per
# Kaleb's request to go back to 2011. Aug 2011 and earlier: 404 (EPUB
# doesn't exist). Sept 2011 through Dec 2015: HTTP 200 with a real EPUB
# file present for all 52 consecutive months, zero gaps -- genuinely
# safe for the same monthly-generator approach "w" uses, unlike the
# irregular 2016+ era. Jan 2016 onward is where AWAKE_BACK_ISSUES's
# hard-coded list picks up, so this era ends at Dec 2015 to avoid
# overlapping it.
AWAKE_MONTHLY_START = (2011, 9)
AWAKE_MONTHLY_END = (2015, 12)

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


WATCHTOWER_MONTHLY_START = (2011, 9)
WATCHTOWER_MONTHLY_END = (2015, 12)
W_DAY = 15   # Study Watchtower ("w") always used day 15 pre-2016
WP_DAY = 1   # Public Watchtower ("wp") always used day 1 pre-2016


def generate_w_pre2016_issues():
    """Study Watchtower ("w") back-issue list for its pre-2016 era, Sept
    2011 through Dec 2015 -- Kaleb's correction: the original v0.1.159
    check tested the WRONG issue-code format for this era (YYYYMM,
    month-only, same as the 2016+ format) and got 100% 404, wrongly
    concluding EPUB didn't exist before 2016. Kaleb supplied a real
    working URL (w_E_20151215.epub) that revealed the actual pre-2016
    format is DAY-based (YYYYMMDD), always the 15th for the Study
    edition. Re-verified EVERY month 2011-2015 with this corrected
    format (not spot-checked): Aug 2011 and earlier still 404, but Sept
    2011 through Dec 2015 all HTTP 200 with a real EPUB, 52 consecutive
    months, zero gaps -- same clean monthly range as Awake!'s. Confirmed
    the Jan 2016 boundary is clean too: 20160115 (day-based) 404s, while
    201601 (month-only, the existing 2016+ format) succeeds -- no
    overlap between the two eras."""
    items = []
    months_full = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    for y, m in _month_range_desc(WATCHTOWER_MONTHLY_START[0], WATCHTOWER_MONTHLY_START[1],
                                    WATCHTOWER_MONTHLY_END[0], WATCHTOWER_MONTHLY_END[1]):
        issue = f"{y}{m:02d}{W_DAY:02d}"
        items.append({
            "title":    f"Watchtower -- Study Edition ({months_full[m - 1]} {y})",
            "subtitle": f"pub: w  issue: {issue}",
            "filename": f"w_{LANG}_{issue}.epub",
            "_pub":     "w",
            "_extra":   {"issue": issue},
        })
    return items


def generate_wp_pre2016_issues():
    """Public Watchtower ("wp") back-issue list for its pre-2016 era --
    same era/correction as generate_w_pre2016_issues() above, but always
    day 1 instead of day 15 (confirmed independently, same method: every
    month 2011-2015 checked live, Sept 2011-Dec 2015 all HTTP 200 with
    day=01, zero gaps, Jan 2016 boundary clean)."""
    items = []
    months_full = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    for y, m in _month_range_desc(WATCHTOWER_MONTHLY_START[0], WATCHTOWER_MONTHLY_START[1],
                                    WATCHTOWER_MONTHLY_END[0], WATCHTOWER_MONTHLY_END[1]):
        issue = f"{y}{m:02d}{WP_DAY:02d}"
        items.append({
            "title":    f"Watchtower -- Public Edition ({months_full[m - 1]} {y})",
            "subtitle": f"pub: wp  issue: {issue}",
            "filename": f"wp_{LANG}_{issue}.epub",
            "_pub":     "wp",
            "_extra":   {"issue": issue},
        })
    return items


def generate_awake_monthly_issues():
    """Awake! ("g") back-issue list for its EARLIER confirmed-monthly era,
    Sept 2011 through Dec 2015 (see AWAKE_MONTHLY_START/END comment) --
    a separate, bounded range from generate_monthly_back_issues() since
    that one is open-ended (no END month) and only "w" uses it. Uses
    plain "Awake! (Month Year)" titles, not the custom per-issue
    cover-story titles AWAKE_BACK_ISSUES (2016+) has, since this earlier
    era doesn't need one -- it's genuinely one issue every month, no
    irregular "No. N" numbering to disambiguate."""
    items = []
    months_full = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    for y, m in _month_range_desc(AWAKE_MONTHLY_START[0], AWAKE_MONTHLY_START[1],
                                    AWAKE_MONTHLY_END[0], AWAKE_MONTHLY_END[1]):
        issue = f"{y}{m:02d}"
        items.append({
            "title":    f"Awake! ({months_full[m - 1]} {y})",
            "subtitle": f"pub: g  issue: {issue}",
            "filename": f"g_{LANG}_{issue}.epub",
            "_pub":     "g",
            "_extra":   {"issue": issue},
        })
    return items


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
    defaults to the RSS-confirmed latest (check_new_issues()) if not
    given, falling back to a parity-corrected calendar guess only if RSS
    is unreachable.

    v26.07.09.14 BUG FIX (Kaleb's report -- missing 2026 workbooks /
    "guess latest issue" seemed broken): this used to default straight to
    raw current_issue_guess() with NO correction at all, even though
    _mwb_valid_issue() already existed for exactly this. Confirmed live:
    current_issue_guess() returned 202607 while check_new_issues() (RSS)
    confirmed 202611 was the real latest -- JW.org publishes issues
    genuinely months ahead of the calendar, not just the +-1 parity
    _mwb_valid_issue() alone corrects for. The CALL SITE in list_items()
    already passed the RSS-confirmed value through correctly when
    available; this was only wrong for a caller (or code path) that
    relies on this function's own internal default, which is now fixed
    to try the same RSS check itself rather than assuming its caller
    always will."""
    if newest_issue:
        ny, nm = int(newest_issue[:4]), int(newest_issue[4:6])
    else:
        rss_hit = next((issue for pub, _t, issue in check_new_issues() if pub == "mwb"), None)
        guess = rss_hit or _mwb_valid_issue(current_issue_guess())
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
    (defaults to the RSS-confirmed latest via check_new_issues() if not
    given, falling back to a parity-corrected calendar guess only if RSS
    is unreachable -- see generate_mwb_back_issues()'s v26.07.09.14 fix
    comment for why the naive calendar guess alone isn't safe here,
    especially for wp: since 2022 it's annual at a fixed irregular month
    per WP_ANNUAL_ISSUES, so an under-guessed range could exclude the
    entire current year's entry, not just be one issue short).
    Models all three publishing eras -- see the constants above and the
    module docstring's BACK-ISSUES note for how each was confirmed."""
    if newest_issue:
        ny, nm = int(newest_issue[:4]), int(newest_issue[4:6])
    else:
        rss_hit = next((issue for pub, _t, issue in check_new_issues() if pub == "wp"), None)
        guess = rss_hit or _wp_valid_issue(current_issue_guess())
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
    optionally scoped to one category (see CATEGORIES), OR -- when
    `query` is a non-empty string -- a REAL live search against jw.org's
    own search service instead of the static local catalog (v0.1.161+;
    see search_jw()'s docstring for how that API works and its
    publications-only scope). `category` is ignored during a live
    search -- jw.org's search API doesn't support scoping by this app's
    local category groupings, so results are simply the API's own
    top matches regardless of which category screen search was opened
    from. (Cosmetic-only quirk: main.py's search-box label may say
    "Search {category}" per its own generic labeling logic, but the
    actual results are unscoped -- same category/global distinction
    gutenberg_fetch.py already has for its own search, not new here.)

    Unlike gutenberg_fetch.py, browsing WITHOUT a query doesn't call an
    API here -- the catalog is assembled locally from STATIC_PUBLICATIONS
    and PERIODICALS, with the RSS feed used only to determine the current
    periodical issue codes. The actual download URL is resolved lazily in
    download() via _resolve_download_url() -- we don't need it for the
    browse list, and (for live search results) not verified to have an
    EPUB until then either -- same as manual pub-code entry already works.

    page is ignored: the catalog (even a single category) is small enough
    to show in full. has_next is always False.

    Catalog assembly order (query=None only):
    1. Static publications (books, courses -- no issue needed)
    2. New issues found via RSS (labeled "(new)")
    3. Periodicals not already covered by RSS (labeled "(this month, guess)")
    4. Daily text (special case: year-specific pub code, no issue param)"""
    items = []

    # v0.1.161: a typed query now bypasses the static catalog entirely
    # and does a real live jw.org search instead of a local substring
    # filter -- confirmed live to find genuine matches (Bible books,
    # doctrine topics, dated periodicals) the old substring-only filter
    # could never have found since it only ever saw titles already
    # present in STATIC_PUBLICATIONS/PERIODICALS.
    query = (query or "").strip()
    if query:
        results, err = search_jw(query, filter="all")
        if err:
            return [], False, err
        pub_items = [dict(it) for it in results if it.get("_kind") == "pub"]
        if not pub_items:
            # search_jw()'s own all->publications->videos fallback only
            # fires when the RAW result list is empty -- it doesn't know
            # this caller specifically needs pub-kind items. "all" often
            # returns a non-empty list that's 100% videos (confirmed
            # live: "love", "evolution", "monthly broadcast may 2026"),
            # which is a distinct, more common case than zero results.
            # Retry explicitly scoped to publications before giving up.
            results, err = search_jw(query, filter="publications")
            if err:
                return [], False, err
            pub_items = [dict(it) for it in results if it.get("_kind") == "pub"]
        for it in pub_items:
            it.pop("_kind", None)  # internal tag, not part of the plugin contract
        if not pub_items:
            return [], False, (
                f'No downloadable publications found for "{query}" '
                f"(video-only results aren't shown here -- see README)")
        return pub_items, False, None

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
        # v26.07.15.02: label with the REAL month/year the guess resolved
        # to, not a hard-coded "this month" -- for wp/g (no RSS tracking)
        # and even mwb/w when RSS is unreachable, the guess routinely
        # snaps to an issue months away from the calendar month (e.g.
        # wp in July often resolves to the prior September). Calling
        # that "(this month, guess)" reads as wrong/missing even when
        # the issue and entry are both correct -- just mislabeled.
        iy, im = int(issue[:4]), int(issue[4:6])
        months_full = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]
        label = f"{months_full[im - 1]} {iy}" if 1 <= im <= 12 else issue
        items.append({
            "title":    f"{title} ({label}, latest known)",
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
    # v26.07.09.14: Study and Public used to share ONE combined category
    # (CATEGORY_WATCHTOWER) -- confirmed genuinely confusing (mixed pub
    # codes interleaving in a way that didn't read as clean date order,
    # per Kaleb's report) and split into two separate categories, each
    # now a normal 1:1 category:pub mapping like every other entry here.
    category_pubs = {
        CATEGORY_WATCHTOWER_STUDY:  ("w",),
        CATEGORY_WATCHTOWER_PUBLIC: ("wp",),
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

    # v0.1.160: Watchtower's EARLIER pre-2016 era (Sept 2011-Dec 2015,
    # day-based issue codes) -- see generate_w_pre2016_issues()/
    # generate_wp_pre2016_issues() docstrings for the full correction
    # story (Kaleb caught that the original "no EPUB before 2016" claim
    # was wrong -- it just needed a day-based issue code, not month-only).
    # Same combined-eras pattern as Awake! above.
    if category == CATEGORY_WATCHTOWER_STUDY:
        for item in generate_w_pre2016_issues():
            issue = item["_extra"]["issue"]
            if ("w", issue) in covered:
                continue
            items.append(item)
    if category == CATEGORY_WATCHTOWER_PUBLIC:
        for item in generate_wp_pre2016_issues():
            issue = item["_extra"]["issue"]
            if ("wp", issue) in covered:
                continue
            items.append(item)

    # Awake! ("g") back issues -- two eras combined. AWAKE_BACK_ISSUES
    # (2016+, hard-coded) for the irregular-frequency modern era, plus
    # generate_awake_monthly_issues() (Sept 2011-Dec 2015, generated) for
    # the earlier confirmed-monthly era -- see AWAKE_MONTHLY_START/END.
    # Only shown when actually browsing the Awake! category, same as
    # w/mwb above -- 80 combined entries would be noise mixed into every
    # other category's results.
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
        for item in generate_awake_monthly_issues():
            if ("g", item["_extra"]["issue"]) in covered_g:
                continue
            items.append(item)

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
            return None, f'"{html.unescape(data["pubName"])}" has no EPUB available'
        if err and err != "INVALID_CODE":
            return None, err
        return None, f'"{code}" not found (check the code and try again)'

    title = html.unescape(data.get("pubName", code))
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
        return None, f'"{html.unescape(data.get("pubName", item["title"]))}" has no EPUB available'
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


def _extract_video_tracks(data, quality=None):
    """Group data["files"][LANG]["MP4"] entries by track number, picking
    ONE rendition per track per VIDEO_LABEL_FALLBACK order (or, if
    `quality` is given, that label first, then the normal fallback order
    for anything without that exact rendition available -- v26.07.20.08,
    added for PicoReader's Streaming Quality setting; NOT used by any
    download call site, which all still call this with quality=None, so
    downloads stay pinned to the original 480p-first default regardless
    of what streaming quality is selected). Returns a list of dicts:
    {"title", "url", "label", "filesize", "track"}. Returns [] if the
    path doesn't exist (e.g. this pub has no videos)."""
    try:
        entries = data["files"][LANG]["MP4"]
    except (KeyError, TypeError):
        return []
    if not isinstance(entries, list):
        return []  # v0.1.140: malformed shape (e.g. a dict instead of a
                   # list) -- treat as "no videos" rather than crash below.

    by_track = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue  # v0.1.140: skip any non-dict entry instead of
                       # crashing on entry.get() -- see VIDEO API NOTES.
        track = entry.get("track")
        label = entry.get("label")
        by_track.setdefault(track, {})[label] = entry

    fallback_order = VIDEO_LABEL_FALLBACK
    if quality and quality in VIDEO_LABEL_FALLBACK:
        fallback_order = [quality] + [l for l in VIDEO_LABEL_FALLBACK if l != quality]

    tracks = []
    for track, by_label in by_track.items():
        chosen = None
        for label in fallback_order:
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


def check_new_gb_updates(limit=None):
    """v0.1.107 (original): Kaleb asked about a Governing Body Updates
    category after list_broadcast_items(). At the time, no dedicated
    category key was found in the Video Library tree, so this scraped
    NEWS_RSS for matching article titles and fetched each article page
    individually to extract a docid, limited to a handful of recent
    items to bound the per-article fetch cost.

    v26.07.15.07 (Kaleb's follow-up -- "is there a category for this?"):
    there is. Confirmed live by walking the VOD category tree:
    VideoOnDemand -> VODStudio -> StudioNewsReports ("News and
    Announcements") contains all Governing Body Update videos as
    regular media entries, not just recent ones -- 56 confirmed live,
    March 2020 (the very first one) through June 2026. Same
    _list_mediator_category_items() helper as JW Broadcasting/Morning
    Worship, filtered to titles containing "Governing Body Update"
    (that category also has ~24 non-GB news/announcement videos mixed
    in, so the filter still matters). Replaces the RSS-scrape +
    per-article-fetch pipeline entirely -- one request now returns the
    complete archive instead of a bounded recent guess, same
    improvement as the Broadcasting/Morning Worship uncapping."""
    items, err = _list_mediator_category_items("StudioNewsReports", "Governing Body Update")
    if err:
        return [], err
    items = [it for it in items if "governing body update" in it.get("title", "").lower()]
    if limit:
        items = items[:limit]
    if not items:
        return [], "No Governing Body Update videos found in the category"
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


def list_mediator_category(key, title, limit=None):
    """v26.07.15.08 (Kaleb's request -- 22 more video categories at
    once): thin public wrapper around _list_mediator_category_items()
    so a new VIDEO_SOURCES entry can just point at a category key/title
    via its "args", the same way list_broadcast_items()/
    list_good_news_items() do internally -- without needing a
    dedicated one-off function per category. All 22 keys below were
    confirmed live this session (category tree walk + media count
    check via MEDIATOR_CATEGORY_URL), not guessed."""
    return _list_mediator_category_items(key, title, limit)


def list_broadcast_items(limit=None):
    """v0.1.106: Kaleb asked for a "check for new videos" feature; no
    dedicated official RSS feed exists for videos (the general
    WHATS_NEW_RSS feed doesn't reliably surface them -- checked a real
    snapshot, zero video items in it), so per Kaleb's direction this
    polls jw.org's own JW Broadcasting monthly-programs category
    directly instead (MEDIATOR_CATEGORY_URL, key="StudioMonthlyPrograms")
    -- confirmed this is what jw.org's own site itself fetches to
    populate that category page (the page's static HTML has no listing
    at all, it's a client-side route). Still 100% jw.org's own
    infrastructure (b.jw-cdn.org), not a third party.

    v26.07.15.06 (Kaleb's request -- same fix as Morning Worship's
    v26.07.15.05): originally capped at limit=12, newest-first, on the
    assumption new-video checks only cared about "what's new," not the
    full archive. Confirmed live the mediator API has no server-side
    pagination here either -- one request to StudioMonthlyPrograms
    already returns the entire category (66 programs, July 2026 back
    to December 2017) in a single response; the cap was purely this
    function truncating it afterward. Removed so the full archive
    reaches main.py's browse screen, same as Morning Worship."""
    return _list_mediator_category_items("StudioMonthlyPrograms", "JW Broadcasting", limit)


def list_good_news_items():
    """v0.1.109: Kaleb asked to add "The Good News According to Jesus"
    (the dramatized episode series about Jesus's life/teachings) as a
    category -- found via the same VideoOnDemand > Series category tree
    already explored for Governing Body Updates (SeriesGoodNews key).
    Confirmed live: 6 episodes as of this writing (pub "gnj"), e.g.
    Episode 1: "The True Light of the World". Small, slow-growing
    catalog (new episodes roughly a few times a year) -- no limit
    needed, just return all of them.

    v26.07.09.14 BUG FIX (Kaleb's report): _list_mediator_category_items()
    sorts by publish date, newest first -- correct for Broadcasting
    ("what's new"), but confirmed live that these episodes were NOT
    published in narrative order (Episode 1 published 2024-12-23,
    Episodes 2-3 on 2026-01-19, Episodes 4-6 on 2026-05-01 -- a
    date-sort scrambles them). Re-sorted here by the actual episode
    number parsed from each title ("Episode N: ..."), ascending, so the
    list reads in watch order. Falls back to leaving publish-date order
    for any title that doesn't match the pattern (future-proofing
    against a title format change upstream, rather than crashing or
    silently mis-sorting)."""
    items, err = _list_mediator_category_items("SeriesGoodNews", "The Good News According to Jesus")
    if items:
        def _episode_num(item):
            m = re.match(r"Episode (\d+)", item.get("title", ""))
            return int(m.group(1)) if m else float("inf")  # unmatched titles sort last
        items.sort(key=_episode_num)
    return items, err


def list_original_songs_items():
    """v26.07.15.03 (Kaleb's request): "Original Songs" -- newer songs
    released outside the printed songbook (distinct project from
    "sjjm"/Sing Out Joyfully to Jehovah, which is the full official
    songbook already offered under AUDIO_SOURCES). Category key
    (VODOriginalSongs) found on jw.org's own site (jw.org/en/library/
    music-songs/original-songs/), confirmed live: 120 items as of this
    writing. These are primarily released as videos (a few also have a
    separate MP3-only release, but there's no reliable single API path
    to those without per-song lookups) -- same _list_mediator_category_items()
    video-shaped result as JW Broadcasting/Good News above, so this
    lives under VIDEO_SOURCES rather than AUDIO_SOURCES. Default
    newest-first date sort (same as Broadcasting) is fine here -- unlike
    Good News above, these aren't a narrative sequence."""
    return _list_mediator_category_items("VODOriginalSongs", "Original Songs")


def list_morning_worship_items(limit=None):
    """v26.07.15.03 (Kaleb's request): "Morning Worship" -- short
    devotional talks from JW Broadcasting, listed separately from the
    main monthly programs (StudioMonthlyPrograms, above). Category key
    (VODPgmEvtMorningWorship) found on jw.org's own Videos library,
    confirmed live: 420 items as of this writing.

    v26.07.15.05 (Kaleb's request -- wanted the full list, not a
    capped page): originally defaulted to limit=60. Confirmed live the
    mediator API has no server-side pagination at all -- one request to
    VODPgmEvtMorningWorship already returns the entire category (all
    420 media entries) in a single JSON response; _list_mediator_
    category_items() was just self-truncating the result afterward with
    media[:limit]. There's no "page down for more" to build against the
    API -- it's already all there. Removed the cap so every entry
    reaches main.py's browse screen, which already scrolls large lists
    fine (Study Watchtower's category is 182 items, same UI path)."""
    return _list_mediator_category_items("VODPgmEvtMorningWorship", "Morning Worship", limit)


# ---------------------------------------------------------------------------
# Free-text search (OmniSearch) -- v0.1.161+
# ---------------------------------------------------------------------------
# Separate service from GETPUBMEDIALINKS. Reverse-engineered live from
# jw.org's own Search page network calls (confirmed, not guessed):
#   1. GET https://b.jw-cdn.org/tokens/jworg.jwt -> a plain-text JWT.
#      Scoped (per its own decoded payload) to filters: all/publications/
#      videos/audio/bible/indexes and sites: jw.org/wol.
#   2. GET https://b.jw-cdn.org/apis/search/results/{lang}/{filter}
#          ?sort=rel&q={query}
#      with header Authorization: Bearer {token}. Confirmed live: without
#      this header the API returns HTTP 200 with a JSON *error body*
#      (status 401 inside the payload, not an HTTP error) -- so callers
#      must check for that shape too, not just catch HTTPError.
# Token is cached in memory and reused until ~30s before its own "exp"
# claim -- avoids fetching a fresh JWT on every search.
SEARCH_TOKEN_URL = "https://b.jw-cdn.org/tokens/jworg.jwt"
SEARCH_API_URL = "https://b.jw-cdn.org/apis/search/results/{lang}/{filter}"

_search_token_cache = {"token": None, "exp": 0}


def clear_search_token_cache():
    """v26.07.09.10: Resets the cached OmniSearch bearer token, forcing the next
    search_jw()/list_items(query=...) call to fetch a brand-new token
    instead of reusing one from an earlier visit to this plugin.

    Called by main.py at the JW plugin's two real exit points (backing
    out of SCREEN_DOWNLOAD_CATEGORIES or SCREEN_DOWNLOAD_BROWSE to
    SCREEN_DOWNLOAD_SOURCES/SCREEN_LIBRARY) -- incognito-style: one
    token per plugin visit, gone the moment you leave, even though the
    token itself would otherwise stay valid for its full ~7-day
    lifetime (confirmed live) if left cached at the module level for
    the rest of the app's process lifetime."""
    _search_token_cache["token"] = None
    _search_token_cache["exp"] = 0


def _jwt_exp(token):
    """Best-effort decode of a JWT's `exp` claim (seconds since epoch),
    without any signature verification -- we don't need to trust the
    token, just know when jw-cdn.org itself says it expires, so we know
    when to fetch a new one. Returns None if anything about the token
    looks unexpected (caller falls back to a short default lifetime)."""
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded)).get("exp")
    except Exception:
        return None


def _get_search_token():
    """Return (token, error). Cached -- see module docstring above."""
    now = time.time()
    if _search_token_cache["token"] and now < _search_token_cache["exp"] - 30:
        return _search_token_cache["token"], None
    req = urllib.request.Request(SEARCH_TOKEN_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            token = resp.read().decode("utf-8", errors="replace").strip()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, str(e)
    if not token:
        return None, "Empty token response"
    exp = _jwt_exp(token) or (now + 300)  # 5 min fallback if exp unreadable
    _search_token_cache["token"] = token
    _search_token_cache["exp"] = exp
    return token, None


def _walk_search_results(node, items, limit):
    """Recursively collect {"type": "item"} entries out of OmniSearch's
    nested results (top-level list of groups, each group has its own
    nested "results" list -- e.g. a "Videos" carousel group alongside
    flatter groups for articles/publications). Three subtypes are
    directly usable by this plugin's existing download machinery:
      - subtype "video"       -> a real playable video (has a lank like
                                  pub-XXX_N_VIDEO, matched by the SAME
                                  _VIDEO_LINK_RE/_VIDEO_DOCID_RE regexes
                                  parse_video_link() already uses for
                                  in-text epub links).
      - subtype "audio"       -> v26.07.10.02: a real downloadable MP3
                                  (lank like pub-XXX_N_AUDIO, same shape
                                  as video's pub-track lanks -- see
                                  _AUDIO_LINK_RE). Confirmed live this
                                  was previously being silently dropped
                                  here even though the raw API already
                                  returned real audio hits (e.g.
                                  filter="audio", q="love" -> 12 results)
                                  -- there was simply no download path
                                  for audio yet when this function was
                                  first written; there is now.
      - subtype "publication" -> a real pub code (lank "pub-XXX") that
                                  MAY have an EPUB -- same as manual
                                  pub-code entry, not verified until
                                  download() actually calls
                                  GETPUBMEDIALINKS, consistent with how
                                  the static catalog already works.
    Everything else (videoCategory, article/"pa-" WOL hits, bible verses,
    etc.) is skipped -- there's no existing download path for those."""
    if limit and len(items) >= limit:
        return
    if isinstance(node, dict):
        if node.get("type") == "item":
            subtype = node.get("subtype")
            lank = node.get("lank") or ""
            title = html.unescape(node.get("title") or "")
            context = node.get("context")
            if subtype == "video" and lank:
                items.append({
                    "title":     title,
                    "subtitle":  html.unescape(context) if context else "Video",
                    "_kind":     "video",
                    "_raw_lank": lank,
                })
            elif subtype == "audio" and lank:
                # v26.07.10.02: same "raw lank, lazy resolve" shape as
                # video -- see resolve_search_audio_item(). "duration" is
                # a real field on audio search results (confirmed live,
                # e.g. "4:16") -- shown in the subtitle same as context
                # would be, since it's more useful here than a text
                # snippet for something you're about to listen to.
                duration = node.get("duration")
                items.append({
                    "title":     title,
                    "subtitle":  duration or (html.unescape(context) if context else "Audio"),
                    "_kind":     "audio",
                    "_raw_lank": lank,
                })
            elif subtype == "publication" and lank.startswith("pub-"):
                code = lank[len("pub-"):]
                sub = f"pub: {code}"
                if context:
                    sub += f"  ({html.unescape(context)})"
                items.append({
                    "title":    title,
                    "subtitle": sub,
                    "filename": f"{code}_{LANG}.epub",
                    "_pub":     code,
                    "_extra":   None,
                    "_kind":    "pub",
                })
        for v in node.values():
            if isinstance(v, (list, dict)):
                _walk_search_results(v, items, limit)
                if limit and len(items) >= limit:
                    return
    elif isinstance(node, list):
        for child in node:
            _walk_search_results(child, items, limit)
            if limit and len(items) >= limit:
                return


def _search_jw_once(query, filter, limit, token):
    """One raw request to OmniSearch. Returns (items, error_message)."""
    url = (SEARCH_API_URL.format(lang=LANG, filter=filter) + "?" +
           urllib.parse.urlencode({"sort": "rel", "q": query}))
    req = urllib.request.Request(url, headers={
        "User-Agent":    USER_AGENT,
        "Accept":        "application/json",
        "Authorization": f"Bearer {token}",
    })
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return [], f"Search failed: {e}"

    # Confirmed live: an auth failure comes back as HTTP 200 with a JSON
    # *list* of RFC-7807-style error objects (status 401 inside), not an
    # HTTPError -- must be checked explicitly, not just caught above.
    if isinstance(data, list):
        detail = data[0].get("title") if data and isinstance(data[0], dict) else None
        return [], f"Search auth error: {detail or 'unknown'}"

    items = []
    _walk_search_results(data.get("results", []), items, limit)
    return items, None


def search_jw(query, filter="all", limit=25):
    """Free-text search against jw.org's real search service (OmniSearch).
    Returns (items, error_message) -- error_message is None on success.

    filter: one of "all", "publications", "videos", "audio", "bible",
    "indexes" (the exact set the search JWT itself is scoped to).

    v0.1.161+: when filter="all" comes back with zero usable items, we
    automatically retry with "publications" then "videos" before giving
    up. Confirmed live this is a real, common gap -- topics like "faith",
    "school", and "daily text" rank WOL articles (which this plugin has
    no download path for) above every actual pub/video in the "all"
    view, even though real matches exist under the narrower filters.
    Only kicks in for the default "all" -- an explicit filter from the
    caller (e.g. the person picked "Videos only") is respected as-is,
    even if it comes back empty, so we don't silently substitute a
    different filter than what was asked for.

    Item dicts come in three flavors, tagged by "_kind":
      "pub"   -- ready to hand straight to download() unchanged (same
                 shape lookup_pub_code()/list_items() already produce).
      "video" -- NOT ready for download_video() yet; only carries
                 "_raw_lank" (no _video_url resolved). Call
                 resolve_search_video_item() on it first -- see that
                 function's docstring for why resolution is lazy here.
      "audio" -- v26.07.10.02: same lazy-resolve shape as "video" --
                 carries "_raw_lank", not ready for download_audio()
                 until resolve_search_audio_item() is called on it."""
    query = (query or "").strip()
    if not query:
        return [], "Enter a search term"
    if len(query) > 200:
        return [], "Search term too long"

    token, err = _get_search_token()
    if err:
        return [], f"Search unavailable: {err}"

    items, err = _search_jw_once(query, filter, limit, token)
    if err:
        return [], err

    if not items and filter == "all":
        for fallback in ("publications", "videos"):
            items, err = _search_jw_once(query, fallback, limit, token)
            if err:
                return [], err
            if items:
                break

    if not items:
        return [], f'No results for "{query}"'
    return items, None


def resolve_search_video_item(item, quality=None):
    """Resolve a "_kind": "video" item from search_jw() into a real
    downloadable item (adds "_video_url") ready for download_video().

    Reuses resolve_video_link() -- the SAME function that already
    resolves in-text video links found inside EPUB chapters -- by
    reconstructing a fake href from the raw lank. This means every edge
    case resolve_video_link() already handles (docid-style links,
    single-video "track=x" pubs, monthly-broadcast pubs needing an
    issue=) is inherited here for free, instead of re-implemented.

    v26.07.20.08: optional `quality`, passed straight through.

    Returns (item, error_message), same contract as resolve_video_link().
    Lazy (called at selection/download time, not at search time) because
    eagerly resolving EVERY video in a result list would mean one extra
    GETPUBMEDIALINKS round-trip per result -- wasteful when the person
    is just browsing search results, not downloading all of them."""
    lank = item.get("_raw_lank")
    if item.get("_kind") != "video" or not lank:
        return None, "Not an unresolved search video item"
    return resolve_video_link("lank=" + lank, quality=quality)


def list_video_items(pub, issue=None, quality=None):
    """Fetch and return the video catalog for a video pub code (e.g. "lffv")
    as a list of item dicts ready for main.py's download-list UI:
    {"title", "subtitle", "filename", "_video_url", "track"}.

    v26.07.20.08: optional `quality` ("480p"/"720p") passed straight to
    _extract_video_tracks() -- see that function's own docstring. None
    (the default, used by every existing call site) preserves the
    original 480p-first behavior exactly.

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

    tracks = _extract_video_tracks(data, quality=quality)
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


def resolve_video_link(href, quality=None):
    """v0.1.98: full resolve for an in-text video link -- parse_video_link()
    then one GETPUBMEDIALINKS call to find the actual video. Returns
    (item, error_message); item is a dict from list_video_items() (or an
    equivalent one built from a docid lookup) ready for download_video(),
    or None on failure.

    v26.07.20.08: optional `quality` ("480p"/"720p"), passed straight
    through to whichever resolver actually runs. None (default, used by
    every download call site) preserves the original 480p-first behavior.

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
        return _resolve_docid_video(ident, quality=quality)
    items, err = list_video_items(ident, issue=issue, quality=quality)
    if err:
        return None, err
    if track == "x":
        return (items[0], None) if items else (None, f'"{ident}" has no videos available')
    for item in items:
        if item.get("track") == track:
            return item, None
    return None, f'Video track {track} not found in "{ident}"'


# v26.07.10.02: audio equivalent of _VIDEO_LINK_RE. Surveyed live this
# session across several search queries ("love", "faith", "prayer",
# "psalm") -- every real audio lank found follows the simple
# "pub-XXX_N_AUDIO" shape (e.g. "pub-osg_102_AUDIO", "pub-sjjc_50_AUDIO",
# "pub-pksjj_137_AUDIO") -- no docid-style or issue-bearing variant seen
# for audio the way video has both. The optional 6-digit issue group is
# kept anyway (same pattern as _VIDEO_LINK_RE) since it costs nothing and
# would just never match if genuinely absent -- safer than assuming this
# survey was exhaustive.
_AUDIO_LINK_RE = re.compile(
    r"lank=pub-([A-Za-z0-9-]+)_(?:(\d{6})_)?(x|\d+)_AUDIO", re.IGNORECASE)


def parse_audio_link(href):
    """v26.07.10.02: audio equivalent of parse_video_link() -- does NOT
    hit the network, just regex matching. Returns (pub, issue, track);
    pub is None if href doesn't match the known audio-link pattern."""
    m = _AUDIO_LINK_RE.search(href or "")
    if not m:
        return None, None, None
    pub, issue, track = m.group(1), m.group(2), m.group(3)
    track = track if track.lower() == "x" else int(track)
    return pub, issue, track


def resolve_audio_link(href):
    """v26.07.10.02: audio equivalent of resolve_video_link() -- one
    list_audio_items() call (no booknum -- every real audio lank found
    this session pointed at song/pub collections like osg/sjjc/sjji/
    pksjj/snv, not NWT Bible-book audio, which isn't linked this way),
    then matches by track number. Returns (item, error_message)."""
    pub, issue, track = parse_audio_link(href)
    if pub is None:
        return None, "Not a recognized audio link"
    items, err = list_audio_items(pub, issue=issue)
    if err:
        return None, err
    if track == "x":
        return (items[0], None) if items else (None, f'"{pub}" has no audio available')
    for item in items:
        if item.get("track") == track:
            return item, None
    return None, f'Audio track {track} not found in "{pub}"'


def resolve_search_audio_item(item):
    """v26.07.10.02: audio equivalent of resolve_search_video_item() --
    same lazy-resolve-at-download-time shape, reusing resolve_audio_link()
    the same way the video version reuses resolve_video_link()."""
    lank = item.get("_raw_lank")
    if item.get("_kind") != "audio" or not lank:
        return None, "Not an unresolved search audio item"
    return resolve_audio_link("lank=" + lank)


def _resolve_docid_video(docid, quality=None):
    """v0.1.104: resolve a docid-based video link (see parse_video_link's
    docstring). GETPUBMEDIALINKS accepts docid as its own top-level param
    (confirmed live -- separate from pub=) and returns a self-contained
    file list for that specific video; the trailing ts=HH:MM:SS-HH:MM:SS
    some of these links carry is a play-range within the video, not a
    separate file, so we download the whole thing same as any other
    link. v26.07.20.08: optional `quality`, same meaning/default as
    list_video_items()'s -- passed straight to _extract_video_tracks()."""
    params = {"docid": docid, "langwritten": LANG, "fileformat": "MP4",
              "alllangs": "0", "output": "json"}
    url = API_BASE + "?" + "&".join(
        f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return None, str(e)
    tracks = _extract_video_tracks(data, quality=quality)
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
    Kaleb's own device screenshot (/mnt/sdcard/ROMS/movies).
    v26.07.18.02 (Kaleb's report): /mnt/union/ROMS/... is muOS's actual
    universal shared ROMS mount (SD1+SD2 merged view) -- confirmed
    earlier for the Ports launcher (see _ports_launcher_path() in
    main.py), but this finder never got the same correction. Added as
    the first candidate; /mnt/sdcard and /mnt/mmc kept as fallbacks for
    setups where /mnt/union isn't present."""
    candidates = [
        "/mnt/union/ROMS/movies",
        "/mnt/sdcard/ROMS/movies",
        "/mnt/mmc/ROMS/movies",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    # Neither exists yet -- default to the union mount and create it so
    # the very first video download on a fresh card still works.
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
    # v26.07.15.16: sanitize with basename() before join -- filename
    # comes from jw.org's API, which is trusted, but this is a cheap
    # defense-in-depth guard against a spoofed/MITM'd response trying
    # to write outside dest_dir via "../" segments. Real filenames are
    # unaffected since basename() only strips path separators.
    safe_filename = os.path.basename(item["filename"])
    dest_path = os.path.join(dest_dir, safe_filename)
    if os.path.exists(dest_path):
        return False, f'"{safe_filename}" already downloaded', dest_path

    video_url = item.get("_video_url")
    if not video_url:
        return False, "No video URL resolved for this item", None
    # v26.07.15.17: see matching comment in gutenberg_fetch.py's
    # download() -- guards against a spoofed API response supplying
    # a non-https URL.
    if not video_url.startswith("https://"):
        return False, "Rejected non-https download URL", None

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


def list_audio_items(pub, issue=None, booknum=None):
    """v26.07.10.01: MP3 equivalent of list_video_items() -- confirmed
    live this session against GETPUBMEDIALINKS?fileformat=MP3 for both
    real cases this is used for: pub=\"nwt\"+booknum (Bible chapter
    audio, e.g. booknum=1 -> 50 Genesis chapters) and pub=\"w\"+issue
    (Watchtower Study Edition per-article audio, e.g. 7 articles for one
    issue). Unlike video, MP3 entries have no rendition/label variants
    to choose between (data[\"files\"][LANG][\"MP3\"] is already a flat
    list, one file per entry) -- confirmed via direct schema inspection,
    so this is simpler than _extract_video_tracks(), no grouping needed.

    Returns (items, error_message), same contract as list_video_items().
    """
    params = {"pub": pub, "langwritten": LANG, "fileformat": "MP3",
              "alllangs": "0", "output": "json"}
    if issue:
        params["issue"] = issue
    if booknum:
        params["booknum"] = str(booknum)
    url = API_BASE + "?" + "&".join(
        f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        data = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return [], str(e)

    try:
        entries = data["files"][LANG]["MP3"]
    except (KeyError, TypeError):
        entries = []
    if not isinstance(entries, list):
        return [], f'"{pub}" has no audio available'

    items = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            url = entry["file"]["url"]
        except (KeyError, TypeError):
            continue
        title = entry.get("title", "audio")
        safe_name = _sanitize_video_filename(title)  # same sanitizer --
                                                       # generic enough,
                                                       # not video-specific
                                                       # despite the name
        size_mb = entry.get("filesize", 0) / (1024 * 1024) if entry.get("filesize") else 0
        items.append({
            "title":       title,
            "subtitle":    f"MP3  ~{size_mb:.1f} MB",
            "filename":    f"{safe_name}.mp3",
            "_audio_url":  url,
            "track":       entry.get("track"),  # v26.07.10.02: needed to
                                                  # match a "lank=pub-X_NN_AUDIO"
                                                  # search result back to
                                                  # the right item, same
                                                  # role list_video_items()'s
                                                  # "track" field already
                                                  # plays for video.
        })
    if not items:
        return [], f'"{pub}" has no audio available'
    return items, None


def list_watchtower_study_audio():
    """v26.07.10.01: AUDIO_SOURCES loader for \"Watchtower Study Audio
    (This Week)\" -- resolves the RSS-confirmed latest Study Edition
    issue itself (same check_new_issues()/current_issue_guess() fallback
    chain generate_mwb_back_issues() already relies on, see its
    v26.07.09.14 BUG FIX comment for why RSS beats a raw calendar
    guess), then calls list_audio_items(pub=\"w\", issue=...) for that
    issue. No booknum/picker needed -- unlike the Bible-audio source,
    there's exactly one \"current\" issue to resolve.
    """
    rss_hit = next((issue for pub, _t, issue in check_new_issues() if pub == "w"), None)
    issue = rss_hit or current_issue_guess()
    return list_audio_items("w", issue=issue)


def list_original_songs_audio():
    """v26.07.15.04 (Kaleb's request, following up on the video-only
    Original Songs entry added under VIDEO_SOURCES): confirmed live via
    jw.org's own finder link (jw.org/finder?...&lank=pub-osg_115_AUDIO)
    that "osg" (Original Songs) has a real standalone MP3 release too --
    list_audio_items("osg") already works with zero changes, same as any
    other pub code (GETPUBMEDIALINKS?pub=osg&fileformat=MP3 returns a
    flat 137-entry list, confirmed live).

    One wrinkle needing a dedicated loader instead of a plain
    AUDIO_SOURCES {"pub": "osg"} entry: about half those 137 entries are
    "(With Audio Descriptions)" narrated duplicates of the other half
    (confirmed live: same songs, titles suffixed, track numbers 500+/
    600+ vs. the plain versions at 1-118) -- filtered out here so the
    picker shows each song once. If audio-described versions are ever
    wanted as their own option, that's a separate AUDIO_SOURCES entry,
    not a flag on this one.
    """
    items, err = list_audio_items("osg")
    if items:
        items = [it for it in items if "(With Audio Descriptions)" not in it.get("title", "")]
    return items, err


def find_music_dir():
    """Locate muOS's native GMU Music Player content folder (ROMS/Music),
    SD1/SD2-aware -- same principle as find_movies_dir() just above.
    v26.07.10.01: \"Music\" (capital M) confirmed against Kaleb's own
    device -- unlike \"movies\", muOS itself has no fixed default naming
    for music content (confirmed via muos.dev docs: content folder names
    are fully user-defined), so this is specifically Kaleb's own setup,
    not a muOS-wide convention.
    v26.07.18.02: /mnt/union/ROMS/... added as first candidate, same
    universal-mount fix as find_movies_dir() -- see that function's
    docstring for the reasoning.
    """
    candidates = [
        "/mnt/union/ROMS/Music",
        "/mnt/sdcard/ROMS/Music",
        "/mnt/mmc/ROMS/Music",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    fallback = candidates[0]
    try:
        os.makedirs(fallback, exist_ok=True)
    except OSError:
        pass
    return fallback


def download_audio(item, dest_dir):
    """Download the MP3 for `item` (from list_audio_items()) into
    dest_dir (normally find_music_dir()'s result). Identical streaming +
    .part-file + atomic-rename pattern as download_video() -- see that
    function's docstring for why each piece matters.

    Returns (ok, message, dest_path) -- same contract as download_video().
    """
    # v26.07.15.16: sanitize with basename() before join -- see the
    # matching comment in download_video() above for why.
    safe_filename = os.path.basename(item["filename"])
    dest_path = os.path.join(dest_dir, safe_filename)
    if os.path.exists(dest_path):
        return False, f'"{safe_filename}" already downloaded', dest_path

    audio_url = item.get("_audio_url")
    if not audio_url:
        return False, "No audio URL resolved for this item", None
    # v26.07.15.17: see matching comment in gutenberg_fetch.py's
    # download().
    if not audio_url.startswith("https://"):
        return False, "Rejected non-https download URL", None

    tmp_path = dest_path + ".part"
    req = urllib.request.Request(audio_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        os.replace(tmp_path, dest_path)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False, f"Download failed: {e}", None

    return True, f'Downloaded "{item["title"]}" to ROMS/Music', dest_path


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
    # v26.07.15.16: sanitize with basename() before join -- see the
    # matching comment in download_video() above for why.
    safe_filename = os.path.basename(item["filename"])
    dest_path = os.path.join(dest_dir, safe_filename)
    if os.path.exists(dest_path):
        return False, f'"{safe_filename}" already in Library', dest_path

    # Step 1: resolve current CDN URL
    epub_url, err = _resolve_download_url(item)
    if err:
        return False, err, None
    if not epub_url:
        return False, "Could not resolve a download link", None
    # v26.07.15.17: see matching comment in gutenberg_fetch.py's
    # download().
    if not epub_url.startswith("https://"):
        return False, "Rejected non-https download URL", None

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
