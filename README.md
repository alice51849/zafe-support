# zafe-support

## Exact-50 support surfaces

The required `index`, `support`, and `privacy` routes are generated or
normalised from `source/support_surfaces.json`:

```bash
python3 tools/support_surfaces.py build
python3 tools/support_surfaces.py check
python3 lint_site.py
```

The source records the verified public catalogue and app/privacy authority
digests used for the copy. Do not hand-edit generated locale pages.
The builder preserves the remote exact-50 query routes in `sitemap.txt` and
appends the generated static canonical routes without restoring retired XML.
