import re
from string import digits
from time import time
from typing import List, Optional, Any, Tuple, cast
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrule, MONTHLY

from ctparse.time.postprocess_latent import _latent_tod
from ..rule import rule, predicate, dimension, _regex_to_join
from ..types import Time, Duration, Interval, pod_hours, RegexMatch, DurationUnit

_rule_template_uncertainty = r"(?:(?:about|around|approximately)\s+)?{}"

@rule(
    r"at|on|am|um|gegen|den|dem|der|the|ca\.?|approx\.?|about|(in|of)( the)?|around",
    dimension(Time),
)
def ruleAbsorbOnTime(ts: datetime, _: RegexMatch, t: Time) -> Time:
    return t


@rule(r"von|vom|zwischen|from|between", dimension(Interval))
def ruleAbsorbFromInterval(ts: datetime, _: Any, i: Interval) -> Interval:
    return i


_dows = [
    ("mon", r"montags?|mondays?|mon?\.?"),
    ("tue", r"die?nstags?|die?\.?|tuesdays?|tue?\.?"),
    ("wed", r"mittwochs?|mi\.?|wednesday?|wed\.?"),
    ("thu", r"donn?erstags?|don?\.?|thursdays?|thur?\.?"),
    ("fri", r"freitags?|fridays?|fri?\.?"),
    ("sat", r"samstags?|sonnabends?|saturdays?|sat?\.?"),
    ("sun", r"sonntags?|so\.?|sundays?|sun?\.?"),
]
_rule_dows = r"|".join(r"(?P<{}>{})".format(dow, expr) for dow, expr in _dows)
_rule_dows = r"({})\s*".format(_rule_dows)


@rule(_rule_dows)
def ruleNamedDOW(ts: datetime, m: RegexMatch) -> Optional[Time]:
    for i, (name, _) in enumerate(_dows):
        if m.match.group(name):
            return Time(DOW=i)
    return None


_months = [
    ("january", r"january?|jan\.?"),
    ("february", r"february?|feb\.?"),
    ("march", r"märz|march|mar\.?|mrz\.?|mär\.?"),
    ("april", r"april|apr\.?"),
    ("may", r"mai|may\.?"),
    ("june", r"juni|june|jun\.?"),
    ("july", r"juli|july|jul\.?"),
    ("august", r"august|aug\.?"),
    ("september", r"september|sept?\.?"),
    ("october", r"oktober|october|oct\.?|okt\.?"),
    ("november", r"november|nov\.?"),
    ("december", r"december|dezember|dez\.?|dec\.?"),
]
_rule_months = "|".join(r"(?P<{}>{})".format(name, expr) for name, expr in _months)


@rule(_rule_months)
def ruleNamedMonth(ts: datetime, m: RegexMatch) -> Optional[Time]:
    match = m.match
    for i, (name, _) in enumerate(_months):
        if match.group(name):
            return Time(month=i + 1)
    return None


_named_ts = (
    (1, r"one|eins?"),
    (2, r"two|zwei"),
    (3, r"three|drei"),
    (4, r"four|vier"),
    (5, r"five|fünf"),
    (6, r"six|sechs"),
    (7, r"seven|sieben"),
    (8, r"eight|acht"),
    (9, r"nine|neun"),
    (10, r"ten|zehn"),
    (11, r"eleven|elf"),
    (12, r"twelve|zwölf"),
)
_rule_named_ts = "|".join(r"(?P<t_{}>{})".format(n, expr) for n, expr in _named_ts)
_rule_named_ts = r"({})\s*".format(_rule_named_ts)

#Young-Ho: Add about/arount
_rule_named_ts = _rule_template_uncertainty.format(_rule_named_ts)


@rule( _rule_named_ts + r"(uhr|h|o\'?clock)?")
def ruleNamedHour(ts: datetime, m: RegexMatch) -> Optional[Time]:
    match = m.match
    for n, _, in _named_ts:
        if match.group("t_{}".format(n)):
            return Time(hour=n, minute=0, meridiemLatent=True)
    return None


@rule("mitternacht|midnight")
def ruleMidnight(ts: datetime, _: RegexMatch) -> Time:
    return Time(hour=0, minute=0)


def _pod_from_match(pod: str, m: RegexMatch) -> str:
    mod = ""
    if m.match.group("mod_early"):
        mod = "early"
    elif m.match.group("mod_late"):
        mod = "late"
    if m.match.group("mod_very"):
        mod = "very" + mod
    return mod + pod


@rule(
    r"(?P<mod_very>(sehr|very)\s+)?"
    "((?P<mod_early>früh(e(r|n|m))?|early)"
    "|(?P<mod_late>(spät(e(r|n|m))?|late)))",
    predicate("isPOD"),
)
def ruleEarlyLatePOD(ts: datetime, m: RegexMatch, p: Time) -> Time:
    return Time(POD=_pod_from_match(p.POD, m))


_pods = [
    (
        "first",
        (
            r"(erster?|first|earliest|as early|frühe?st(ens?)?|so früh)"
            "( (as )?possible| (wie )?möglich(er?)?)?"
        ),
    ),
    (
        "last",
        (
            r"(letzter?|last|latest|as late as possible|spätest möglich(er?)?|"
            "so spät wie möglich(er?)?)"
        ),
    ),
    ("earlymorning", r"very early|sehr früh"),
    ("lateevening", r"very late|sehr spät"),
    ("morning", r"morning|morgend?s?|(in der )?frühe?|early"),
    ("forenoon", r"forenoon|vormittags?"),
    ("afternoon", r"afternoon|nachmittags?"),
    ("noon", r"noon|mittags?"),
    ("evening", r"evening|tonight|late|abend?s?|spät"),
    ("night", r"night|nachts?"),
]

_rule_pods = "|".join("(?P<{}>{})".format(pod, expr) for pod, expr in _pods)


@rule(_rule_pods)
def rulePOD(ts: datetime, m: RegexMatch) -> Optional[Time]:
    for _, (pod, _) in enumerate(_pods):
        if m.match.group(pod):
            return Time(POD=pod)
    return None


@rule(r"(?<!\d|\.)(?P<day>(?&_day))\.?(?!\d)")
def ruleDOM1(ts: datetime, m: RegexMatch) -> Time:
    # Ordinal day "5."
    return Time(day=int(m.match.group("day")))


@rule(r"(?<!\d|\.)(?P<month>(?&_month))\.?(?!\d)")
def ruleMonthOrdinal(ts: datetime, m: RegexMatch) -> Time:
    # Ordinal day "5."
    return Time(month=int(m.match.group("month")))


@rule(r"(?<!\d|\.)(?P<day>(?&_day))\s*(?:st|nd|rd|th|s?ten|ter)")
# a "[0-31]" followed by a th/st
def ruleDOM2(ts: datetime, m: RegexMatch) -> Time:
    return Time(day=int(m.match.group("day")))


@rule(r"(?<!\d|\.)(?P<year>(?&_year))(?!\d)")
def ruleYear(ts: datetime, m: RegexMatch) -> Time:
    # Since we may have two-digits years, we have to make a call
    # on how to handle which century does the time refers to.
    # We are using a strategy inspired by excel. Reference:
    # https://github.com/comtravo/ctparse/issues/56
    # https://docs.microsoft.com/en-us/office/troubleshoot/excel/two-digit-year-numbers
    y = int(m.match.group("year"))
    SAME_CENTURY_THRESHOLD = 10

    # Let the reference year be ccyy (e.g. 1983 => cc=19, yy=83)
    cc = ts.year // 100
    yy = ts.year % 100
    # Check if year is two digits
    if y < 100:
        # Then any two digit year between 0 and
        # yy+10 is interpreted to be within the
        #  century cc (e.g. 83 maps to 1983, 93 to 1993),
        # anything above maps to the previous century (e.g. 94 maps to 1894).
        if y < yy + SAME_CENTURY_THRESHOLD:
            return Time(year=cc * 100 + y)
        else:
            return Time(year=(cc - 1) * 100 + y)
    else:
        return Time(year=y)


@rule(
    r"heute|(um diese zeit|zu dieser zeit|um diesen zeitpunkt|zu diesem zeitpunkt)|"
    "todays?|(at this time)"
)
def ruleToday(ts: datetime, _: RegexMatch) -> Time:
    return Time(year=ts.year, month=ts.month, day=ts.day)


@rule(
    r"(genau\s*)?jetzt|diesen moment|in diesem moment|gerade eben|"
    r"((just|right)\s*)?now|immediately"
)
def ruleNow(ts: datetime, _: RegexMatch) -> Time:
    return Time(
        year=ts.year, month=ts.month, day=ts.day, hour=ts.hour, minute=ts.minute
    )


@rule(r"morgen|tmrw?|tomm?or?rows?")
def ruleTomorrow(ts: datetime, _: RegexMatch) -> Time:
    dm = ts + relativedelta(days=1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(r"übermorgen")
def ruleAfterTomorrow(ts: datetime, _: RegexMatch) -> Time:
    dm = ts + relativedelta(days=2)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(r"gestern|yesterdays?")
def ruleYesterday(ts: datetime, _: RegexMatch) -> Time:
    dm = ts + relativedelta(days=-1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(r"vor\s?gestern")
def ruleBeforeYesterday(ts: datetime, _: RegexMatch) -> Time:
    dm = ts + relativedelta(days=-2)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(r"(das )?ende (des|dieses) monats?|(the )?(EOM|end of (the )?month)")
def ruleEOM(ts: datetime, _: RegexMatch) -> Time:
    dm = ts + relativedelta(day=1, months=1, days=-1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(
    r"(das )?(EOY|jahr(es)? ?ende|ende (des )?jahr(es)?)|"
    r"(the )?(EOY|end of (the )?year)"
)
def ruleEOY(ts: datetime, _: RegexMatch) -> Time:
    dm = ts + relativedelta(day=1, month=1, years=1, days=-1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(predicate("isDOM"), predicate("isMonth"))
def ruleDOMMonth(ts: datetime, dom: Time, m: Time) -> Time:
    return Time(day=dom.day, month=m.month)


@rule(predicate("isDOM"), r"of", predicate("isMonth"))
def ruleDOMMonth2(ts: datetime, dom: Time, _: RegexMatch, m: Time) -> Time:
    return Time(day=dom.day, month=m.month)


@rule(predicate("isMonth"), predicate("isDOM"))
def ruleMonthDOM(ts: datetime, m: Time, dom: Time) -> Time:
    return Time(month=m.month, day=dom.day)


@rule(r"am|diese(n|m)|at|on|this", predicate("isDOW"))
def ruleAtDOW(ts: datetime, _: RegexMatch, dow: Time) -> Time:
    dm = ts + relativedelta(weekday=dow.DOW)
    if dm.date() == ts.date():
        dm += relativedelta(weeks=1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(
    r"((am )?(dem |den )?((kommenden?|nächsten?)( Woche)?))|"
    "((on |at )?(the )?((next|following)( week)?))",
    predicate("isDOW"),
)
def ruleNextDOW(ts: datetime, _: RegexMatch, dow: Time) -> Time:
    dm = ts + relativedelta(weekday=dow.DOW, weeks=1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(predicate("isDOW"), r"((kommende|nächste) Woche)|((next|following) week)")
def ruleDOWNextWeek(ts: datetime, dow: Time, _: RegexMatch) -> Time:
    dm = ts + relativedelta(weekday=dow.DOW, weeks=1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(predicate("isDOY"), predicate("isYear"))
def ruleDOYYear(ts: datetime, doy: Time, y: Time) -> Time:
    return Time(year=y.year, month=doy.month, day=doy.day)


@rule(predicate("isDOW"), predicate("isPOD"))
def ruleDOWPOD(ts: datetime, dow: Time, pod: Time) -> Time:
    return Time(DOW=dow.DOW, POD=pod.POD)


@rule(predicate("isDOW"), predicate("isDOM"))
def ruleDOWDOM(ts: datetime, dow: Time, dom: Time) -> Time:
    # Monday 5th
    # Find next date at this day of week and day of month
    dm = rrule(MONTHLY, dtstart=ts, byweekday=dow.DOW, bymonthday=dom.day, count=1)[0]
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(predicate("hasDOW"), predicate("isDate"))
def ruleDOWDate(ts: datetime, dow: Time, date: Time) -> Time:
    # Monday 5th December - ignore DOW, but carry over e.g. POD from dow
    return Time(date.year, date.month, date.day, POD=dow.POD)


@rule(predicate("isDate"), predicate("hasDOW"))
def ruleDateDOW(ts: datetime, date: Time, dow: Time) -> Time:
    # Monday 5th December - ignore DOW, but carry over e.g. POD from dow
    return Time(date.year, date.month, date.day, POD=dow.POD)


# LatentX: handle time entities that are not grounded to a date yet
# and assume the next date+time in the future
@rule(predicate("isDOM"))
def ruleLatentDOM(ts: datetime, dom: Time) -> Time:
    dm = ts + relativedelta(day=dom.day)
    if dm <= ts:
        dm += relativedelta(months=1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(predicate("isDOW"))
def ruleLatentDOW(ts: datetime, dow: Time) -> Time:
    dm = ts + relativedelta(weekday=dow.DOW)
    if dm <= ts:
        dm += relativedelta(weeks=1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(predicate("isDOY"))
def ruleLatentDOY(ts: datetime, doy: Time) -> Time:
    dm = ts + relativedelta(month=doy.month, day=doy.day)
    if dm < ts:
        dm += relativedelta(years=1)
    return Time(year=dm.year, month=dm.month, day=dm.day)


@rule(predicate("isPOD"))
def ruleLatentPOD(ts: datetime, pod: Time) -> Time:
    # Set the time to the pre-defined POD values, but keep the POD
    # information. The date is chosen based on what ever is the next
    # possible slot for these times
    h_from, h_to = pod_hours[pod.POD]
    t_from = ts + relativedelta(hour=h_from, minute=0)
    if t_from <= ts:
        t_from += relativedelta(days=1)
    return Time(year=t_from.year, month=t_from.month, day=t_from.day, POD=pod.POD)


@rule(
    r"(?<!\d|\.)(?P<day>(?&_day))[\./\-]"
    r"((?P<month>(?&_month))|(?P<named_month>({})))\.?"
    r"(?!\d|am|\s*pm)".format(_rule_months)
)
# do not allow dd.ddam, dd.ddpm, but allow dd.dd am - e.g. in the German
# "13.06 am Nachmittag"
def ruleDDMM(ts: datetime, m: RegexMatch) -> Time:
    if m.match.group("month"):
        month = int(m.match.group("month"))
    else:
        for i, (name, _) in enumerate(_months):
            if m.match.group(name):
                month = i + 1
    return Time(month=month, day=int(m.match.group("day")))


@rule(
    r"(?<!\d|\.)((?P<month>(?&_month))|(?P<named_month>({})))[/\-]"
    r"(?P<day>(?&_day))"
    r"(?!\d|am|\s*pm)".format(_rule_months)
)
def ruleMMDD(ts: datetime, m: RegexMatch) -> Time:
    if m.match.group("month"):
        month = int(m.match.group("month"))
    else:
        for i, (name, _) in enumerate(_months):
            if m.match.group(name):
                month = i + 1
    return Time(month=month, day=int(m.match.group("day")))


@rule(
    r"(?<!\d|\.)(?P<day>(?&_day))[-/\.]"
    r"((?P<month>(?&_month))|(?P<named_month>({})))[-/\.]"
    r"(?P<year>(?&_year))(?!\d)".format(_rule_months)
)
def ruleDDMMYYYY(ts: datetime, m: RegexMatch) -> Time:
    y = int(m.match.group("year"))
    if y < 100:
        y += 2000
    if m.match.group("month"):
        month = int(m.match.group("month"))
    else:
        for i, (name, _) in enumerate(_months):
            if m.match.group(name):
                month = i + 1
    return Time(year=y, month=month, day=int(m.match.group("day")))


def _is_valid_military_time(ts: datetime, t: Time) -> bool:
    if t.hour is None or t.minute is None:
        return False

    t_year = t.hour * 100 + t.minute
    # Military times (i.e. no separator) are notriously difficult to
    # distinguish from yyyy; these are some heuristics to avoid an abundance
    # of false positives for hhmm
    #
    # If hhmm is the current year -> assume it is a year
    if t_year == ts.year:
        return False
    # If hhmm is the year in 3 month from now -> same, prefer year
    if t_year == (ts + relativedelta(months=3)).year:
        return False
    # If the minutes is not a multiple of 5 prefer year.
    # Since military times are typically used for flights,
    # and flight times are only multiples of 5, we use this heuristic as evidence
    # for military times.
    if t.minute % 5:
        return False
    return True


def _maybe_apply_am_pm(t: Time, ampm_match: str) -> Time:

    if not t.hour:
        return t
    if ampm_match is None:
        print("am pm latent.")
        t.meridiemLatent = True
        return t
    if ampm_match.lower().startswith("a") and t.hour <= 12:
        t.meridiemLatent = False
        return t
    if ampm_match.lower().startswith("p") and t.hour < 12:
        return Time(hour=t.hour + 12, minute=t.minute, meridiemLatent=False)
    # the case ampm_match.startswith('a') and t.hour >
    # 12 (e.g. 13:30am) makes no sense, lets ignore the ampm
    # likewise if hour >= 12 no 'pm' action is needed
    return t


@rule(
    # match hhmm
    r"(?<!\d|\.)(?P<hour>(?:[01]\d)|(?:2[0-3]))(?P<minute>(?&_minute))"
    r"\s*(?P<clock>uhr|h)?"  # optional uhr
    r"\s*(?P<ampm>\s*[ap]\.?m\.?)?(?!\d)"  # optional am/pm
)
def ruleHHMMmilitary(ts: datetime, m: RegexMatch) -> Optional[Time]:
    t = Time(hour=int(m.match.group("hour")), minute=int(m.match.group("minute") or 0))
    if m.match.group("clock") or _is_valid_military_time(ts, t):
        return _maybe_apply_am_pm(t, m.match.group("ampm"))
    return None


@rule(
    r"(?<!\d|\.)"  # We don't start matching with another number, or a dot
    r"(?P<hour>(?&_hour))"  # We certainly match an hour
    # We try to match also the minute
    r"((?P<sep>:|uhr|h|\.)(?P<minute>(?&_minute)))?"
    r"\s*(?P<clock>uhr|h)?"  # We match uhr with no minute
    r"(?P<ampm>\s*[ap]\.?m\.?)?"  # AM PM
    r"(?!\d)"
)
def ruleHHMM(ts: datetime, m: RegexMatch) -> Time:
    # hh [am|pm]
    # hh:mm
    # hhmm
    t = Time(hour=int(m.match.group("hour")), minute=int(m.match.group("minute") or 0))
    return _maybe_apply_am_pm(t, m.match.group("ampm"))


@rule(r"(?<!\d|\.)(?P<hour>(?&_hour))\s*(uhr|h|o\'?clock)")
def ruleHHOClock(ts: datetime, m: RegexMatch) -> Time:
    return Time(hour=int(m.match.group("hour")))


@rule(r"(a |one )?quarter( to| till| before| of)|vie?rtel vor", predicate("isTOD"))
def ruleQuarterBeforeHH(ts: datetime, _: RegexMatch, t: Time) -> Optional[Time]:
    # no quarter past hh:mm where mm is not 0 or missing
    if t.minute:
        return None
    if t.hour > 0:
        return Time(hour=t.hour - 1, minute=45)
    else:
        return Time(hour=23, minute=45)


@rule(r"((a |one )?quarter( after| past)|vie?rtel nach)", predicate("isTOD"))
def ruleQuarterAfterHH(ts: datetime, _: RegexMatch, t: Time) -> Optional[Time]:
    if t.minute:
        return None
    return Time(hour=t.hour, minute=15)


@rule(r"halfe?( to| till| before| of)?|halb( vor)?", predicate("isTOD"))
def ruleHalfBeforeHH(ts: datetime, _: RegexMatch, t: Time) -> Optional[Time]:
    if t.minute:
        return None
    if t.hour > 0:
        return Time(hour=t.hour - 1, minute=30)
    else:
        return Time(hour=23, minute=30)


@rule(r"halfe?( after| past)|halb nach", predicate("isTOD"))
def ruleHalfAfterHH(ts: datetime, _: RegexMatch, t: Time) -> Optional[Time]:
    if t.minute:
        return None
    return Time(hour=t.hour, minute=30)


@rule(predicate("isTOD"), predicate("isPOD"))
def ruleTODPOD(ts: datetime, tod: Time, pod: Time) -> Optional[Time]:
    # time of day may only be an hour as in "3 in the afternoon"; this
    # is only relevant for time <= 12
    if tod.hour < 12 and (
        "afternoon" in pod.POD
        or "evening" in pod.POD
        or "night" in pod.POD
        or "last" in pod.POD
    ):
        h = tod.hour + 12
    elif tod.hour > 12 and (
        "forenoon" in pod.POD or "morning" in pod.POD or "first" in pod.POD
    ):
        # 17Uhr morgen -> do not merge
        return None
    else:
        h = tod.hour
    return Time(hour=h, minute=tod.minute)


@rule(predicate("isPOD"), predicate("isTOD"))
def rulePODTOD(ts: datetime, pod: Time, tod: Time) -> Optional[Time]:
    return cast(Time, ruleTODPOD(ts, tod, pod))


@rule(predicate("isDate"), predicate("isTOD"))
def ruleDateTOD(ts: datetime, date: Time, tod: Time) -> Time:
    return Time(
        year=date.year, month=date.month, day=date.day, hour=tod.hour, minute=tod.minute
    )


@rule(predicate("isTOD"), predicate("isDate"))
def ruleTODDate(ts: datetime, tod: Time, date: Time) -> Time:
    return Time(
        year=date.year, month=date.month, day=date.day, hour=tod.hour, minute=tod.minute
    )


@rule(predicate("isDate"), predicate("isPOD"))
def ruleDatePOD(ts: datetime, d: Time, pod: Time) -> Time:
    return Time(year=d.year, month=d.month, day=d.day, POD=pod.POD)


@rule(predicate("isPOD"), predicate("isDate"))
def rulePODDate(ts: datetime, pod: Time, d: Time) -> Time:
    return Time(year=d.year, month=d.month, day=d.day, POD=pod.POD)


@rule(
    r"((?P<not>not |nicht )?(vor|before))|(bis )?spätestens( bis)?|bis|latest",
    dimension(Time),
)
def ruleBeforeTime(ts: datetime, r: RegexMatch, t: Time) -> Interval:
    if r.match.group("not"):
        return Interval(t_from=t, t_to=None)
    else:
        return Interval(t_from=None, t_to=t)


@rule(
    r"((?P<not>not |nicht )?(nach|after))|(ab )?frühe?stens( ab)?|ab|"
    "(from )?earliest( after)?|from",
    dimension(Time),
)
def ruleAfterTime(ts: datetime, r: RegexMatch, t: Time) -> Interval:
    if r.match.group("not"):
        return Interval(t_from=None, t_to=t)
    else:
        return Interval(t_from=t, t_to=None)


@rule(predicate("isDate"), _regex_to_join, predicate("isDate"))
def ruleDateDate(ts: datetime, d1: Time, _: RegexMatch, d2: Time) -> Optional[Interval]:
    if d1.year > d2.year:
        return None
    if d1.year == d2.year and d1.month > d2.month:
        return None
    if d1.year == d2.year and d1.month == d2.month and d1.day >= d2.day:
        return None
    return Interval(t_from=d1, t_to=d2)


@rule(predicate("isDOM"), _regex_to_join, predicate("isDate"))
def ruleDOMDate(ts: datetime, d1: Time, _: RegexMatch, d2: Time) -> Optional[Interval]:
    if d1.day >= d2.day:
        return None
    return Interval(t_from=Time(year=d2.year, month=d2.month, day=d1.day), t_to=d2)


@rule(predicate("isDate"), _regex_to_join, predicate("isDOM"))
def ruleDateDOM(ts: datetime, d1: Time, _: RegexMatch, d2: Time) -> Optional[Interval]:
    if d1.day >= d2.day:
        return None
    return Interval(t_from=d1, t_to=Time(year=d1.year, month=d1.month, day=d2.day))


@rule(predicate("isDOY"), _regex_to_join, predicate("isDate"))
def ruleDOYDate(ts: datetime, d1: Time, _: RegexMatch, d2: Time) -> Optional[Interval]:
    if d1.month > d2.month:
        return None
    elif d1.month == d2.month and d1.day >= d2.day:
        return None
    return Interval(t_from=Time(year=d2.year, month=d1.month, day=d1.day), t_to=d2)


@rule(predicate("isDateTime"), _regex_to_join, predicate("isDateTime"))
def ruleDateTimeDateTime(
    ts: datetime, d1: Time, _: RegexMatch, d2: Time
) -> Optional[Interval]:
    if d1.year > d2.year:
        return None
    if d1.year == d2.year and d1.month > d2.month:
        return None
    if d1.year == d2.year and d1.month == d2.month and d1.day > d2.day:
        return None
    if (
        d1.year == d2.year
        and d1.month == d2.month
        and d1.day == d2.day
        and d1.hour > d2.hour
    ):
        return None
    if (
        d1.year == d2.year
        and d1.month == d2.month
        and d1.day == d2.day
        and d1.hour == d2.hour
        and d1.minute >= d2.minute
    ):
        return None
    return Interval(t_from=d1, t_to=d2)


@rule(predicate("isTOD"), _regex_to_join, predicate("isTOD"))
def ruleTODTOD(ts: datetime, t1: Time, _: RegexMatch, t2: Time) -> Interval:
    return Interval(t_from=t1, t_to=t2)


@rule(predicate("isPOD"), _regex_to_join, predicate("isPOD"))
def rulePODPOD(ts: datetime, t1: Time, _: RegexMatch, t2: Time) -> Interval:
    return Interval(t_from=t1, t_to=t2)


@rule(predicate("isDate"), dimension(Interval))
def ruleDateInterval(ts: datetime, d: Time, i: Interval) -> Optional[Interval]:
    if not (
        (i.t_from is None or i.t_from.isTOD or i.t_from.isPOD)
        and (i.t_to is None or i.t_to.isTOD or i.t_to.isPOD)
    ):
        return None
    t_from = t_to = None
    if i.t_from is not None:
        t_from = Time(
            year=d.year,
            month=d.month,
            day=d.day,
            hour=i.t_from.hour,
            minute=i.t_from.minute,
            POD=i.t_from.POD,
        )
    if i.t_to is not None:
        t_to = Time(
            year=d.year,
            month=d.month,
            day=d.day,
            hour=i.t_to.hour,
            minute=i.t_to.minute,
            POD=i.t_to.POD,
        )
    # This is for wrapping time around a date.
    # Mon, Nov 13 11:30 PM - 3:35 AM
    if t_from and t_to and t_from.dt >= t_to.dt:
        t_to_dt = t_to.dt + relativedelta(days=1)
        t_to = Time(
            year=t_to_dt.year,
            month=t_to_dt.month,
            day=t_to_dt.day,
            hour=t_to_dt.hour,
            minute=t_to_dt.minute,
            POD=t_to.POD,
        )
    return Interval(t_from=t_from, t_to=t_to)


@rule(predicate("isPOD"), dimension(Interval))
def rulePODInterval(ts: datetime, p: Time, i: Interval) -> Optional[Interval]:
    def _adjust_h(t: Time) -> Optional[int]:
        if t.hour is None:
            return None
        if t.hour < 12 and (
            "afternoon" in p.POD
            or "evening" in p.POD
            or "night" in p.POD
            or "last" in p.POD
        ):
            return t.hour + 12
        else:
            return t.hour

    # only makes sense if i is a time interval
    if not (
        (i.t_from is None or i.t_from.hasTime) and (i.t_to is None or i.t_to.hasTime)
    ):
        return None
    t_to = t_from = None
    if i.t_to is not None:
        t_to = Time(
            year=i.t_to.year,
            month=i.t_to.month,
            day=i.t_to.day,
            hour=_adjust_h(i.t_to),
            minute=i.t_to.minute,
            DOW=i.t_to.DOW,
        )
    if i.t_from is not None:
        t_from = Time(
            year=i.t_from.year,
            month=i.t_from.month,
            day=i.t_from.day,
            hour=_adjust_h(i.t_from),
            minute=i.t_from.minute,
            DOW=i.t_from.DOW,
        )
    return Interval(t_from=t_from, t_to=t_to)



_named_number = (
    (1, r"an?|one"),
    (2, r"two"),
    (3, r"three"),
    (4, r"four"),
    (5, r"five"),
    (6, r"six"),
    (7, r"seven"),
    (8, r"eight"),
    (9, r"nine"),
    (10, r"ten"),
    (11, r"eleven"),
    (12, r"twelve"),
    (13, r"thirteen"),
    (14, r"fourteen"),
    (15, r"fifteen"),
    (16, r"sixteen"),
    (17, r"seventeen"),
    (18, r"eighteen"),
    (19, r"nineteen"),
    (20, r"twenty")
)

_tens = ["ten", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_ones = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]

def _get_human_readable_number_regex_larger_than_20(n: int) -> Optional[str]:
    hundreds = n // 100
    tens = (n - hundreds * 100) // 10
    ones = (n - hundreds * 100 - tens * 10) % 10

    res = ""

    if hundreds >= 10:
        return None
    else:
        if hundreds > 0:
            res += _named_number[hundreds-1][1] + r"\s+hundreds?\s+(?:and\s+)?"
        if tens > 0:
            if ones == 0:
                res += _tens[tens-1]
            else:
                res += "{t}{o}|{t}-{o}|(?:{t} {o})".format(t=_tens[tens-1] ,o=_ones[ones-1]) 
        else:
            if ones > 0:
                res += _ones[ones-1]
        
        return res

_named_number += tuple((i, _get_human_readable_number_regex_larger_than_20(i)) for i in range(21, 60))

def _make_rule_named_number(l:List[Tuple[int, str]], group_name_prefix="n_")->str:
    rule = "|".join(r"(?P<{}{}>{}\b)".format(group_name_prefix, n, expr) for n, expr in l)
    return rule

_rule_named_number = _make_rule_named_number(_named_number)
_rule_named_number = r"({})\s+".format(_rule_named_number)
_rule_named_number = _rule_template_uncertainty.format(_rule_named_number) 

_durations = [
    (DurationUnit.NIGHTS, r"nights?"),
    (DurationUnit.DAYS, r"days?"),
    (DurationUnit.MINUTES, r"m(?:inutes?)?"),
    (DurationUnit.HOURS, r"h(?:ours?)?"),
    (DurationUnit.WEEKS, r"weeks?"),
    (DurationUnit.MONTHS, r"months?"),
]


_rule_durations = r"|".join(
    r"(?P<d_{}>{}\b)".format(dur.value, expr) for dur, expr in _durations
)
_rule_durations = r"({})\s*".format(_rule_durations)


# Rules regarding durations
@rule(_rule_template_uncertainty.format(r"(?P<num>\d+)\s+") + _rule_durations)
def ruleDigitDuration(ts: datetime, m: RegexMatch) -> Optional[Duration]:
    # 1 day, 1 night etc.
    num = m.match.group("num")
    if num:
        for n, _, in _durations:
            unit = m.match.group("d_" + n.value)
            if unit:
                return Duration(int(num), n)

    return None


@rule(_rule_named_number + _rule_durations)
def ruleNamedNumberDuration(ts: datetime, m: RegexMatch) -> Optional[Duration]:
    # one day, two nights, thirty days etc.
    num = None
    for n, _ in _named_number:
        match = m.match.group("n_{}".format(n))
        if match:
            num = n
            continue

    if num:
        for d, _, in _durations:
            unit = m.match.group("d_" + d.value)
            if unit:
                return Duration(num, d)

    return None


@rule(r"(?:an?\s+)?(hal[fb]e?|1/2)(\s+(?:of\s+)?an?)?\s*" + _rule_durations)
def ruleDurationHalf(ts: datetime, m: RegexMatch) -> Optional[Duration]:
    # half day, half hour, 1/2 hour
    for n, _, in _durations:
        if m.match.group("d_" + n.value):
            if n == DurationUnit.HOURS:
                return Duration(30, DurationUnit.MINUTES, {"fraction": "half"})
            if n == DurationUnit.DAYS:
                return Duration(12, DurationUnit.HOURS, {"fraction": "half"})

    return None


@rule(r"(?:an?\s+)?(quarter|1/4)(\s+(?:of\s+)?an?)?\s+" + _rule_durations)
def ruleDurationQuarter(ts: datetime, m: RegexMatch) -> Optional[Duration]:
    # quarter day, quarter hour, 1/4 hour
    for n, _, in _durations:
        if m.match.group("d_" + n.value):
            if n == DurationUnit.HOURS:
                return Duration(15, DurationUnit.MINUTES, {"fraction": "quarter"})
            if n == DurationUnit.DAYS:
                return Duration(8, DurationUnit.HOURS, {"fraction": "quarter"})

    return None

@rule(predicate("isDateInterval"), r"f[üo]r", dimension(Duration))
def ruleIntervalConjDuration(
    ts: datetime, interval: Interval, _: RegexMatch, dur: Duration
) -> Optional[Interval]:
    # Example: people tend to repeat themselves when specifying durations
    # 15-16 Nov für 1 Nacht
    return ruleDurationInterval(ts, dur, interval)  # type: ignore


@rule(predicate("isDateInterval"), dimension(Duration))
def ruleIntervalDuration(
    ts: datetime, interval: Interval, dur: Duration
) -> Optional[Interval]:
    # Variant without conjunction
    # 15-16 Nov 1 Nacht
    return ruleDurationInterval(ts, dur, interval)  # type: ignore


@rule(dimension(Duration), predicate("isDateInterval"))
def ruleDurationInterval(
    ts: datetime, dur: Duration, interval: Interval
) -> Optional[Interval]:
    # 3 days 15-18 Nov
    delta = interval.t_to.dt - interval.t_from.dt
    dur_delta = _duration_to_relativedelta(dur)
    if delta.days == dur_delta.days:
        return interval
    return None


@rule(predicate("hasDate"), r"f[üo]r", dimension(Duration))
def ruleTimeDuration(
    ts: datetime, t: Time, _: RegexMatch, dur: Duration
) -> Optional[Interval]:
    # Examples:
    # on the 27th for one day
    # heute eine Übernachtung

    # To make an interval we should at least have a date
    if dur.unit in (
        DurationUnit.DAYS,
        DurationUnit.NIGHTS,
        DurationUnit.WEEKS,
        DurationUnit.MONTHS,
    ):
        delta = _duration_to_relativedelta(dur)
        end_ts = t.dt + delta
        # We the end of the interval is a date without particular times
        end = Time(year=end_ts.year, month=end_ts.month, day=end_ts.day)
        return Interval(t_from=t, t_to=end)

    if dur.unit in (DurationUnit.HOURS, DurationUnit.MINUTES):
        delta = _duration_to_relativedelta(dur)
        end_ts = t.dt + delta
        end = Time(
            year=end_ts.year,
            month=end_ts.month,
            day=end_ts.day,
            hour=end_ts.hour,
            minute=end_ts.minute,
        )
        return Interval(t_from=t, t_to=end)
    return None


def _duration_to_relativedelta(dur: Duration) -> relativedelta:
    return {
        DurationUnit.DAYS: relativedelta(days=dur.value),
        DurationUnit.NIGHTS: relativedelta(days=dur.value),
        DurationUnit.WEEKS: relativedelta(weeks=dur.value),
        DurationUnit.MONTHS: relativedelta(months=dur.value),
        DurationUnit.HOURS: relativedelta(hours=dur.value),
        DurationUnit.MINUTES: relativedelta(minutes=dur.value),
    }[dur.unit]


#Appended rules######################


@rule(dimension(Duration), r"ago|before")
def ruleDurationAgo(ts: datetime, dur: Duration, _: RegexMatch) -> Time:
    # Example:
    # 5 days ago
    # 3 weeks before
    delta = _duration_to_relativedelta(dur)
    time = ts - delta
    return Time(year = time.year, month = time.month, day=time.day, hour=time.hour, minute=time.minute)


#only elapsed duration
@rule(r"for", dimension(Duration))
def ruleElapsedDuration(ts: datetime, _1: RegexMatch, dur: Duration) -> Interval:
    delta = _duration_to_relativedelta(dur)
    start_ts = ts - delta
    start = Time(year=start_ts.year, month=start_ts.month, day=start_ts.day, hour=start_ts.hour, minute=start_ts.minute)
    return Interval(t_from=start, t_to=Time(year=ts.year, month=ts.month, day=ts.day, hour=ts.hour, minute=ts.minute))

#time + duration
@rule(r"from|since", dimension(Time), r"for", dimension(Duration))
def ruleTimeDurationTime(ts: datetime, _1: RegexMatch, t: Time, _2: RegexMatch, dur: Duration) -> Interval:
    delta = _duration_to_relativedelta(dur)
    
    end = None
    if t.isDateTime:
        end_ts = t.dt + delta
        end = Time(year=end_ts.year, month=end_ts.month, day=end_ts.day, hour=end_ts.hour, minute=end_ts.minute)
    else:
        #Latent time
        end_ts = _latent_tod(ts, t).dt + delta
        if t.isDate:
            end = Time(year=end_ts.year, month=end_ts.month, day=end_ts.day)
        elif t.isTOD:
            end = Time(year=t.year, month=t.month, day=t.day, hour=end_ts.hour, minute=end_ts.minute)
        
    return Interval(t_from=t, t_to=end)


@rule(dimension(Duration), dimension(Duration))
def ruleDurationDuration(ts: datetime, dur1: Duration, dur2: Duration) -> Optional[Duration]:
    if dur1.unit == DurationUnit.DAYS and (dur2.unit == DurationUnit.HOURS or dur2.unit == DurationUnit.MINUTES):
        if dur2.unit == DurationUnit.HOURS:
            return Duration(dur1.value * 24 + dur2.value, DurationUnit.HOURS)
        elif dur2.unit == DurationUnit.MINUTES:
            return Duration(dur1.value * 24 * 60 + dur2.value, DurationUnit.MINUTES)
        else: return None
    elif dur1.unit == DurationUnit.HOURS and dur2.unit == DurationUnit.MINUTES:
        return Duration(dur1.value * 60 + dur2.value, DurationUnit.MINUTES)

@rule(dimension(Duration), r"and", dimension(Duration))
def ruleDurationAndDuration(ts: datetime, dur1: Duration, _: RegexMatch, dur2: Duration) -> Optional[Duration]:
   return ruleDurationDuration(ts, dur1, dur2)

@rule(dimension(Duration), r"and (?:a\s+)?half")
def ruleDurationAndHalf(ts: datetime, dur1: Duration, _: RegexMatch) -> Optional[Duration]:
    if dur1.unit == DurationUnit.HOURS:
        return Duration(dur1.value * 60 + 30, DurationUnit.MINUTES)
    elif dur1.unit == DurationUnit.DAYS:
        return Duration(dur1.value * 24 + 12, DurationUnit.HOURS)
    else:
        return None


#Modified by Young-Ho

@rule(r"(?P<left>\d+)(?P<separator>\.|\/)(?P<right>\d+)\s+" + r"(?:of\s+)?(?:an?\s+)?" + _rule_durations)
def ruleRatialDuration(ts: datetime, m: RegexMatch) -> Optional[Duration]:
    separator = m.match.group("separator")

    if separator == ".":
        # 1.5 day, 1.5 hours etc.
        digit = m.match.group("left")
        decimal = m.match.group("right")

        if digit:
            for n, _, in _durations:
                unit = m.match.group("d_" + n.value)
                if unit:
                    if decimal:
                        if n.value == "hours":
                            return Duration(round(int(digit) * 60 + float("0." +decimal) * 60), DurationUnit.MINUTES, tag={"fraction": digit +"." + decimal})
                        elif n.value == "days":
                            return Duration(round(int(digit) * 24 + float("0." +decimal) * 24), DurationUnit.HOURS, tag={"fraction": digit +"." + decimal})
                    else:
                        return Duration(int(digit), n)
    elif separator == "/":
         # 1/2 day, 1/4 huors etc.

        numerator = m.match.group("left")
        denominator = m.match.group("right")

        if numerator and denominator:
            for n, _, in _durations:
                unit = m.match.group("d_" + n.value)
                if unit:
                    ratio = int(numerator) / int(denominator)
                    if n.value == "hours":
                        return Duration(round(ratio * 60), DurationUnit.MINUTES, {"fraction": ratio})
                    elif n.value == "days":
                        return Duration(round(ratio * 24), DurationUnit.HOURS, {"fraction": ratio})
               
    return None

def _ruleDigitAndFractionDuration(digit: int, dur: Duration) -> Optional[Duration]:

    if dur.unit == DurationUnit.HOURS:
        return Duration(digit * 24 + dur.value, DurationUnit.HOURS)
    elif dur.unit == DurationUnit.MINUTES:
        return Duration(digit * 60 + dur.value, DurationUnit.MINUTES)

    return None

@rule(r"(?:(?P<num>\d+)|{})(?:\s+and)?".format(_make_rule_named_number(_named_number[0:23], "digit_")), predicate("isFractionalDuration"))
def ruleDigitAndFractionDuration(ts: datetime, m: RegexMatch, dur: Duration) -> Optional[Duration]:

    digit = None
    if m.match.group("num"):
        digit = int(m.match.group("num"))
    else:
        for n in range(1,24):
            if m.match.group("digit_" + str(n)):
                digit = n
                break
    
    if digit:
        return _ruleDigitAndFractionDuration(digit, dur)
    else: return None

_rule_duration_fractions = r"(?P<frac_digit>\d+)|"+_make_rule_named_number(_named_number[0:3], "frac_c_")

_rule_duration_fractions = r"({})\s+".format(_rule_duration_fractions)
_rule_duration_fractions = _rule_template_uncertainty.format(_rule_duration_fractions) 


_fractions = [(4, r"quarters?"), (2, r"hal(?:f|ves)"), (3, r"thirds?")]
_rule_fractions = "|".join(r"(?P<frac1_{}>{})".format(n, r) for n, r in _fractions)

_rule_duration_fractions += r"({})\s+".format(_rule_fractions) + r"(?:of\s+)?(?:an?\s+)?" + r"(?:{})\b".format(r"|".join(
    r"(?P<d_{}>{}\b)".format(dur.value, expr) for dur, expr in _durations)
)

@rule(_rule_duration_fractions)
def ruleDurationFraction(ts: datetime, m: RegexMatch) -> Optional[Duration]:
    # half day, half hour, 1/2 hour, 3 quarters of day

    fraction = None

    #Find base fraction
    for n, _, in _fractions:
        if m.match.group("frac1_" + str(n)):
            fraction = 1/n
            break    
    
    if fraction is None:
        return None

    #Find fraction multiples
    if m.match.group("frac_digit"):
        digit = m.match.group("frac_digit")
        fraction *= int(digit)
    else:
        for n in range(1,4):
            if m.match.group("frac_c_" + str(n)):
                fraction *= n
                break
    
    #Find duration unit
    for n, _, in _durations:
        unit = m.match.group("d_" + n.value)
        if unit:
            if n.value == "hours":
                return Duration(round(fraction * 60), DurationUnit.MINUTES, tag={"fraction": fraction})
            elif n.value == "days":
                return Duration(round(fraction * 24), DurationUnit.HOURS, tag={"fraction": fraction})

    return None