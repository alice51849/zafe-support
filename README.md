# zafe-support

## Exact-50 support surfaces

The required `index`, `support`, and `privacy` routes are generated or
normalised from `source/support_surfaces.json`:

```bash
python3 tools/support_surfaces.py build
python3 tools/support_surfaces.py check
```

The source records the verified public catalogue and app/privacy authority
digests used for the copy. Do not hand-edit generated locale pages.
