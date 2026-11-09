# Third-party data and dependencies

## Geographic data

- `orchestrator/data/cities.csv` is identified in the source code as a reduced export of **GeoNames cities15000**. It contains selected name, country, administrative-area, coordinate and population fields. GeoNames data is available under [Creative Commons Attribution 4.0](https://www.geonames.org/about.html). Attribution: GeoNames. The original retrieval date is not recorded in this snapshot.
- `remotion/src/geo/land50.json` is derived from **Natural Earth 1:50m land** data by `orchestrator/tools/make_geo.py`, which simplifies geometry and rounds coordinates. Natural Earth distributes its map data in the [public domain](https://www.naturalearthdata.com/about/terms-of-use/). Made with Natural Earth.

## Rendering assets and software

The film-grain and frame-mask textures in `remotion/src/film/` are generated visual assets; the project includes their generator in `orchestrator/tools/make_film.py`.

Python and JavaScript libraries retain their respective licenses. See `requirements.txt` and `remotion/package-lock.json` for dependency information. Fonts loaded by the rendering components and media obtained through external services remain subject to their own terms.

Production footage, music, generated episode assets and account data are not bundled with the repository.
