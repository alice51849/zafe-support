#!/usr/bin/env python3
"""Fail-closed repository lint for Zafe's generated support surfaces."""
from __future__ import annotations

import hashlib
import html
import re
import subprocess
import sys
from pathlib import Path

from tools.support_surfaces import check, load_source


ROOT = Path(__file__).resolve().parent
EMAIL = "hourstag.app@gmail.com"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
ATTR_RE = re.compile(r"\b([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*([\"'])(.*?)\2", re.S)
PUBLIC_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".txt", ".xml"}


def node_check(arguments: list[str], body: str | None = None) -> str | None:
    result = subprocess.run(
        arguments,
        input=body,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return detail[-1] if detail else f"exit {result.returncode}"
    return None


def main() -> int:
    errors: list[str] = []
    try:
        result = check(load_source())
    except (OSError, ValueError, SystemExit) as error:
        errors.append(f"surface checker failed: {error}")
        result = {}

    unique_inline: dict[tuple[str, str], tuple[str, str]] = {}
    inline_count = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.casefold() in PUBLIC_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            unexpected = sorted(
                {
                    address
                    for address in EMAIL_RE.findall(text)
                    if address.casefold() != EMAIL
                }
            )
            if unexpected:
                errors.append(
                    f"{path.relative_to(ROOT)}: unapproved public emails {unexpected}"
                )
        if path.suffix.casefold() != ".html":
            continue
        for attributes, body in SCRIPT_RE.findall(text):
            attrs = {
                match.group(1).casefold(): html.unescape(match.group(3))
                for match in ATTR_RE.finditer(attributes)
            }
            if attrs.get("src"):
                continue
            script_type = attrs.get("type", "").casefold().strip()
            if script_type in {
                "application/json",
                "application/ld+json",
                "importmap",
                "speculationrules",
            }:
                continue
            if script_type and script_type not in {
                "application/ecmascript",
                "application/javascript",
                "module",
                "text/ecmascript",
                "text/javascript",
            }:
                continue
            inline_count += 1
            mode = "module" if script_type == "module" else "classic"
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            unique_inline.setdefault(
                (mode, digest), (path.relative_to(ROOT).as_posix(), body)
            )

    for (mode, _), (relative, body) in sorted(unique_inline.items()):
        command = ["node", "--check", "-"]
        if mode == "module":
            command = ["node", "--input-type=module", "--check", "-"]
        error = node_check(command, body)
        if error:
            errors.append(f"{relative}: inline JavaScript syntax: {error}")

    external_count = 0
    for path in sorted(ROOT.rglob("*.js")):
        if ".git" in path.parts:
            continue
        external_count += 1
        error = node_check(["node", "--check", str(path)])
        if error:
            errors.append(f"{path.relative_to(ROOT)}: JavaScript syntax: {error}")

    if errors:
        print(f"BLOCK ({len(errors)} issue(s))")
        for error in errors[:100]:
            print(f"- {error}")
        return 1
    print(
        "PASS: "
        f"{result['required_cells']} exact-50 cells, text sitemap, approved email, "
        f"{inline_count} inline/{external_count} external JavaScript files"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
