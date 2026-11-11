"""Made-up program for the Enhance tests: a customer limits expiry report. Not real UOB code."""

DATE_FORMAT = "%d/%m/%Y"


def format_expiry(day, month, year):
    """Turn a date into the text shown on the report."""
    return f"{day:02d}/{month:02d}/{year}"


def days_left(expiry_day, today_day):
    """How many days remain before a limit expires. Never below zero."""
    return max(expiry_day - today_day, 0)


class ExpiryReport:
    def build_line(self, customer, expiry_day):
        return f"{customer}: {days_left(expiry_day, 10)} days left"
