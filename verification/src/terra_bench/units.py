"""Small spelling normalizer, not dimensional conversion or fuzzy unit matching."""
import re

# Spelling/context aliases, never scale conversion. The independent numerical
# oracle still checks the indicator, denominator, years and arithmetic. A unit
# label is not evidence that the correct measurement was calculated.
ALIASES = {
    'm3/person/year': 'm^3 per person per year',
    'm3/capita/year': 'm^3 per person per year',
    'm^3 per year per person': 'm^3 per person per year',
    'm3 per person per year': 'm^3 per person per year',
    'm3 per capita per year': 'm^3 per person per year',
    'm^3 per capita per year': 'm^3 per person per year',
    "%": "percent", "% of population": "percent", "percent of population": "percent",
    "% of internal resources": "percent of internal freshwater resources",
    "% of internal freshwater resources": "percent of internal freshwater resources",
    "percentage points (2021 minus 2011)": "percentage points",
}


def unit_spelling(value):
    value = str(value).replace("³", "^3").replace("²", "^2")
    value = re.sub(r"\b(km|m|cm)([23])\b", r"\1^\2", value)
    value = re.sub(r"\s*/\s*", " per ", value)
    value = " ".join(value.split())
    return ALIASES.get(value, value)


def same_unit(actual, expected):
    return isinstance(actual, str) and unit_spelling(actual) == unit_spelling(expected)


def label_has_unit(label, unit):
    candidates = [unit, unit_spelling(unit), *(key for key, value in ALIASES.items() if value == unit_spelling(unit))]
    def included(candidate, text):
        pattern = (r"(?<!\w)" if candidate[0].isalnum() else "") + re.escape(candidate)
        pattern += r"(?!\w)" if candidate[-1].isalnum() else ""
        return re.search(pattern, text) is not None
    return any(included(candidate, label) or included(unit_spelling(candidate), unit_spelling(label))
               for candidate in candidates if candidate)
