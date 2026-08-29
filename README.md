# zafe-support

## Exact-50 support surfaces

The required `index`, `support`, and `privacy` routes are generated or
normalised from `source/support_surfaces.json`:

```bash
python3 tools/support_surfaces.py build
python3 tools/support_surfaces.py check
python3 -m unittest discover -s tests
python3 lint_site.py
```

The source records the verified public catalogue and app/privacy authority
digests used for the copy. Do not hand-edit generated locale pages.
The builder writes only canonical static URLs to `sitemap.txt` without
restoring retired XML. The three root pages keep a fail-closed legacy
`?lang=` redirect for exact Apple locales while preserving unrelated query
parameters and fragments.
