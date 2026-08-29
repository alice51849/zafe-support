#!/usr/bin/env python3
"""Build and validate one repository's exact-50 public support surfaces."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source" / "support_surfaces.json"
SURFACES = ("index", "support", "privacy")
FILES = {"index": "index.html", "support": "support.html", "privacy": "privacy.html"}
RTL = {"ar-SA", "he", "ur-PK"}
ROOT_ENGLISH = {"en-AU", "en-CA", "en-GB", "en-US"}
OFFICIAL = [
    "ar-SA", "bn-BD", "ca", "zh-Hans", "zh-Hant", "hr", "cs", "da",
    "nl-NL", "en-AU", "en-CA", "en-GB", "en-US", "fi", "fr-CA",
    "fr-FR", "de-DE", "el", "gu-IN", "he", "hi", "hu", "id", "it",
    "ja", "kn-IN", "ko", "ms", "ml-IN", "mr-IN", "no", "or-IN", "pl",
    "pt-BR", "pt-PT", "pa-IN", "ro", "ru", "sk", "sl-SI", "es-MX",
    "es-ES", "sv", "ta-IN", "te-IN", "th", "tr", "uk", "ur-PK", "vi",
]
SCRIPT_RANGES = {
    "ar-SA": r"[\u0600-\u06ff]", "he": r"[\u0590-\u05ff]",
    "ur-PK": r"[\u0600-\u06ff]", "bn-BD": r"[\u0980-\u09ff]",
    "gu-IN": r"[\u0a80-\u0aff]", "hi": r"[\u0900-\u097f]",
    "mr-IN": r"[\u0900-\u097f]", "kn-IN": r"[\u0c80-\u0cff]",
    "ml-IN": r"[\u0d00-\u0d7f]", "or-IN": r"[\u0b00-\u0b7f]",
    "pa-IN": r"[\u0a00-\u0a7f]", "ta-IN": r"[\u0b80-\u0bff]",
    "te-IN": r"[\u0c00-\u0c7f]", "el": r"[\u0370-\u03ff]",
    "ru": r"[\u0400-\u04ff]", "uk": r"[\u0400-\u04ff]",
    "zh-Hans": r"[\u3400-\u9fff]", "zh-Hant": r"[\u3400-\u9fff]",
    "ja": r"[\u3040-\u30ff\u3400-\u9fff]", "ko": r"[\uac00-\ud7af]",
    "th": r"[\u0e00-\u0e7f]",
}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
TAG_RE = re.compile(r"<[^>]+>")
RAW_KEY_RE = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){2,}\b")
LINK_RE = re.compile(
    r"\s*<link\b(?=[^>]*\brel\s*=\s*[\"'](?:canonical|alternate)[\"'])[^>]*>",
    re.I,
)
META_RE = re.compile(
    r"\s*<meta\b(?=[^>]*(?:property|name)\s*=\s*[\"']"
    r"(?:og:url|og:locale|support-surface-authority)[\"'])[^>]*>",
    re.I,
)
SCHEMA_RE = re.compile(
    r"\s*<script\b[^>]*\bid\s*=\s*[\"']support-surface-schema[\"'][^>]*>"
    r".*?</script>",
    re.I | re.S,
)
APP_ID_RE = re.compile(r"[0-9]{1,20}")
PROVIDER_TOKEN_RE = re.compile(r"[0-9]{1,20}")
CAMPAIGN_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{1,30}")


def is_safe_static_relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "%" in value:
        return False
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or parts.query or parts.fragment or value.startswith("/"):
        return False
    pure = PurePosixPath(value)
    return (
        str(pure) == value
        and all(part not in {"", ".", ".."} for part in pure.parts)
        and pure.suffix == ".html"
    )


def load_source() -> dict:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if data.get("schema") != "support-surface-source/v1":
        raise SystemExit("unsupported support surface source schema")
    if data.get("official_locales") != OFFICIAL:
        raise SystemExit("official locale list mismatch")
    if set(data.get("routes", {})) != set(OFFICIAL):
        raise SystemExit("route locale set mismatch")
    for locale in OFFICIAL:
        if set(data["routes"][locale]) != set(SURFACES):
            raise SystemExit(f"{locale}: route surface set mismatch")
        for surface in SURFACES:
            expected = (
                FILES[surface]
                if locale in ROOT_ENGLISH
                else f"{locale}/{FILES[surface]}"
            )
            if data["routes"][locale][surface] != expected:
                raise SystemExit(f"{locale}/{surface}: unsafe or non-canonical route")
    legacy = data.get("legacy_query")
    if not isinstance(legacy, dict):
        raise SystemExit("missing legacy query contract")
    if legacy.get("parameter") != "lang":
        raise SystemExit("legacy query parameter must remain exact-case lang")
    if legacy.get("surfaces") != list(SURFACES):
        raise SystemExit("legacy query surfaces mismatch")
    extras = data.get("sitemap_extras")
    if not isinstance(extras, list) or len(extras) != len(set(extras)):
        raise SystemExit("invalid sitemap extras")
    if any(not is_safe_static_relative(item) for item in extras):
        raise SystemExit("unsafe sitemap extra")
    campaign_app_store_url(data)
    return data


def path_url(base_url: str, relative: str) -> str:
    base = base_url.rstrip("/") + "/"
    if relative == "index.html":
        return base
    if relative.endswith("/index.html"):
        return base + relative[:-10]
    return base + relative


def route_url(data: dict, locale: str, surface: str) -> str:
    return path_url(data["base_url"], data["routes"][locale][surface])


def page_links(data: dict, surface: str) -> str:
    rows = [
        f'<link rel="alternate" hreflang="{locale}" '
        f'href="{html.escape(route_url(data, locale, surface), quote=True)}">'
        for locale in OFFICIAL
    ]
    rows.append(
        f'<link rel="alternate" hreflang="x-default" '
        f'href="{html.escape(route_url(data, "en-US", surface), quote=True)}">'
    )
    return "\n".join(rows)


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def campaign_app_store_url(data: dict) -> str:
    config = data.get("app_store")
    required = {
        "app_id", "direct_url", "provider_token", "campaign_token",
        "media_type", "label", "surfaces",
    }
    if not isinstance(config, dict) or set(config) != required:
        raise SystemExit("invalid App Store campaign contract")
    app_id = config["app_id"]
    provider = config["provider_token"]
    campaign = config["campaign_token"]
    direct = config["direct_url"]
    if not isinstance(app_id, str) or APP_ID_RE.fullmatch(app_id) is None:
        raise SystemExit("invalid App Store app ID")
    if direct != f"https://apps.apple.com/app/id{app_id}":
        raise SystemExit("App Store identity mismatch")
    if (
        not isinstance(provider, str)
        or PROVIDER_TOKEN_RE.fullmatch(provider) is None
        or not isinstance(campaign, str)
        or CAMPAIGN_TOKEN_RE.fullmatch(campaign) is None
        or config["media_type"] != "8"
    ):
        raise SystemExit("invalid App Store campaign identity")
    if (
        not isinstance(config["label"], str)
        or "App Store" not in config["label"]
        or config["surfaces"] != ["index", "support"]
    ):
        raise SystemExit("invalid App Store CTA contract")
    return direct + "?" + urlencode((
        ("pt", provider),
        ("ct", campaign),
        ("mt", config["media_type"]),
    ))


def legacy_query_script(data: dict, target: dict) -> str:
    surface = target["surface"]
    legacy = data["legacy_query"]
    if target["path"] != FILES[surface] or surface not in legacy["surfaces"]:
        return ""
    routes = json.dumps(
        {locale: route_url(data, locale, surface) for locale in OFFICIAL},
        ensure_ascii=True,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    parameter = json.dumps(legacy["parameter"])
    return f"""<script data-legacy-query-router="{esc(legacy["parameter"])}">
(() => {{
  "use strict";
  const routes = Object.freeze(Object.assign(Object.create(null), {routes}));
  const parameter = {parameter};
  const source = new URL(window.location.href);
  const values = source.searchParams.getAll(parameter);
  if (values.length !== 1 || !Object.hasOwn(routes, values[0])) return;
  const target = new URL(routes[values[0]]);
  source.searchParams.delete(parameter);
  target.search = source.searchParams.toString();
  target.hash = source.hash;
  window.location.replace(target.href);
}})();
</script>"""


def render(data: dict, target: dict) -> str:
    locale = target["locale"]
    surface = target["surface"]
    canonical = route_url(data, locale, surface)
    nav = []
    for key, label in zip(SURFACES, target["nav"], strict=True):
        current = ' aria-current="page"' if key == surface else ""
        nav.append(f'<a href="{esc(route_url(data, locale, key))}"{current}>{esc(label)}</a>')
    language_links = "".join(
        f'<a lang="{code}" hreflang="{code}" href="{esc(route_url(data, code, surface))}"'
        f'{" aria-current=\"true\"" if code == locale else ""}>'
        f'{esc(data["language_names"][code])}</a>'
        for code in OFFICIAL
    )
    sections = "".join(
        f'<section class="card"><h2>{esc(item["heading"])}</h2>'
        f'<p>{esc(item["body"])}</p></section>'
        for item in target.get("sections", [])
    )
    faq_items = target.get("faqs", [])
    faqs = ""
    if faq_items:
        faq_rows = "".join(
            f'<details><summary>{esc(question)}</summary><p>{esc(answer)}</p></details>'
            for question, answer in faq_items
        )
        faqs = (
            f'<section class="card wide"><h2>{esc(target["faq_heading"])}</h2>'
            f'{faq_rows}</section>'
        )
    parent_note = (
        f'<aside class="parent-note">{esc(target["parent_note"])}</aside>'
        if target.get("parent_note") else ""
    )
    store = ""
    if surface in data["app_store"]["surfaces"]:
        store_label = data["app_store"]["label"]
        store_accessible_label = f'{target["app_name"]} · {store_label}'
        store = (
            f'<a class="button" data-app-store-id="{esc(data["app_store"]["app_id"])}" '
            f'href="{esc(campaign_app_store_url(data))}" '
            f'aria-label="{esc(store_accessible_label)}" '
            f'rel="noopener">{esc(store_label)}</a>'
        )
    secondary = (
        f'<a class="quiet-button" href="{esc(route_url(data, locale, "support"))}">'
        f'{esc(target["support_label"])}</a>'
        if surface == "index" else ""
    )
    icon = ""
    if data.get("icon_url"):
        icon = f'<img src="{esc(data["icon_url"])}" width="42" height="42" alt="">'
    contact = ""
    if surface in {"support", "privacy"}:
        contact = (
            f'<section class="card wide contact"><h2>{esc(target["contact_heading"])}</h2>'
            f'<p>{esc(target["contact_body"])}</p>'
            f'<a class="button" href="mailto:{esc(data["email"])}">'
            f'{esc(target["contact_button"])}</a>'
            f'<a class="email" href="mailto:{esc(data["email"])}">{esc(data["email"])}</a>'
            f'</section>'
        )
    graph = [{
        "@type": "WebPage",
        "url": canonical,
        "name": target["title"],
        "inLanguage": locale,
        "isPartOf": {"@type": "WebSite", "url": data["base_url"]},
    }]
    if faq_items:
        graph.append({
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_items
            ],
        })
    schema = json.dumps(
        {"@context": "https://schema.org", "@graph": graph},
        ensure_ascii=False, separators=(",", ":"),
    ).replace("</", "<\\/")
    theme = data["theme"]
    legacy_router = legacy_query_script(data, target)
    return f"""<!doctype html>
<html lang="{esc(locale)}" dir="{"rtl" if locale in RTL else "ltr"}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="support-surface-generated" content="support-surface-source/v1">
<meta name="support-surface-authority" content="{esc(data["authority_digest"])}">
<title>{esc(target["title"])}</title>
<meta name="description" content="{esc(target["description"]) }">
<link rel="canonical" href="{esc(canonical)}">
{page_links(data, surface)}
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(target["title"])}">
<meta property="og:description" content="{esc(target["description"])}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:locale" content="{esc(locale.replace("-", "_"))}">
{legacy_router}
<script id="support-surface-schema" type="application/ld+json">{schema}</script>
<style>
:root{{--ink:{theme["ink"]};--muted:{theme["muted"]};--a1:{theme["a1"]};--a2:{theme["a2"]};--line:color-mix(in srgb,var(--a1) 22%,transparent)}}
*{{box-sizing:border-box}}html{{background:{theme["background"]}}}
body{{margin:0;min-height:100vh;color:var(--ink);font:16px/1.62 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans","Noto Sans Arabic","Noto Sans Devanagari","Noto Sans Bengali","Noto Sans Tamil","Noto Sans Telugu","Noto Sans Kannada","Noto Sans Malayalam","Noto Sans Gujarati","Noto Sans Gurmukhi","Noto Sans Thai",sans-serif;background:radial-gradient(circle at 8% 0%,color-mix(in srgb,var(--a1) 16%,transparent),transparent 32rem),radial-gradient(circle at 92% 4%,color-mix(in srgb,var(--a2) 14%,transparent),transparent 30rem)}}
a{{color:var(--a1);text-decoration:none}}a:focus-visible,summary:focus-visible{{outline:3px solid color-mix(in srgb,var(--a1) 45%,transparent);outline-offset:4px}}
.shell{{width:min(1040px,calc(100% - 34px));margin:auto}}header{{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:22px 0;flex-wrap:wrap}}
.brand{{display:flex;align-items:center;gap:11px;color:var(--ink);font-weight:750}}.brand img{{border-radius:12px}}
nav{{display:flex;gap:5px;flex-wrap:wrap}}nav a{{min-height:44px;padding:10px 13px;border-radius:13px;color:var(--muted);font-weight:650}}nav a[aria-current]{{background:color-mix(in srgb,var(--a1) 12%,transparent);color:var(--a1)}}
.language{{position:relative}}.language summary{{min-height:44px;padding:10px 13px;border:1px solid var(--line);border-radius:13px;cursor:pointer;list-style:none}}.language summary::-webkit-details-marker{{display:none}}
.language-list{{position:absolute;z-index:5;inset-inline-end:0;top:52px;width:min(600px,calc(100vw - 24px));max-height:66vh;overflow:auto;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;padding:12px;border:1px solid var(--line);border-radius:18px;background:{theme["panel"]};box-shadow:0 20px 60px color-mix(in srgb,var(--a1) 18%,transparent)}}.language-list a{{padding:8px 10px;border-radius:10px;color:var(--muted)}}.language-list a[aria-current]{{background:color-mix(in srgb,var(--a1) 12%,transparent);color:var(--a1)}}
main{{padding:18px 0 8px}}.hero{{padding:20px 0 30px}}.eyebrow{{margin:0;color:var(--a1);font-size:13px;font-weight:800;letter-spacing:.1em;text-transform:uppercase}}h1{{margin:12px 0 8px;font-size:clamp(31px,6vw,54px);line-height:1.12;font-weight:720;letter-spacing:-.025em}}.lead{{max-width:70ch;margin:0;color:var(--muted);font-size:18px}}
.actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}}.button,.quiet-button{{display:inline-flex;align-items:center;min-height:44px;padding:11px 20px;border-radius:14px;font-weight:720}}.button{{color:white;background:linear-gradient(130deg,var(--a1),var(--a2))}}.quiet-button{{border:1px solid var(--line);color:var(--muted);background:{theme["panel"]}}}
.parent-note{{margin-top:17px;padding:13px 16px;border-inline-start:4px solid var(--a1);border-radius:10px;background:color-mix(in srgb,var(--a1) 9%,transparent);color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:15px}}.card{{padding:21px 23px;border:1px solid var(--line);border-radius:19px;background:{theme["panel"]};box-shadow:0 18px 44px color-mix(in srgb,var(--a1) 10%,transparent)}}.wide{{grid-column:1/-1}}.card h2{{margin:0 0 8px;font-size:20px}}.card p{{margin:0;color:var(--muted)}}details{{padding:13px 0;border-top:1px solid var(--line)}}details:first-of-type{{border-top:0}}summary{{cursor:pointer;font-weight:690}}details p{{margin-top:8px!important}}.contact{{margin-top:15px}}.email{{display:inline-flex;margin:12px;color:var(--muted)}}
footer{{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-top:28px;padding:25px 0 38px;border-top:1px solid var(--line);color:var(--muted);font-size:14px}}
@media(max-width:720px){{.language-list{{position:fixed;inset:76px 12px auto;grid-template-columns:repeat(2,minmax(0,1fr))}}}}
</style>
</head>
<body>
<div class="shell">
<header><a class="brand" href="{esc(route_url(data, locale, "index"))}">{icon}<span>{esc(target["app_name"])}</span></a><nav aria-label="{esc(target["nav_label"])}">{''.join(nav)}</nav><details class="language"><summary>{esc(target["language_label"])}</summary><div class="language-list">{language_links}</div></details></header>
<main>
<section class="hero"><p class="eyebrow">{esc(target["eyebrow"])}</p><h1>{esc(target["heading"])}</h1><p class="lead">{esc(target["lead"])}</p>{parent_note}<div class="actions">{store}{secondary}</div></section>
<div class="grid">{sections}{faqs}{contact}</div>
</main>
<footer><span>© 2026 {esc(target["app_name"])}</span><span>{esc(target["footer_note"])}</span></footer>
</div>
</body>
</html>
"""


def set_html_identity(text: str, locale: str) -> str:
    match = re.search(r"<html\b([^>]*)>", text, re.I)
    if not match:
        raise ValueError("missing html element")
    attrs = match.group(1)
    attrs = re.sub(r"\s+(?:lang|dir)\s*=\s*[\"'][^\"']*[\"']", "", attrs, flags=re.I)
    replacement = f'<html{attrs} lang="{locale}" dir="{"rtl" if locale in RTL else "ltr"}">'
    return text[:match.start()] + replacement + text[match.end():]


def normalize_page(data: dict, relative: str, locale: str, surface: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    text = set_html_identity(text, locale)
    canonical = path_url(data["base_url"], relative)
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    page_name = TAG_RE.sub(" ", title.group(1)).strip() if title else data["site"]
    schema = json.dumps({
        "@context": "https://schema.org", "@type": "WebPage", "url": canonical,
        "name": html.unescape(page_name), "inLanguage": locale,
    }, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    block = (
        f'\n<meta name="support-surface-authority" content="{esc(data["authority_digest"])}">'
        f'\n<link rel="canonical" href="{esc(canonical)}">\n{page_links(data, surface)}'
        f'\n<meta property="og:url" content="{esc(canonical)}">'
        f'\n<meta property="og:locale" content="{esc(locale.replace("-", "_"))}">'
        f'\n<script id="support-surface-schema" type="application/ld+json">{schema}</script>\n'
    )
    text = re.sub(r"<!--\s*ls-i18n:(?:start|end)\s*-->", "", text, flags=re.I)
    text = LINK_RE.sub("", text)
    text = META_RE.sub("", text)
    text = SCHEMA_RE.sub("", text)
    if "</head>" not in text.lower():
        raise ValueError(f"{relative}: missing head close")
    text = re.sub(r"</head>", block + "</head>", text, count=1, flags=re.I)
    path.write_text(text, encoding="utf-8")


def unique_routes(data: dict) -> dict[str, tuple[str, str]]:
    users: dict[str, list[tuple[str, str]]] = {}
    for locale in OFFICIAL:
        for surface in SURFACES:
            users.setdefault(data["routes"][locale][surface], []).append((locale, surface))
    result = {}
    for path, values in users.items():
        locales = [item[0] for item in values]
        locale = "en-US" if "en-US" in locales else values[0][0]
        result[path] = (locale, values[0][1])
    return result


def sitemap_relatives(data: dict) -> list[str]:
    return sorted({*unique_routes(data), *data["sitemap_extras"]})


def sitemap_urls(data: dict) -> list[str]:
    return sorted(
        path_url(data["base_url"], relative)
        for relative in sitemap_relatives(data)
    )


def write_sitemap(data: dict) -> None:
    for relative in data["sitemap_extras"]:
        if not (ROOT / relative).is_file():
            raise SystemExit(f"missing sitemap extra: {relative}")
    (ROOT / "sitemap.txt").write_text(
        "\n".join(sitemap_urls(data)) + "\n",
        encoding="utf-8",
    )


def build(data: dict) -> str:
    for target in data.get("targets", []):
        destination = ROOT / target["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render(data, target), encoding="utf-8")
    for relative, (locale, surface) in unique_routes(data).items():
        path = ROOT / relative
        if not path.is_file():
            raise SystemExit(f"missing required output: {relative}")
        normalize_page(data, relative, locale, surface)
    write_sitemap(data)
    return content_digest(data)


def visible_text(text: str) -> str:
    text = re.sub(r"<(?:script|style)\b.*?</(?:script|style)>", " ", text, flags=re.I | re.S)
    return " ".join(html.unescape(TAG_RE.sub(" ", text)).split())


def attr_values(text: str, tag: str, attr: str, required: tuple[str, str] | None = None) -> list[str]:
    out = []
    for match in re.finditer(fr"<{tag}\b([^>]*)>", text, re.I):
        attrs = match.group(1)
        if required:
            req = re.search(fr"\b{required[0]}\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
            if not req or req.group(1).lower() != required[1].lower():
                continue
        value = re.search(fr"\b{attr}\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
        if value:
            out.append(html.unescape(value.group(1)))
    return out


def resolve_local(data: dict, current: str, href: str) -> Path | None:
    if not href or href.startswith(("#", "mailto:", "tel:")):
        return None
    parts = urlsplit(href)
    if parts.scheme:
        base = urlsplit(data["base_url"])
        if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
            return None
        prefix = base.path.rstrip("/") + "/"
        if not parts.path.startswith(prefix):
            return None
        rel = unquote(parts.path[len(prefix):])
    elif href.startswith("/"):
        prefix = urlsplit(data["base_url"]).path.rstrip("/") + "/"
        if not href.startswith(prefix):
            return None
        rel = unquote(href[len(prefix):].split("?", 1)[0].split("#", 1)[0])
    else:
        rel = str((Path(current).parent / unquote(parts.path)).as_posix())
    candidate = ROOT / rel
    if not candidate.suffix:
        candidate = candidate / "index.html"
    return candidate


def check(data: dict) -> dict:
    errors = []
    allowed_email = data["email"].lower()
    route_set = unique_routes(data)
    target_paths = {target["path"]: target for target in data.get("targets", [])}
    expected_hreflang = set(OFFICIAL) | {"x-default"}
    for relative, (locale, surface) in route_set.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{relative}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        html_lang = attr_values(text, "html", "lang")
        html_dir = attr_values(text, "html", "dir")
        if html_lang != [locale]:
            errors.append(f"{relative}: html lang {html_lang!r} != {locale}")
        expected_dir = "rtl" if locale in RTL else "ltr"
        if html_dir != [expected_dir]:
            errors.append(f"{relative}: html dir {html_dir!r} != {expected_dir}")
        canonicals = attr_values(text, "link", "href", ("rel", "canonical"))
        expected_canonical = path_url(data["base_url"], relative)
        if canonicals != [expected_canonical]:
            errors.append(f"{relative}: canonical mismatch")
        alternates = {}
        for match in re.finditer(r"<link\b([^>]*)>", text, re.I):
            attrs = match.group(1)
            rel = re.search(r"\brel\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
            if not rel or rel.group(1).lower() != "alternate":
                continue
            lang = re.search(r"\bhreflang\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
            href = re.search(r"\bhref\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
            if lang and href:
                alternates[lang.group(1)] = html.unescape(href.group(1))
        if set(alternates) != expected_hreflang:
            errors.append(f"{relative}: hreflang set mismatch")
        else:
            for code in OFFICIAL:
                if alternates[code] != route_url(data, code, surface):
                    errors.append(f"{relative}: hreflang {code} URL mismatch")
                    break
        schema_match = re.search(
            r'<script\b[^>]*id=["\']support-surface-schema["\'][^>]*>(.*?)</script>',
            text, re.I | re.S,
        )
        try:
            if not schema_match:
                raise ValueError("missing")
            json.loads(schema_match.group(1))
        except (ValueError, json.JSONDecodeError):
            errors.append(f"{relative}: invalid support schema")
        authority = attr_values(text, "meta", "content", ("name", "support-surface-authority"))
        if authority != [data["authority_digest"]]:
            errors.append(f"{relative}: authority digest mismatch")
        emails = {item.lower() for item in EMAIL_RE.findall(text)}
        if emails - {allowed_email}:
            errors.append(f"{relative}: unapproved public email")
        plain = visible_text(text)
        if surface == "support":
            if len(plain) < 80 or allowed_email not in plain.lower():
                errors.append(f"{relative}: support equivalence gate failed")
        if surface == "privacy" and len(re.findall(r"<h[23]\b", text, re.I)) < 4:
            errors.append(f"{relative}: privacy content too thin")
        for href in attr_values(text, "a", "href"):
            if href.lower().startswith("mailto:") and allowed_email not in href.lower():
                errors.append(f"{relative}: wrong mailto")
                continue
            local = resolve_local(data, relative, href)
            if local is not None and not local.is_file():
                errors.append(f"{relative}: broken local link {href}")
        target = target_paths.get(relative)
        if target:
            if 'name="support-surface-generated"' not in text:
                errors.append(f"{relative}: generated marker missing")
            if RAW_KEY_RE.search(plain) or "{{" in plain or "}}" in plain:
                errors.append(f"{relative}: raw key or placeholder visible")
            if locale not in {"en-US", "en-AU", "en-CA", "en-GB"}:
                pattern = SCRIPT_RANGES.get(locale)
                if pattern and not re.search(pattern, plain):
                    errors.append(f"{relative}: expected script is absent")
        expected_store = (
            campaign_app_store_url(data)
            if surface in data["app_store"]["surfaces"]
            else None
        )
        store_links = [
            href for href in attr_values(text, "a", "href")
            if data["app_store"]["app_id"] in href
        ]
        if expected_store and store_links != [expected_store]:
            errors.append(f"{relative}: Zafe App Store CTA mismatch")
        if not expected_store and store_links:
            errors.append(f"{relative}: unexpected Zafe App Store CTA")
        router_count = len(re.findall(
            r"<script\b[^>]*\bdata-legacy-query-router=[\"']lang[\"']",
            text,
            re.I,
        ))
        expected_router_count = int(relative == FILES[surface])
        if router_count != expected_router_count:
            errors.append(f"{relative}: legacy query router count mismatch")
    sitemap_path = ROOT / "sitemap.txt"
    actual_sitemap_urls = (
        [
            line.strip()
            for line in sitemap_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if sitemap_path.is_file()
        else []
    )
    expected_sitemap_urls = sitemap_urls(data)
    if actual_sitemap_urls != expected_sitemap_urls:
        errors.append("sitemap.txt is not the exact canonical static URL set")
    if len(actual_sitemap_urls) != len(set(actual_sitemap_urls)):
        errors.append("sitemap.txt contains duplicate URLs")
    if any(
        urlsplit(url).query or urlsplit(url).fragment
        for url in actual_sitemap_urls
    ):
        errors.append("sitemap.txt contains query or fragment URLs")
    for relative in data["sitemap_extras"]:
        extra = ROOT / relative
        if not extra.is_file():
            errors.append(f"{relative}: missing sitemap extra")
            continue
        text = extra.read_text(encoding="utf-8")
        expected = path_url(data["base_url"], relative)
        if attr_values(text, "link", "href", ("rel", "canonical")) != [expected]:
            errors.append(f"{relative}: sitemap extra canonical mismatch")
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    expected_sitemap = data["base_url"].rstrip("/") + "/sitemap.txt"
    if f"Sitemap: {expected_sitemap}" not in robots:
        errors.append("robots.txt does not retain the remote text sitemap")
    if (ROOT / "sitemap.xml").exists():
        errors.append("retired sitemap.xml was reintroduced")
    if errors:
        raise SystemExit("\n".join(errors[:100]))
    return {
        "site": data["site"],
        "required_cells": len(OFFICIAL) * len(SURFACES),
        "unique_files": len(route_set),
        "targets": len(data.get("targets", [])),
        "digest": content_digest(data),
        "status": "PASS",
    }


def content_digest(data: dict) -> str:
    digest = hashlib.sha256()
    for relative in sorted(unique_routes(data)):
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((ROOT / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "check", "digest"))
    args = parser.parse_args()
    data = load_source()
    if args.command == "build":
        print(json.dumps({"site": data["site"], "digest": build(data)}, sort_keys=True))
    elif args.command == "check":
        print(json.dumps(check(data), sort_keys=True))
    else:
        print(content_digest(data))


if __name__ == "__main__":
    main()
