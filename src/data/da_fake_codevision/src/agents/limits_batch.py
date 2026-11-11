"""Made-up caller 2 (a batch job) of the made-up expiry report. Not real UOB code."""

from agents import limits_expiry_report as report


def run_batch(customers):
    builder = report.ExpiryReport()
    return [builder.build_line(name, 20) for name in customers] + [report.days_left(5, 1)]
