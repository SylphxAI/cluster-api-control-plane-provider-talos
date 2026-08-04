#!/usr/bin/env python3
"""Normalize Kres-generated GitHub Actions jobs to owned runner profiles.

Kres v26be706 generates maintenance jobs on `ubuntu-latest` and its generated
workflow jobs using the opaque `generic` runner group.  This fork owns the
runner-policy boundary, so the Kres post-generation hook deterministically
rewrites all generated jobs to the explicit owned Linux profile.  The same
normalizer is used by `make rekres` and --check makes generator drift fail
closed in CI.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WORKFLOWS = (
    Path('.github/workflows/ci.yaml'),
    Path('.github/workflows/lock.yml'),
    Path('.github/workflows/stale.yml'),
    Path('.github/workflows/slack-notify.yaml'),
    Path('.github/workflows/slack-notify-ci-failure.yaml'),
)
OWNED_RUNNER = '[self-hosted, sylphx-linux-standard]'

# Kres emits these selections with the runner value on the next YAML line.
GENERIC_GROUP = re.compile(
    r'(?m)^(?P<indent>[ \t]*)runs-on:[ \t]*\n(?P=indent)[ \t]{2}group:[ \t]*generic[ \t]*$'
)
GITHUB_HOSTED_LIST = re.compile(
    r'(?m)^(?P<indent>[ \t]*)runs-on:[ \t]*\n(?P=indent)[ \t]{2}-[ \t]*ubuntu-latest[ \t]*$'
)


def strip_comment(line: str) -> str:
    quote: str | None = None
    for index, character in enumerate(line):
        if quote is None and character in ('"', "'"):
            quote = character
        elif quote == character:
            quote = None
        elif quote is None and character == '#':
            return line[:index]
    return line


def normalize(content: str) -> str:
    content = GENERIC_GROUP.sub(
        lambda match: f"{match.group('indent')}runs-on: {OWNED_RUNNER}", content
    )
    return GITHUB_HOSTED_LIST.sub(
        lambda match: f"{match.group('indent')}runs-on: {OWNED_RUNNER}", content
    )


def validate(path: Path, content: str) -> list[str]:
    violations: list[str] = []
    lines = content.splitlines()
    for line_number, raw_line in enumerate(lines, start=1):
        line = strip_comment(raw_line).rstrip()
        if not re.match(r'^\s*runs-on\s*:', line):
            continue
        match = re.match(r'^\s*runs-on\s*:\s*(.*?)\s*$', line)
        assert match is not None
        value = match.group(1)
        if value != OWNED_RUNNER:
            violations.append(
                f'{path}:{line_number}: expected runs-on: {OWNED_RUNNER!r}, got {value!r}'
            )
    if not any(re.match(r'^\s*runs-on\s*:', strip_comment(line)) for line in lines):
        violations.append(f'{path}: no runs-on selection found')
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='fail if normalization would change a workflow')
    arguments = parser.parse_args()
    errors: list[str] = []
    changed: list[Path] = []

    for path in WORKFLOWS:
        if not path.is_file():
            errors.append(f'{path}: required Kres-generated workflow is missing')
            continue
        original = path.read_text()
        rendered = normalize(original)
        if arguments.check and rendered != original:
            errors.append(f'{path}: Kres output is not normalized; run make rekres')
        elif not arguments.check and rendered != original:
            path.write_text(rendered)
            changed.append(path)
        errors.extend(validate(path, rendered))

    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    if changed:
        print('normalized ' + ', '.join(str(path) for path in changed))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
