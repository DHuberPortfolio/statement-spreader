"""Which table is which statement, what its columns' periods are, and what unit it is in."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass

from .contracts import Period, RawTable, Scale, StatementType
from .layout import Layout
from .numbers import clean_label, clean_text
from .profile import Profile, matches

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_name) if m})
_MONTHS["sept"] = 9

_FULL_DATE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})\s*,?\s*(\d{4})\b", re.I)
_DAY_FIRST = re.compile(
    r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?,?\s+(\d{4})\b", re.I)
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_MONTH_DAY = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})\b", re.I)
_MONTH_YEAR = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?,?\s+(\d{4})\b", re.I)
_YEAR = re.compile(r"(?<!\d)(19[5-9]\d|20\d\d)(?!\d)")
_FY_SHORT = re.compile(r"\bfy\s*'?(\d{2})\b", re.I)
_COMPARISON = re.compile(r"%|\bchange\b|increase|decrease|\bvariance\b|\bfavorable\b|\bunfavorable\b", re.I)

_DURATIONS = [
    (re.compile(r"\b(three|3)[\s-]+months?\b|\bquarter\b|\b13 weeks\b", re.I), 3),
    (re.compile(r"\b(six|6)[\s-]+months?\b|\b26 weeks\b|\bhalf[\s-]year\b", re.I), 6),
    (re.compile(r"\b(nine|9)[\s-]+months?\b|\b39 weeks\b", re.I), 9),
    (re.compile(r"\b(twelve|12)[\s-]+months?\b|\byears?\b|\bfiscal\b|\bannual\b|\b5[23] weeks\b|\bfy\b", re.I), 12),
]

_SCALE_WORDS = {"thousand": 1_000, "thousands": 1_000, "million": 1_000_000, "millions": 1_000_000,
                "billion": 1_000_000_000, "billions": 1_000_000_000, "000": 1_000, "000s": 1_000, "000's": 1_000}
_SCALE = re.compile(
    r"(?:in|amounts? in|expressed in|stated in|reported in|presented in)\s+(?:u\.?s\.?\s+)?\$?\s*(?:dollars\s+in\s+)?"
    r"(thousands|millions|billions)"
    r"|\(\s*\$?\s*(?:in\s+)?(thousands|millions|billions|000s?|000's)\s*(?:of\s+(?:u\.?s\.?\s+)?dollars)?"
    r"|(thousands|millions|billions) of (?:u\.?s\.?\s+)?dollars"
    r"|\$\s*(000s?|000's)\b|\(\$000\)|(000s?|000's) omitted"
    r"|\$\s*in\s+(thousands|millions|billions)"
    r"|(?:^|[(\[|;:])\s*(?:u\.?s\.?\s+)?(?:\$|dollars|usd)?\s*(thousands|millions|billions)\b(?=\s*(?:,|\)|except|of|$))"
    r"|\b(thousands|millions|billions)\s*,?\s*except\b",
    re.I,
)
_SHARE_SCALE = re.compile(
    r"shares?\b[^.;)]{0,60}?\bin\s+(thousands|millions)"
    r"|(thousands|millions)\s+of\s+shares",
    re.I,
)
_SHARES_UNITS = re.compile(r"except\s+(?:for\s+)?(?:number of\s+)?shares?(?!\s+(?:which|are|in))|except\s+share\s+(?:and|data)", re.I)


def _last(rx: re.Pattern[str], text: str) -> re.Match[str] | None:
    found = list(rx.finditer(text))
    return found[-1] if found else None


def _first_group(m: re.Match[str]) -> str:
    return next(g for g in m.groups() if g)


@dataclass
class Detection:
    statement: StatementType
    score: float


def classify(layout: Layout, table: RawTable, profile: Profile) -> Detection | None:
    """Score the table against each statement's detection rules; None when nothing fits."""
    labels = [clean_label(r.label) for r in layout.rows if r.label]
    if len(labels) < 4:
        return None
    best: Detection | None = None
    for stype, sdef in profile.statements.items():
        d = sdef.detect
        must = sum(1 for lab in labels if any(matches(p, lab) for p in d.must_any))
        if not must:
            continue
        also = sum(1 for lab in labels if any(matches(p, lab) for p in d.also_any))
        excl = sum(1 for lab in labels if any(matches(p, lab) for p in d.exclude_any))
        if excl:
            continue
        # How many distinct template lines the table's labels hit: a primary statement hits many,
        # a summary table in management's discussion hits a few.
        hits = set()
        for lab in labels:
            for line in sdef.lines:
                if any(matches(p, lab) for p in line.aliases):
                    hits.add(line.id)
                    break
        score = 2.0 * min(must, 2) + min(also, 6) + 1.5 * len(hits) + 0.02 * len(labels)
        if not layout.slots:
            score -= 5
        # A management-discussion table compares years ("% change", "Increase/(decrease)");
        # a primary statement does not.
        if any(_COMPARISON.search(s.header or "") for s in layout.slots):
            score -= 12
        if best is None or score > best.score:
            best = Detection(stype, score)
    if best and best.score < 8:
        return None
    return best


def _date(y: int, m: int, d: int) -> str | None:
    try:
        last = calendar.monthrange(y, m)[1]
    except (ValueError, calendar.IllegalMonthError):
        return None
    if not 1 <= d <= last:
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


_PERIOD_PHRASE = re.compile(
    r"\b(?:years?|fiscal\s+years?|twelve\s+months|(?:three|six|nine)\s+months|quarters?|periods?|weeks?)\s+end(?:ed|ing)\s+"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})\b"
    r"|\b(?:as\s+of|as\s+at)\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})\b",
    re.I)


def title_period_hints(text: str) -> tuple[tuple[int, int] | None, int | None, str]:
    """Month/day and period length printed in a statement's title ("Years ended June 30").

    Only a date after period wording counts ("years ended June 30", "as of December 31"): the
    text near a statement also holds audit-report and signature dates, which are not periods.
    """
    t = clean_text(text)
    md: tuple[int, int] | None = None
    for m in _PERIOD_PHRASE.finditer(t):
        g = [x for x in m.groups() if x]
        mon = _MONTHS.get(g[0].lower()[:3])
        day = int(g[1])
        if mon and 1 <= day <= 31:
            md = (mon, day)
            break  # callers pass the most specific text first
    months = None
    for rx, n in _DURATIONS:
        if rx.search(t):
            months = n
            break
    return md, months, t[-160:]


def parse_period(header: str, statement: StatementType, fallback_month_day: tuple[int, int] | None = None,
                 title: str = "") -> Period | None:
    """Turn a column header into a Period, recording anything that had to be assumed.

    title is the statement's title and unit text; when a column prints only "2025", the month
    and day ("Years ended June 30") and the period length usually live there.
    """
    text = clean_text(header)
    assumed: list[str] = []
    notes: list[str] = []
    title_md, title_months, _ = title_period_hints(title) if title else (None, None, "")
    if title and not _FULL_DATE.search(text) and not _MONTH_DAY.search(text) and _YEAR.search(text):
        year = _YEAR.findall(text)[-1]
        # "Fiscal years ended December 27, 2025, December 28, 2024 and ..." names each year's date.
        exact = {m.group(3): (m.group(1), m.group(2)) for m in _FULL_DATE.finditer(clean_text(title))}
        if year in exact:
            text = f"{exact[year][0]} {exact[year][1]}, {text}"
            notes.append(f"Month and day read from the title ({exact[year][0]} {exact[year][1]}, {year}).")
        elif title_md:
            text = f"{calendar.month_name[title_md[0]]} {title_md[1]}, {text}"
            notes.append(f"Month and day read from the title ({calendar.month_name[title_md[0]]} {title_md[1]}).")
    if title_months and statement is not StatementType.BALANCE and not any(rx.search(text) for rx, _ in _DURATIONS):
        text = f"{'Year' if title_months == 12 else f'{title_months} months'} ended {text}"
    end: str | None = None
    # The last date in the header text is the column's own (spanning text comes first).
    m = _last(_FULL_DATE, text)
    if m:
        end = _date(int(m.group(3)), _MONTHS[m.group(1).lower()[:3]], int(m.group(2)))
    if end is None:
        m2 = _last(_DAY_FIRST, text)
        if m2:
            end = _date(int(m2.group(3)), _MONTHS[m2.group(2).lower()[:3]], int(m2.group(1)))
    if end is None:
        m3 = _last(_NUMERIC_DATE, text)
        if m3:
            y = int(m3.group(3))
            y = y + 2000 if y < 100 else y
            end = _date(y, int(m3.group(1)), int(m3.group(2)))
    if end is None:
        years = _YEAR.findall(text)
        fy = _FY_SHORT.search(text)
        year = int(years[-1]) if years else (2000 + int(fy.group(1)) if fy else None)
        if year is None:
            return None
        md = _MONTH_DAY.search(text)
        my = _MONTH_YEAR.search(text)
        if md and _MONTHS.get(md.group(1).lower()[:3]):
            end = _date(year, _MONTHS[md.group(1).lower()[:3]], int(md.group(2)))
        elif my and _MONTHS.get(my.group(1).lower()[:3]):
            mm = _MONTHS[my.group(1).lower()[:3]]
            end = _date(year, mm, calendar.monthrange(year, mm)[1])
        elif fallback_month_day:
            end = _date(year, *fallback_month_day)
            assumed.append(f"Only the year is printed; the month and day were taken from another column ({end}).")
        if end is None:
            end = f"{year:04d}-12-31"
            assumed.append("Only the year is printed; the period is assumed to end on December 31.")
    months: int | None = None
    if statement is StatementType.BALANCE:
        months = None
    else:
        for rx, n in _DURATIONS:
            if rx.search(text):
                months = n
                break
        if months is None:
            months = 12
            assumed.append("The column does not say how long the period is; assumed to be a full year.")
    key = f"{end}/{'I' if months is None else f'{months}M'}"
    return Period(key=key, end=end, months=months, label=clean_text(header) or text, assumed=assumed, notes=notes)


def detect_scale(texts: list[str]) -> tuple[Scale, Scale | None]:
    """Find the unit statement ("in millions, except per share amounts") nearest the table.

    texts are ordered nearest first (the table's own title rows, then the text above it).
    Returns the money scale and, when stated separately, the share-count scale.
    """
    money: Scale | None = None
    shares: Scale | None = None
    for n, text in enumerate(texts):
        if not text:
            continue
        t = clean_text(text)
        if money is None:
            # A match right after "shares ..." describes share counts, not money.
            ms = [m for m in _SCALE.finditer(t) if "share" not in t[max(0, m.start() - 45): m.start()].lower()]
            if ms:
                # Inside the table the first statement wins; in the text above it, the nearest (last).
                m = ms[0] if n < 2 else ms[-1]
                word = _first_group(m).lower()
                money = Scale(multiplier=_SCALE_WORDS[word], evidence=m.group(0).strip())
                sm = _SHARE_SCALE.search(t[max(0, m.start() - 20): m.end() + 200])
                if sm:
                    shares = Scale(multiplier=_SCALE_WORDS[_first_group(sm).lower()], evidence=sm.group(0).strip())
                elif _SHARES_UNITS.search(t[m.start(): m.end() + 120]):
                    shares = Scale(multiplier=1, evidence="share counts excepted from the unit statement")
        if money is not None:
            break
    if money is None:
        return Scale(multiplier=1, evidence="No unit statement (such as 'in thousands') was found near the table.",
                     assumed=True), None
    return money, shares
