#!/usr/bin/env python3
"""Compute the next MAJOR.MINOR.PATCH version from the latest git v* release tag."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

_VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _parse_version(raw: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.fullmatch(raw.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _format_version(version: tuple[int, int, int]) -> str:
    return f"{version[0]}.{version[1]}.{version[2]}"


def _latest_release_tag(merged: str | None = None) -> tuple[str, tuple[int, int, int]]:
    command = ["git", "tag", "-l", "v*", "--sort=-v:refname"]
    if merged is not None:
        command.extend(["--merged", merged])

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Unable to list git tags: {result.stderr.strip()}")

    for line in result.stdout.splitlines():
        tag = line.strip()
        if not tag:
            continue
        parsed = _parse_version(tag)
        if parsed is None:
            print(f"Skipping non-release tag {tag!r}", file=sys.stderr)
            continue
        return tag, parsed

    scope = f" reachable from {merged}" if merged is not None else ""
    raise SystemExit(f"No git tags matching vMAJOR.MINOR.PATCH found{scope}; create an initial release tag first.")


def _bump(version: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    if part == "patch":
        return major, minor, patch + 1
    raise SystemExit(f"Unsupported bump {part!r}; expected major, minor, or patch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bump",
        required=True,
        choices=("major", "minor", "patch"),
        help="Which semver component to increment from the latest vMAJOR.MINOR.PATCH tag",
    )
    parser.add_argument(
        "--merged",
        metavar="COMMIT",
        help="Only consider tags reachable from this commit (git tag --merged)",
    )
    args = parser.parse_args(argv)

    current_tag, current = _latest_release_tag(args.merged)
    nxt = _bump(current, args.bump)
    print(_format_version(nxt), flush=True)
    print(
        f"Bumped {current_tag} --{args.bump}-> v{_format_version(nxt)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
