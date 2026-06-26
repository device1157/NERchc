from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalendarConversion:
    calendar_date: str | None
    date_precision: str
    calendar_source: str
    calendar_confidence: float


def convert_exact_date(
    ce_year: int | None,
    lunar_month: int | None,
    lunar_day: int | None,
    ganzhi: str | None = None,
) -> CalendarConversion:
    if ce_year is None:
        return CalendarConversion(None, "unknown", "no_ce_year", 0.0)
    if not lunar_month or not lunar_day:
        return CalendarConversion(None, "estimated_year", "reign_year_rule", 0.45)
    if not (1 <= lunar_month <= 12 and 1 <= lunar_day <= 30):
        return CalendarConversion(None, "estimated_year", "invalid_lunar_components", 0.2)
    exact = _try_lunisolar_conversion(ce_year, lunar_month, lunar_day)
    if exact:
        source = "lunisolar_converter"
        confidence = 0.72
        if ganzhi:
            source += "_unchecked_ganzhi"
            confidence = 0.68
        return CalendarConversion(exact, "exact_day", source, confidence)
    return CalendarConversion(None, "estimated_year", "exact_mapping_unavailable", 0.45)


def _try_lunisolar_conversion(ce_year: int, lunar_month: int, lunar_day: int) -> str | None:
    try:
        from lunardate import LunarDate  # type: ignore
    except Exception:
        return None
    try:
        return LunarDate(ce_year, lunar_month, lunar_day).toSolarDate().isoformat()
    except Exception:
        return None
