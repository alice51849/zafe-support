from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import support_surfaces as surfaces  # noqa: E402


SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
ROUTER_RE = re.compile(r"\bdata-legacy-query-router=[\"']lang[\"']", re.I)
NODE_RUNNER = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(0, "utf8");
const cases = JSON.parse(process.env.ROUTER_CASES);
const results = [];
for (const item of cases) {
  let replaced = null;
  const location = {
    href: item.href,
    replace(value) { replaced = String(value); }
  };
  vm.runInNewContext(
    source,
    {window: {location}, URL, Object},
    {timeout: 1000}
  );
  results.push(replaced);
}
process.stdout.write(JSON.stringify(results));
"""


class SupportSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = surfaces.load_source()
        surfaces.build(cls.data)

    def router_script(self, surface: str) -> str:
        text = (ROOT / surfaces.FILES[surface]).read_text(encoding="utf-8")
        scripts = [
            body
            for attrs, body in SCRIPT_RE.findall(text)
            if ROUTER_RE.search(attrs)
        ]
        self.assertEqual(1, len(scripts), surface)
        return scripts[0]

    def run_router(self, surface: str, hrefs: list[str]) -> list[str | None]:
        env = dict(os.environ)
        env["ROUTER_CASES"] = json.dumps(
            [{"href": href} for href in hrefs],
            ensure_ascii=True,
        )
        result = subprocess.run(
            ["node", "-e", NODE_RUNNER],
            input=self.router_script(surface),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=env,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def generated_snapshot(self) -> dict[str, str]:
        paths = set(surfaces.unique_routes(self.data)) | {"sitemap.txt"}
        return {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in sorted(paths)
        }

    def test_source_keeps_exact_frozen_contracts(self) -> None:
        self.assertEqual(surfaces.OFFICIAL, self.data["official_locales"])
        self.assertEqual(50, len(self.data["official_locales"]))
        self.assertEqual(
            {"parameter": "lang", "surfaces": list(surfaces.SURFACES)},
            self.data["legacy_query"],
        )
        self.assertEqual(["help.html"], self.data["sitemap_extras"])
        self.assertEqual("6787344033", self.data["app_store"]["app_id"])
        self.assertEqual("118326163", self.data["app_store"]["provider_token"])
        self.assertEqual("sup_zafe", self.data["app_store"]["campaign_token"])

    def test_generator_is_idempotent_across_two_runs(self) -> None:
        surfaces.build(self.data)
        first = self.generated_snapshot()
        surfaces.build(self.data)
        self.assertEqual(first, self.generated_snapshot())

    def test_legacy_router_accepts_only_exact_official_locales(self) -> None:
        for surface in surfaces.SURFACES:
            source_url = surfaces.route_url(self.data, "en-US", surface)
            hrefs = [
                (
                    f"{source_url}?keep=a%2Fb&lang={locale}&empty="
                    "&redirect=https%3A%2F%2Fevil.example#kept"
                )
                for locale in surfaces.OFFICIAL
            ]
            results = self.run_router(surface, hrefs)
            for locale, result in zip(surfaces.OFFICIAL, results, strict=True):
                self.assertIsNotNone(result, f"{surface}/{locale}")
                actual = urlsplit(result)
                expected = urlsplit(surfaces.route_url(self.data, locale, surface))
                self.assertEqual(
                    (expected.scheme, expected.netloc, expected.path),
                    (actual.scheme, actual.netloc, actual.path),
                    f"{surface}/{locale}",
                )
                self.assertEqual(
                    [
                        ("keep", "a/b"),
                        ("empty", ""),
                        ("redirect", "https://evil.example"),
                    ],
                    parse_qsl(actual.query, keep_blank_values=True),
                )
                self.assertEqual("kept", actual.fragment)
                self.assertEqual("alice51849.github.io", actual.hostname)

    def test_legacy_router_rejects_case_prototype_path_and_duplicates(self) -> None:
        mutations = [
            "",
            "?Lang=ja",
            "?lang=JA",
            "?lang=en-us",
            "?lang=",
            "?lang=__proto__",
            "?lang=prototype",
            "?lang=constructor",
            "?lang=toString",
            "?lang=%2F%2Fevil.example",
            "?lang=..%2Fja",
            "?lang=ja%2F..",
            "?lang=https%3A%2F%2Fevil.example",
            "?lang=ja&lang=en-US",
        ]
        for surface in surfaces.SURFACES:
            base = surfaces.route_url(self.data, "en-US", surface)
            self.assertEqual(
                [None] * len(mutations),
                self.run_router(surface, [base + item for item in mutations]),
                surface,
            )

    def test_router_is_frozen_and_uses_object_has_own(self) -> None:
        for surface in surfaces.SURFACES:
            script = self.router_script(surface)
            self.assertIn("Object.freeze(", script)
            self.assertIn("Object.create(null)", script)
            self.assertIn("Object.hasOwn(routes, values[0])", script)
            self.assertNotIn("hasOwnProperty", script)

    def test_all_inline_javascript_parses_with_node(self) -> None:
        checked = 0
        for relative in sorted(surfaces.unique_routes(self.data)):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for attrs, body in SCRIPT_RE.findall(text):
                attrs_lower = attrs.casefold()
                if "application/ld+json" in attrs_lower:
                    continue
                result = subprocess.run(
                    ["node", "--check", "-"],
                    input=body,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(0, result.returncode, f"{relative}: {result.stderr}")
                checked += 1
        self.assertEqual(3, checked)

    def test_sitemap_is_unique_exact_and_canonical(self) -> None:
        lines = [
            line
            for line in (ROOT / "sitemap.txt").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(surfaces.sitemap_urls(self.data), lines)
        self.assertEqual(len(lines), len(set(lines)))
        self.assertTrue(all(not urlsplit(url).query for url in lines))
        self.assertTrue(all(not urlsplit(url).fragment for url in lines))

        expected_paths = dict(surfaces.unique_routes(self.data))
        for relative in self.data["sitemap_extras"]:
            expected_paths[relative] = ("en-US", "extra")
        canonical_to_path = {
            surfaces.path_url(self.data["base_url"], relative): relative
            for relative in expected_paths
        }
        self.assertEqual(set(lines), set(canonical_to_path))
        for url, relative in canonical_to_path.items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            canonicals = surfaces.attr_values(
                text, "link", "href", ("rel", "canonical")
            )
            self.assertEqual([url], canonicals, relative)

    def test_zafe_app_store_cta_is_on_index_and_support_surfaces(self) -> None:
        expected = surfaces.campaign_app_store_url(self.data)
        parsed = urlsplit(expected)
        self.assertEqual("apps.apple.com", parsed.hostname)
        self.assertEqual("/app/id6787344033", parsed.path)
        self.assertEqual(
            [("pt", "118326163"), ("ct", "sup_zafe"), ("mt", "8")],
            parse_qsl(parsed.query),
        )
        for relative, (_, surface) in surfaces.unique_routes(self.data).items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            hrefs = [
                html.unescape(href)
                for href in surfaces.attr_values(text, "a", "href")
                if "id6787344033" in href
            ]
            if surface in self.data["app_store"]["surfaces"]:
                self.assertEqual([expected], hrefs, relative)
                self.assertIn("App Store</a>", text, relative)
            else:
                self.assertEqual([], hrefs, relative)

    def test_exact50_hreflang_email_and_native_checker(self) -> None:
        result = surfaces.check(self.data)
        self.assertEqual(150, result["required_cells"])
        self.assertEqual(141, result["unique_files"])
        self.assertEqual("PASS", result["status"])
        for relative in surfaces.unique_routes(self.data):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertEqual(
                51,
                len(re.findall(r"<link\b[^>]*\bhreflang=", text, re.I)),
                relative,
            )
            emails = {
                item.casefold()
                for item in surfaces.EMAIL_RE.findall(text)
            }
            self.assertLessEqual(emails, {"hourstag.app@gmail.com"}, relative)


if __name__ == "__main__":
    unittest.main()
