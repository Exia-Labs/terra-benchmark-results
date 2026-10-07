"""Original-data overlay questions; no numerical answer is precomputed for Terra."""

OVERLAY_TASKS = {
    "345106": {
        "question": "Generate a heatmap of USA population density and overlay it with current wildfire locations.",
        "raster": "us_population", "vector": "fires", "deriveDensity": True,
        "filter": {"IncidentTy": ["WF"]},
    },
    "281727": {
        "question": "Map the distribution of railway networks in relation to population density in Bangladesh.",
        "raster": "bangladesh_density",
        "vector": "bangladesh_railways",
    },
}


def overlay_protocols():
    result = {
        task: {
            "title": spec["question"],
            "question": spec["question"],
            "family": "source-overlay",
            "bbox": [88, 20, 93, 27],
            "clarification": "Use the supplied WorldPop 2018 Bangladesh density raster in people/km² and the frozen OpenStreetMap railway lines. "
            "Keep the original raster values, band, grid and missing-data mask, and all original railway geometries and identifiers. "
            "Show density as a continuous quantitative raster together with a distinguishable railway line layer on the same map. "
            "Do not treat density as population counts, infer stations or service access, or substitute newer observations. "
            "Disclose the 2018 population / 2025 railway snapshot mismatch and that visual association does not establish causation. "
            "No proximity threshold, population total or new modeled density surface is requested.",
            "outputContract": "Deliver the two map layers and retain inspectable source or unchanged-result identities. End with one fenced JSON: "
            "{count: number of railway features displayed, unknown_count: masked or nonfinite density cells, coverage_note: string, "
            "selection:{collectionId,itemId,assetKey} for density, map_layer_id: density layer ID, "
            "overlay:{selection:{collectionId,itemId,assetKey},map_layer_id: railway layer ID}}. "
            "Explain what the overlay shows and its historical/coverage limits. A source layer can be used directly; no needless calculation is required.",
        }
        for task, spec in OVERLAY_TASKS.items()
    }
    result["345106"].update(bbox=[-180, 18, 180, 72], clarification=(
        "Use the full original USA WorldPop 2020 count raster, band 1, and archived NIFC incident snapshot with latest ModifiedOn 2024-02-27. "
        "Active wildfires means supplied feed records with IncidentTy=WF, excluding prescribed burns RX; this is historical, not today's fire status. "
        "Convert nonnegative people-per-cell counts to people/km² by each original cell's full WGS84 ellipsoidal meridian/parallel surface area. "
        "Apply original scale/offset, keep native grid and missing/nonfinite mask, and genuine zeros. Do not approximate every cell as 1 km². "
        "Heatmap here means a continuous quantitative density raster, not a new smoothing kernel over population. "
        "Overlay every original selected wildfire point, retaining geometry and IDs; do not claim contemporaneous exposure or affected population from 2020 population and 2024 incidents. "
        "Use all supplied raster coverage including Alaska/Hawaii/islands; no mainland-only crop or resampling. "
        "Add density and fire layers to the same map. End with the stated JSON contract: count is wildfire features displayed, unknown_count is original masked/nonfinite raster cells."))
    return result
