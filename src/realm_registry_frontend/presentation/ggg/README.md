# The GGG presentation's maps

`static/what-is-this/ggg/index.html` is written by hand, except two drawings made by these scripts.

## The title map

An isometric landscape drawn with the "What is this?" deck's own helpers, so both decks share one style.

```sh
python3 -I iso_map.py ../build.py > map.svgfrag
python3 -I splice_title.py ../../static/what-is-this/ggg/index.html map.svgfrag
```

`splice_title.py` is for the first insertion only: it replaces the earlier flat map. To change the
map later, regenerate `map.svgfrag` and replace the contents of the title slide's
`<div class="art map">` by hand.

## The zoom map: the EU, Spain, the Comunitat Valenciana, València

Download the four datasets into one folder:

| File | Source | Licence |
|---|---|---|
| `countries.geojson` | https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson | Natural Earth, public domain |
| `ccaa.geojson` | https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/georef-spain-comunidad-autonoma/exports/geojson | Instituto Geográfico Nacional, CC BY 4.0 |
| `cv_municipios.geojson` | https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/georef-spain-municipio/exports/geojson?refine=acom_name%3A%22Comunitat%20Valenciana%22 | Instituto Geográfico Nacional, CC BY 4.0 |
| `districtes.geojson` | https://geoportal.valencia.es/server/rest/services/OPENDATA/UrbanismoEInfraestructuras/MapServer/225/query?where=1=1&outFields=*&outSR=4326&f=geojson | Ajuntament de València, CC BY 4.0 |

Then:

```sh
python3 -I zoom_map.py <data folder> .
python3 -I splice_zoom.py ../../static/what-is-this/ggg/index.html .
```

`splice_zoom.py` replaces the slide and its styles each time it runs. The slide credits the three
sources, as the CC BY licences require.
