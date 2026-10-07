"""Format-only preparation. Reference calculations live in oracles.py, never metadata."""
from __future__ import annotations

import io
import shutil
import struct
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pandas.testing import assert_frame_equal

from .bivariate_tasks import BIVARIATE_TASKS
from .change_tasks import CHANGE_TASKS
from .common import PIN, TASK_IDS, Blocked, digest, read, sha, write
from .contour_tasks import CONTOUR_TASKS, contour_assets
from .control_tasks import CONTROL_TASKS
from .county_tasks import COUNTY_HEAT_TASKS, COUNTY_TASKS
from .flood_tasks import FLOOD_TASKS
from .flood_tasks import assets as flood_assets
from .heat_tasks import HEAT_TASKS
from .map_tasks import MAP_TASKS, map_assets
from .overlay_tasks import OVERLAY_TASKS
from .population_tasks import POPULATION_TASKS, population_assets
from .proximity_tasks import PROXIMITY_TASKS
from .regional_tasks import assets_for
from .series_tasks import SERIES_TASKS
from .water_tasks import WATER_SELECTIONS
from .water_tasks import assets as water_assets

ROW_ID = "benchmark_row_id"
ASSETS = {
    "africa_railways": {"file": "Africa railways.shp", "kind": "vector", "title": "African railways, USGS 2021 compiled network", "edition": "Original frozen GeoBenchX USGS 2021 compilation, not current routing data"},
    "na_railways": {"file": "North_American_Rail_Network_Lines.shp", "kind": "vector", "title": "North American Rail Network Lines, frozen GeoBenchX snapshot", "edition": "Original pinned GeoBenchX NARN/FRA/BTS snapshot, not a live network"},
    "tb_ny": {"file": "NYS TB cases 2023.csv", "kind": "table", "format": "csv", "textFields": ["County"], "nullTokens": ["---"],
              "title": "New York county tuberculosis cases and rates, 2019–2023", "edition": "NYSDOH 2024 report, frozen GeoBenchX transcription; use 2023 counts",
              "units": {"2023 cases": "cases", "2023 cases per 100 000": "cases per 100,000 people"}},
    "tb_ma": {"file": "Incidence of Tuberculosis Disease 2023 Massachusetts Counties.csv", "kind": "table", "format": "csv",
              "title": "Massachusetts county tuberculosis cases and published rates, 2023", "edition": "Massachusetts DPH 2023 summary, frozen GeoBenchX transcription",
              "textFields": ["County"], "units": {"Number of Cases": "cases", "TB Case Rate[1] 2023(cases per 100,000)": "cases per 100,000 people"}},
    "co2": {"file": "per-capita-co-emissions_OWID_tons.csv", "kind": "table", "format": "csv", "textFields": ["Country name"],
            "title": "CO2 emissions per capita, OWID frozen historical table", "edition": "Frozen GeoBenchX OWID snapshot; no current data replacement",
            "units": {"1990": "tonnes CO2 per person", "2020": "tonnes CO2 per person"}},
    "ghg": {"file": "GHG_emissions_OWID_wide.csv", "kind": "table", "format": "csv", "textFields": ["Country Name"],
            "title": "Greenhouse gas emissions per capita, OWID frozen historical table", "edition": "Frozen GeoBenchX OWID snapshot; CO2-equivalent emissions including land use",
            "units": {"1990": "tonnes CO2e per person", "2020": "tonnes CO2e per person"}},
    "towns": {"file": "bx729wr3020.shp", "kind": "vector", "title": "US cities and towns, 2014",
              "edition": "2014; pop_2010 is 2010 population", "units": {"pop_2010": "people"}},
    "snow": {"file": "sfav2_CONUS_2024093012_to_2025052012_processed.tif", "kind": "raster",
             "title": "US snowfall, 2024–25 frozen season", "edition": "2024-09-30 to 2025-05-20",
             "units": {"band1": "inches"}},
    "facilities": {"file": "Africa mineral facilities.shp", "kind": "vector",
                   "title": "African mineral extraction facilities", "edition": "USGS 2021 benchmark snapshot"},
    "countries": {"file": "WB_countries_Admin0_10m.shp", "kind": "vector",
                  "title": "World Bank country boundaries", "edition": "GeoBenchX harmonized names"},
    "migration": {"file": "API_SM.POP.NETM_DS2_en_csv_v2_91.zip", "kind": "table",
                  "title": "Net migration, World Development Indicators", "edition": "2024-11-13 snapshot; use 2023",
                  "units": {"2023": "people (net migration)"}},
    "density": {"file": "dza_pd_2020_1km_UNadj.tif", "kind": "raster",
                "title": "Algeria population density, WorldPop 2020", "edition": "2020 UN-adjusted; 1 km grid",
                "units": {"band1": "people/km²"}},
    "counties": {"file": "tl_2024_us_county.shp", "kind": "vector", "title": "US county boundaries",
                 "edition": "Census TIGER/Line 2024"},
    "earthquakes": {"file": "earthquakes_30_days_Feb142025.shp", "kind": "vector",
                    "title": "Earthquake points, frozen 30-day snapshot",
                    "edition": "Archive labelled Feb142025; observed event timestamps 2025-01-16 through 2025-02-15 UTC"},
    "stations": {"file": "Amtrak_Stations.shp", "kind": "vector", "title": "Amtrak railway stations",
                 "edition": "USDOT BTS frozen GeoBenchX 2025 snapshot"},
    "power_stations": {"file": "Africa Power Stations.shp", "kind": "vector",
                       "title": "African power stations", "edition": "USGS 2021 frozen compilation",
                       "units": {"DsgAttr02": "MW"}},
    "seaports": {"file":"Ports_Latin_America.shp","kind":"vector","title":"Latin American mineral-exporting seaports","edition":"USGS OFR 2017-1079 frozen benchmark compilation"},
    "states": {"file":"tl_2024_us_state.shp","kind":"vector","title":"US state boundaries","edition":"Census TIGER/Line 2024"},
    "fires": {"file":"Incidents.shp","kind":"vector","title":"Frozen US fire incident locations and recorded sizes","edition":"Frozen GeoBenchX archive; not a current active-fire feed","units":{"IncidentSi":"acres"}},
    "water_withdrawal": {"file": "API_ER.H2O.FWTL.ZS_DS2_en_csv_v2_7098.zip", "kind": "table",
                         "title": "Freshwater withdrawals as percent of internal resources",
                         "edition": "Frozen World Development Indicators; use 2021",
                         "units": {"2021": "percent of internal freshwater resources"}},
    "electricity": {"file": "API_EG.USE.ELEC.KH.PC_DS2_en_csv_v2_2767.zip", "kind": "table",
                    "title": "Electric power consumption per capita", "edition": "Frozen WDI; use 2014",
                    "units": {"2014": "kWh per capita"}},
    "gdp": {"file": "API_NY.GDP.PCAP.CD_DS2_en_csv_v2_77536.zip", "kind": "table",
            "title": "GDP per capita", "edition": "Frozen WDI; current US dollars by year",
            "units": {"2020": "current USD per capita", "2022": "current USD per capita"}},
    "fertility": {"file": "API_SP.DYN.TFRT.IN_DS2_en_csv_v2_821.zip", "kind": "table",
                  "title": "Fertility rate", "edition": "Frozen WDI; use 2022",
                  "units": {"2022": "births per woman"}},
}
TASK_ASSETS = {"333321": ("towns", "snow"), "130168": ("facilities", "countries", "migration"),
               "332083": ("facilities", "density"), "417961": ("counties", "earthquakes", "stations")}
TASK_ASSETS.update({"883928": ("stations", "snow"),
    "806525": ("countries", "power_stations", "water_withdrawal"),
    "429627": ("countries", "power_stations", "electricity"),
    "918547": ("countries", "earthquakes", "gdp"), "977524": ("countries", "fertility")})
TASK_BASE = {"333321": "towns", "130168": "facilities", "332083": "facilities", "417961": "stations"}
TASK_ASSETS["955741"] = ("counties", "earthquakes", "fires")
TASK_BASE["955741"] = "counties"
TASK_ASSETS['310610'] = ('na_railways', 'snow')
TASK_BASE['310610'] = 'na_railways'
TASK_ASSETS['586288'] = ('us_population', 'fires')
ASSETS["sa_rivers"] = {"file": "rivers_samerica_37330.shp", "kind": "vector", "title": "FAO AQUAmaps South American river segments", "edition": "Frozen regional HydroSHEDS-derived rivers_samerica_37330; internal research only, no promotional sharing"}
TASK_ASSETS["365343"] = ("sa_rivers", "countries", "forest_percent")
TASK_BASE["365343"] = "sa_rivers"
TASK_BASE.update({"883928": "stations", "806525": "countries", "429627": "countries",
                  "918547": "countries", "977524": "countries"})
for _key, _spec in map_assets().items():
    ASSETS[_key] = {**_spec, **ASSETS.get(_key, {}), "units": {**_spec["units"], **ASSETS.get(_key, {}).get("units", {})}}
for _task, (_indicator, _) in MAP_TASKS.items():
    TASK_ASSETS[_task] = assets_for(_task, _indicator)
    TASK_BASE[_task] = "countries"
ASSETS.update(contour_assets())
ASSETS.update(water_assets())
ASSETS.update(flood_assets())
TASK_ASSETS.update({task: (s["population"], s["flood"]) for task, s in FLOOD_TASKS.items()})
TASK_ASSETS.update(WATER_SELECTIONS)
TASK_ASSETS["150069"] = ("na_lakes", "snow")
TASK_BASE["150069"] = "na_lakes"
TASK_BASE.update({task: keys[0] for task, keys in WATER_SELECTIONS.items()})
ASSETS['peru_provinces'] = {'file':'per_admbnda_adm2_ign_20200714.shp', 'kind':'vector',
                          'title':'Peru province boundaries (ADM2)', 'edition':'IGN / OCHA COD-AB frozen 2020-07-14 release, 196 provinces'}
ASSETS.update(population_assets())
for _task, _spec in PROXIMITY_TASKS.items():
    TASK_ASSETS[_task] = (_spec['base'], _spec['lines'])
    TASK_BASE[_task] = _spec['base']
TASK_ASSETS.update({task:() for task in CONTROL_TASKS})
for _task, _spec in OVERLAY_TASKS.items():
    TASK_ASSETS[_task] = (_spec['raster'], _spec['vector'])
for _task, _spec in POPULATION_TASKS.items():
    TASK_ASSETS[_task] = (_spec['raster'],) + ((_spec['points'],) if _spec.get('points') else ())
for _task, _spec in CONTOUR_TASKS.items():
    TASK_ASSETS[_task] = (_spec["raster"],) + ((_spec["overlay"],) if _spec.get("overlay") else ())
    if _spec.get("floodMask"):
        TASK_ASSETS[_task] += (_spec["floodMask"],)
    if _spec.get('overlaySelector'):
        TASK_ASSETS[_task] += (_spec['overlaySelector']['geography'],)
    TASK_ASSETS[_task] = tuple(dict.fromkeys((*TASK_ASSETS[_task], *_spec.get('contexts', []))))
for _task, _spec in BIVARIATE_TASKS.items():
    TASK_ASSETS[_task] = tuple(_spec["assets"])
    TASK_BASE[_task] = "countries"
for _task, _spec in CHANGE_TASKS.items():
    TASK_ASSETS[_task] = tuple(_spec["assets"])
    TASK_BASE[_task] = _spec["base"]
for _task, _spec in HEAT_TASKS.items():
    TASK_ASSETS[_task] = tuple(_spec["assets"])
    TASK_BASE[_task] = _spec["base"]
for _task,_spec in SERIES_TASKS.items():
    TASK_ASSETS[_task]=tuple(_spec['assets'])
    TASK_BASE[_task]='countries'
for _task,_spec in COUNTY_TASKS.items():
    TASK_ASSETS[_task]=tuple(_spec['assets'])
    TASK_BASE[_task]='counties'
for _task,_spec in COUNTY_HEAT_TASKS.items():
    TASK_ASSETS[_task]=tuple(_spec['assets'])
    TASK_BASE[_task]='counties'
TASK_ASSETS['419069'] = ('counties', 'tb_ma', 'tb_ny', 'us_population')
TASK_BASE['419069'] = 'counties'
TASK_ASSETS['321268'] = ('us_population', 'snow_previous')
TASK_BASE['321268'] = 'us_population'


def point_measures(path):
    """Retain optional PointZ M ordinates as a source attribute; GDAL otherwise drops them."""
    with Path(path).open("rb") as stream:
        header = stream.read(100)
        shape_type = struct.unpack_from("<i", header, 32)[0]
        if shape_type != 11:
            return None
        measures = []
        while record := stream.read(8):
            length = struct.unpack(">ii", record)[1] * 2
            body = stream.read(length)
            m = None
            if len(body) >= 36 and struct.unpack_from("<i", body)[0] == 11:
                m = struct.unpack_from("<d", body, 28)[0]
                if not np.isfinite(m) or m < -1e38:
                    m = None
            measures.append(m)
        return measures


def vector_convert(source, destination, key):
    measures = point_measures(source)
    original = gpd.read_file(source)
    if measures is not None and any(v is not None for v in measures):
        if len(measures) != len(original) or "source_measure_m" in original:
            raise Blocked("Cannot preserve original point measures without a field conflict.")
        original["source_measure_m"] = measures
    if original.crs is None or ROW_ID in original:
        raise Blocked("Fixture lacks CRS or conflicts with the reserved row-identity column.")
    frame = original.copy()
    frame[ROW_ID] = [f"{key}:{i:06d}" for i in range(len(frame))]
    frame.to_parquet(destination, index=False)
    restored = gpd.read_parquet(destination)
    assert_frame_equal(original.drop(columns="geometry"), restored.drop(columns=["geometry", ROW_ID]))
    if original.crs != restored.crs or not np.array_equal(original.geometry.to_wkb(), restored.geometry.to_wkb()):
        raise Blocked("Vector conversion changed geometries or CRS.")
    return frame


def table_convert(source, destination, spec=None):
    if spec and spec.get("format") == "csv":
        frame = pd.read_csv(source, dtype={field: str for field in spec.get("textFields", [])},
                            na_values=spec.get("nullTokens", []), encoding="utf-8-sig")
        frame = frame.drop(columns=[c for c in frame if c.startswith("Unnamed:") and frame[c].isna().all()])
        frame.to_parquet(destination, index=False)
        assert_frame_equal(frame, pd.read_parquet(destination))
        return frame
    with zipfile.ZipFile(source) as archive:
        names = [n for n in archive.namelist() if Path(n).name.startswith("API_") and n.endswith(".csv")]
        if len(names) != 1:
            raise Blocked("World Bank archive has no unique data CSV.")
        frame = pd.read_csv(io.BytesIO(archive.read(names[0])), skiprows=4,
                            dtype={"Country Name": str, "Country Code": str,
                                   "Indicator Name": str, "Indicator Code": str})
    # CSV's trailing unnamed empty column is serialization, not data.
    frame = frame.drop(columns=[c for c in frame if c.startswith("Unnamed:") and frame[c].isna().all()])
    if frame["Country Code"].duplicated().any() or frame["Country Name"].duplicated().any():
        raise Blocked("World Bank country keys are not unique.")
    frame.to_parquet(destination, index=False)
    assert_frame_equal(frame, pd.read_parquet(destination))
    return frame


def prepare_files(directory, task_ids=TASK_IDS):
    directory = Path(directory)
    download = read(directory / "download.json")
    if download["revision"] != PIN:
        raise Blocked("Wrong benchmark source revision.")
    for member in download["members"]:
        if sha(directory / member["path"]) != member["sha256"]:
            raise Blocked("Downloaded fixture changed since retrieval.")
    output = directory / "prepared"
    output.mkdir(exist_ok=True)
    entries = {}
    selected_assets = dict.fromkeys(key for task in task_ids for key in TASK_ASSETS[task])
    for key in selected_assets:
        spec = ASSETS[key]
        paths = list((directory / "raw").rglob(spec["file"]))
        if len(paths) != 1:
            raise Blocked(f"Missing or ambiguous fixture: {spec['file']}")
        source = paths[0]
        dest = output / (key + (".tif" if spec["kind"] == "raster" else ".parquet"))
        metadata = {**spec, "sourceSha256": sha(source)}
        if spec["kind"] == "vector":
            frame = vector_convert(source, dest, key)
        elif spec["kind"] == "table":
            frame = table_convert(source, dest, spec)
        else:
            shutil.copyfile(source, dest)
            with rasterio.open(dest) as raster:
                metadata.update(crs=str(raster.crs), bounds=list(raster.bounds), shape=list(raster.shape),
                                nodata=raster.nodata, transform=list(raster.transform), bandCount=raster.count)
            if sha(source) != sha(dest):
                raise Blocked("Raster bytes changed during copying.")
        if spec["kind"] != "raster":
            metadata.update(rowCount=len(frame), fields=[{"name": c, "dtype": str(frame[c].dtype)}
                                                        for c in frame.columns if c != "geometry"])
            if spec["kind"] == "vector":
                metadata.update(crs=str(frame.crs), bounds=frame.to_crs(4326).total_bounds.tolist(),
                                geometryTypes=sorted(set(frame.geom_type.dropna())),
                                missingGeometryCount=int(frame.geometry.isna().sum()), identity=ROW_ID)
        entries[key] = {**metadata, "path": str(dest.relative_to(directory)), "sha256": sha(dest),
                        "bytes": dest.stat().st_size}
    manifest = {"protocolVersion": 1, "benchmarkRevision": PIN, "assets": entries,
                "tasks": {i: {"assets": TASK_ASSETS[i]} for i in task_ids},
                "identityPolicy": "Count original source rows; preserve original fields and add a stable row key. "
                                  "Repeated GNIS/FeatureUID values do not imply duplicate source rows.",
                "conversionPolicy": "Format only. XYZ retained; meaningful optional M ordinates retained "
                                    "in source_measure_m because the geometry reader drops M."}
    manifest["fingerprint"] = digest(manifest)
    write(directory / "fixtures.json", manifest)
    return manifest


def validate_files(directory):
    directory = Path(directory)
    fixtures = read(directory / "fixtures.json")
    actual = {k: v for k, v in fixtures.items() if k != "fingerprint"}
    if digest(actual) != fixtures["fingerprint"]:
        raise Blocked("Fixture manifest fingerprint differs.")
    for spec in fixtures["assets"].values():
        if sha(directory / spec["path"]) != spec["sha256"]:
            raise Blocked("Prepared input checksum differs.")
    return fixtures


def frame_metadata(frame):
    metadata = {"table:columns": [{"name": c, "type": "number" if pd.api.types.is_numeric_dtype(frame[c])
                                   else "string"} for c in frame if c != "geometry"], "table:row_count": len(frame)}
    # Fixture provisioning already reads the exact immutable file. Publish that
    # observed count so ordinary vector display need not run a preparation job
    # merely to rediscover it. A tabular row count is not a feature count.
    if isinstance(frame, gpd.GeoDataFrame):
        metadata["blue:feature_count"] = len(frame)
    return metadata
