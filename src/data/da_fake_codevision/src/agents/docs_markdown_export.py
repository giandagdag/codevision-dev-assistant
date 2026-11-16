"""Made-up helper: writes a report as a Markdown file. Not real UOB code."""


def write_report_file(title, lines, path):
    """Creates a Markdown document with a heading and one bullet per line."""
    body = [f"# {title}", ""] + [f"- {line}" for line in lines]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(body))
    return path
