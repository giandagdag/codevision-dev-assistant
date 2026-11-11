"""Made-up caller 1 (a screen) of the made-up expiry report. Not real UOB code."""

from agents.limits_expiry_report import format_expiry


def show_expiry():
    return format_expiry(1, 2, 2027)
