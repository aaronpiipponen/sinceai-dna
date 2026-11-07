# -*- coding: utf-8 -*-
"""Lexical fact check shared by the handoff brief and the rejected verifier experiment.

One job: report tokens in generated text that the input does not carry.

    from grounding import unknown_facts
    invented = unknown_facts([sentence], source)

One regex per token class. A token the text uses that INPUT does not carry is
treated as invented. This is a lexical guard only: it cannot prove a
sentence's meaning, and it accepts a number reused in a different context.

Standard library only.
"""

import re

_TOKEN = re.compile(r"\S+")
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I)
_DOMAIN = re.compile(r"(?<![\w@])(?:[\w-]+\.)+[A-Za-z]{2,}\b")
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
_SNAKE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")
_DOTTED = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]+)+\b")
_DATE_ISO = re.compile(r"(?<![\d-])(\d{4})-(\d{1,2})-(\d{1,2})(?![\d-])")
_DATE_DMY = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\d.])")
_DATE_DM = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(?![\d.])")
# The clock part of an ISO timestamp in INPUT, and the readable form a person
# writes instead ("9.34", "9:34"). Guards keep a date or a decimal out.
_ISO_TIME = re.compile(r"\d{4}-\d{1,2}-\d{1,2}[T ](\d{1,2}):(\d{2})")
_CLOCK = re.compile(r"(?<![\d.])(\d{1,2})[:.](\d{2})(?![\d.])")
_SENTENCE_END = re.compile(r"[.:!?]\s+$")
_TRIM = ".,;:!?()[]{}\"'“”‘’…"
_MONEY = "€$£¥%"
# A numeric token/prefix. Letters end it, so "4800euros" still checks the
# amount while a URL or a domain is left to its own exact check.
_NUM_LEAD = re.compile(r"[+\-]?\d[\d\s.,:/()\-]*")


def _tokens(text):
    return [t.strip(_TRIM) for t in _TOKEN.findall(text)]


def _dates(text):
    """Every date in a string as (month, day, year-or-None).

    The guards stop a decimal, IP address or phone group being read as a
    day.month pair; a full date must also carry its year so a changed year
    cannot fall back to the yearless form in the same token.
    """
    found = set()
    for year, month, day in _DATE_ISO.findall(text):
        found.add((int(month), int(day), int(year)))
    for day, month, year in _DATE_DMY.findall(text):
        found.add((int(month), int(day), int(year)))
    for day, month in _DATE_DM.findall(text):
        found.add((int(month), int(day), None))
    return found


def _number_key(token):
    """A comparable key for a numeric token, or None for a date/word.

    The key keeps the token's shape: 480 is not 4800, and 2,90 is not 290.
    Comma and dot decimals compare as the same decimal, which is the one
    harmless reformatting we accept.
    """
    text = token.strip(_TRIM + _MONEY)
    match = _NUM_LEAD.match(text)
    if not match:
        return None
    core = match.group(0).rstrip(".,:/-")
    if not core or not any(c.isdigit() for c in core) or _dates(core):
        return None
    sign, body = "", core
    if body[0] in "+-":
        sign, body = body[0], body[1:]
    if not body:
        return None
    if re.fullmatch(r"\d+[.,]\d{1,2}", body):
        whole, fraction = re.split(r"[.,]", body)
        return ("decimal", sign, whole, fraction)
    if body.isdigit():
        return ("int", sign, body)
    return ("other", sign, re.sub(r"\s+", "", body).replace(",", "."))


def _fact_part(word):
    """The part of a capitalised token that must appear in INPUT.

    Finnish and Swedish compound and inflect an acronym freely: INPUT says
    "SIM-päivitystä" and the text says "SIM-korttiin", so the whole token
    would never match. Only the acronym is the fact; the tail is grammar.
    """
    head, sep, _tail = word.partition("-")
    if sep and len(head) >= 2 and head.isupper():
        return head
    return word


def _same_date(a, b):
    month, day, year = a
    other_month, other_day, other_year = b
    if (month, day) != (other_month, other_day):
        return False
    return year is None or other_year is None or year == other_year


def strings(value):
    """Every string in a nested list/dict, so one check covers a whole brief."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def unknown_facts(texts, source):
    """Tokens in `texts` that do not appear in the exact input message."""
    rejected = set()
    lower = source.lower()
    source_dates = _dates(source)
    # A readable time ("yesterday at 9.34") is the same fact as the clock
    # part of an ISO timestamp in INPUT, so it is not an invention.
    source_times = set()
    # Numbers are compared as whole tokens. A number inside a URL, domain or
    # date must not vouch for a standalone amount, and neither must a
    # substring of a longer number (480 in 4800, 1111 in 11119).
    source_numbers = set()
    for token in _tokens(source):
        for hour, minute in _ISO_TIME.findall(token):
            source_times.add((int(hour), int(minute)))
        if (_URL.search(token) or _EMAIL.search(token) or _DOMAIN.search(token)
                or _DOTTED.search(token)):
            continue
        if _SNAKE.search(token):
            # An identifier can carry a fact as a digit run: "behind_30d" says
            # updates are 30 days behind, which the text may state in words.
            for run in re.findall(r"\d+", token):
                source_numbers.add(("int", "", run))
            continue
        key = _number_key(token)
        if key is not None:
            source_numbers.add(key)
    for text in texts:
        for token in _tokens(text):
            if any(c.isdigit() for c in token):
                token_dates = _dates(token)
                if token_dates:
                    # A reformatted date is still the same fact, but a
                    # different year is a different date.
                    if not all(any(_same_date(d, s) for s in source_dates)
                               for d in token_dates):
                        rejected.add(token)
                    continue
                clock = _CLOCK.fullmatch(token)
                if clock and (int(clock.group(1)), int(clock.group(2))) in source_times:
                    continue
                if (_URL.search(token) or _EMAIL.search(token)
                        or _DOMAIN.search(token) or _SNAKE.search(token)
                        or _DOTTED.search(token)):
                    # URLs, addresses and identifiers have their own exact
                    # checks below; their digits are not standalone numbers.
                    continue
                key = _number_key(token)
                if key is not None and key not in source_numbers:
                    rejected.add(token)
        for match in _SNAKE.finditer(text):
            rejected.add(match.group(0))
        for match in _DOTTED.finditer(text):
            value = match.group(0)
            if value.lower() not in lower:
                rejected.add(value)
        for pattern in (_URL, _EMAIL, _DOMAIN):
            for match in pattern.finditer(text):
                value = match.group(0).strip(_TRIM)
                if value and value.lower() not in lower:
                    rejected.add(value)
        body = text.strip()
        for match in _WORD.finditer(body):
            word = match.group(0)
            if len(word) < 3 or not word[0].isupper() or word.upper() == "DNA":
                continue
            if match.start() == 0 or _SENTENCE_END.search(body[:match.start()]):
                continue
            if _fact_part(word).lower() not in lower:
                rejected.add(word)
    return sorted(rejected)
