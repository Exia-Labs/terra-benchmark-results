"""Separate qualitative controls, never counted as computed GIS passes."""

from .common import ROOT, read

# Questions come verbatim from pinned original-tasks.json at submission. These
# private rubric facts must never be concatenated into the evaluated prompt.
CONTROL_TASKS = {
    "123067": ("absence", "The metadata-only inventory does not provide measured railway density and population density for defined comparable Brazilian regions; a numerical correlation requires those observations and a regional unit, not invented values."),
    "244529": ("absence", "The inventory does not establish matched local economic activity, population density and flood-prone-area observations in Peru. National economic totals or a single flood footprint do not establish that relationship."),
    "245463": ("absence", "The metadata-only inventory does not establish a measured national population-density distribution for defined Brazilian regions and their railway intersections. Explain the necessary measurements/geographic unit without inventing a bottom quartile."),
    "476928": ("absence", "The supplied catalog metadata does not establish Brazilian municipality geometries and matched population/area observations for a national-average comparison and two 20km distance tests. Country boundaries alone are not municipalities."),
    "727667": ("absence", "Wildfire incident points alone do not establish active burned-area/perimeter geometry and matched population density within those areas. Do not silently turn arbitrary incident buffers or reported sizes into observed fire footprints."),
    "305778": ("absence", "Economically strategic regions have no defined boundaries or measurable selection rule in the frozen inputs; power-station counts cannot establish strategic importance."),
    "529248": ("absence", "Distribution efficiency has no supplied objective, demand/service coverage, transmission connectivity or capacity standard. Stations per person is a different proxy, not an established efficiency measure."),
    "538378": ("absence", "Significant mining activity has no supplied threshold or region definition; facility presence is not production intensity. Country freshwater-withdrawal percentages cannot establish unspecified regional activity."),
    "833409": ("absence", "No renewable-energy-focus policy regions or power-station fuel/source classification is provided. Locations alone cannot identify renewable focus."),
    "146485": ("absence", "Northern Angola has no defined boundary or named region selection. The supplied population raster is count per cell, not density; choose a northern extent and derive density before producing the requested subset."),
    "265245": ("absence", "High energy demand is not defined or measured at the requested regional level; national historical per-capita consumption is not subnational demand. A threshold/geography or demand observations are required."),
    "304935": ("absence", "The African Great Lakes region has no defined country or basin membership and no local water-use measurements. National withdrawal ratios are not local lake-use patterns; disclose a country-level proxy only as a proposed different analysis."),
    "149968": ("absence", "Chile coastal areas require an explicit coastline/corridor or named administrative definition, absent from the frozen protocol. National boundaries include inland borders; buffering them is not a coastal definition. Count per cell also needs area conversion for density."),
    "459898": ("absence", "No aridity classification or precipitation/evapotranspiration observations are supplied. Country renewable-water totals cannot establish where arid regions are."),
    "811107": (
        "absence",
        "Brazilian state GDP per capita is absent; national GDP cannot select wealthy Brazilian states.",
    ),
    "577156": (
        "absence",
        "National agricultural value-added shares do not establish Brazilian state-level agricultural values.",
    ),
    "138450": (
        "absence",
        "No Chinese city built-up-area time series for 2015–2020; population alone is not urban sprawl.",
    ),
    "117526": (
        "absence",
        "No agricultural drought-severity index or matching agricultural-region coverage for southern Africa.",
    ),
    "772258": (
        "absence",
        "No African highway geometry or local forest-loss time series; national forest totals cannot measure highway-buffer deforestation.",
    ),
    "422124": (
        "absence",
        "USA towns cover only part of North America; Canada/Mexico population centres are absent. Clearly bounded USA-only work may be proposed but is not a continent-wide result.",
    ),
    "833518": (
        "absence",
        "No South American economic-corridor definitions or boundaries; railway buffers cannot silently stand in for economic corridors.",
    ),
    "397320": (
        "absence",
        "Continental African extraction points exist but population rasters cover only selected African countries. A labeled subset is not full African coverage.",
    ),
    "518135": (
        "absence",
        "Railway and population coverage does not span all upper-middle-income countries. Do not silently restrict the requested country group.",
    ),
    "911221": (
        "absence",
        "No energy-transition-plan geography; station locations do not establish policy commitments.",
    ),
    "221611": (
        "absence",
        "No Eastern European industrial pollution observations; CO2 country totals are not city hotspots.",
    ),
    "572164": ("absence", "No disaster-preparedness classification or regional readiness observations."),
    "965208": (
        "absence",
        "Population coverage is country-limited and high earthquake-frequency regions are undefined. A short earthquake snapshot is not long-run hazard frequency.",
    ),
    "768309": (
        "absence",
        "One Tibetan flood event plus Bangladesh population does not establish South-Asia-wide flood-prone population density.",
    ),
    "279238": (
        "absence",
        "A single February 2018 flood footprint is not a South American flood-risk model; population coverage is also incomplete.",
    ),
    "488600": (
        "absence",
        "Earthquake points are global, but population rasters cover only selected countries. A disclosed overlap subset must not be claimed global.",
    ),
    "979234": (
        "absence",
        "Supplied population rasters do not cover the requested low-income African mining-country set; income and source coverage must not be inferred from facility presence.",
    ),
    "526880": ("absence", "No biodiversity-hotspot boundaries or classifications."),
    "677223": (
        "absence",
        "No renewable-energy production table; electricity consumption and plant capacity are different quantities.",
    ),
    "214430": (
        "absence",
        "No globally covering major-city population and corresponding urban-area boundaries; national population density is not city density.",
    ),
    "544781": ("absence", "No marine protected area polygons or designation observations."),
    "488696": (
        "absence",
        "National forest area is not urban green-space percentage; city green-space coverage is missing.",
    ),
    "938589": ("absence", "National population history is not a ten-year series for African capital cities."),
    "447179": (
        "absence",
        "No healthcare-infrastructure measurements or facility inventory for developing economies.",
    ),
    "436356": (
        "absence",
        "No African forest-patch geometry and protected-area boundaries; country forest totals cannot measure fragmentation.",
    ),
    "954523": (
        "absence",
        "No district food-insecurity observations or matching Southeast Asian district geography.",
    ),
    "794962": (
        "absence",
        "Continental African population density coverage is absent; national totals or plant counts cannot locate concentration in populated areas.",
    ),
    "596713": (
        "absence",
        "Brazil railway lines exist but station points do not; line vertices cannot be invented as stations.",
    ),
    "264811": (
        "absence",
        "No urban-agglomeration polygons; town points alone do not delimit urbanized areas.",
    ),
    "342420": (
        "absence",
        "No subnational Brazilian GDP observations; country GDP cannot identify wealthy regions.",
    ),
    "664340": (
        "absence",
        "African railway lines exist, but population raster coverage is incomplete along the continental network.",
    ),
    "719909": (
        "absence",
        "No maritime-development-plan regions; port locations do not establish plan coverage.",
    ),
    "765686": (
        "absence",
        "No economic-cluster definitions/boundaries and matching complete population coverage.",
    ),
    "364138": (
        "definition",
        "Agriculture is cultivation of crops and/or raising livestock for food, fiber or other products.",
    ),
    "483163": (
        "definition",
        "A theodolite is a surveying instrument measuring horizontal and vertical angles; not itself a population/GIS dataset.",
    ),
    "299410": (
        "fiction",
        "Blefuscu is fictional in Swift's Gulliver's Travels. No real observed national crop statistics can be claimed; ask for a fictional or intended real-place interpretation.",
    ),
    "315340": (
        "absence",
        "No city AQI observations or pollutant measurements for South Asia. Population and national CO2 emissions do not establish city AQI.",
    ),
    "868995": (
        "absence",
        "No healthcare expenditure measurements; GDP and population do not determine healthcare expenditure.",
    ),
    "646908": ("absence", "No public education spending table for Scandinavian countries."),
    "537597": ("absence", "No healthcare expenditure as share of GDP observations for Western Europe."),
    "483194": (
        "absence",
        "No infant mortality observations for South Asia; fertility is not infant mortality.",
    ),
    "854925": (
        "absence",
        "No maternal mortality observations for West Africa; fertility does not measure maternal deaths.",
    ),
    "478472": ("absence", "No digital literacy observations for Southeast Asia."),
    "931200": (
        "absence",
        "No air pollution concentrations or exposure observations for East Asia; national CO2 inventories are not local ambient air pollution.",
    ),
    "673093": ("absence", "No foreign direct investment table for Asian economies; GDP is not FDI."),
    "128902": (
        "absence",
        "No unemployment rates for EU states; total labor force and population do not supply unemployed counts.",
    ),
    "792682": ("absence", "No public education spending table for Caribbean countries."),
    "663887": ("absence", "No environmental protection expenditure measurements."),
    "377506": ("absence", "No digital government service adoption observations."),
    "237711": ("absence", "No climate adaptation readiness indicators or vulnerability classification."),
    "558813": (
        "absence",
        "No energy security metrics; electricity consumption alone does not establish energy security.",
    ),
    "487632": (
        "absence",
        "No drought resilience observations; water withdrawals and forest area are not resilience indices.",
    ),
    "606612": (
        "absence",
        "No sustainable agriculture adoption evidence; agriculture share of GDP does not measure adoption.",
    ),
    "272016": ("absence", "No youth unemployment observations or age-disaggregated unemployment counts."),
}


def control_protocols():
    inventory = read(ROOT / "catalog-inventory.json")
    original = read(ROOT / "data/upstream/benchmark_set/tasks_and_reference_solutions.json")["tasks"]
    questions = {t["task_ID"].rsplit("_", 1)[-1]: t["task_text"] for t in original}
    catalog = "\n".join(f"- {v['kind']}: {v['title']}" for v in inventory["datasets"])
    return {
        task: {
            "title": questions[task],
            "question": questions[task],
            "family": "qualitative-control",
            "bbox": [-180, -85, 180, 85],
            "clarification": "This is a closed-catalog task. The complete original GeoBenchX source inventory is listed below; it describes available source types, not actual measurements. "
            "Do not supplement it with live data or claim numerical evidence from general knowledge. General knowledge may be used for definitions and explanation. "
            "Answer the original question as far as this information environment supports, accurately distinguishing observations, inference and uncertainty. "
            "This source-availability/control cohort supplies catalog metadata rather than the observation files and is reported separately from computational tasks.\n"
            + catalog,
            "outputContract": "Give a concise ordinary-language answer. No artificial count, result artifact, workflow or map is required when the answer does not warrant one. Do not invent observations or claim an analysis was run.",
        }
        for task in CONTROL_TASKS
    }


def control_answer(task):
    kind, fact = CONTROL_TASKS[task]
    criteria = (
        {
            "correct_definition": "Give a factually correct, useful definition.",
            "direct_answer": "Answer the asked concept directly rather than treating missing GIS data as an obstacle.",
            "no_fabrication": "Do not invent data, analysis or citations.",
        }
        if kind == "definition"
        else {
            "recognizes_fiction": "Recognize the fictional place rather than fabricate a real agricultural economy.",
            "scope_honesty": "Clearly separate fiction, real-world evidence and uncertainty.",
            "useful_next_step": "Offer an appropriate interpretation or clarification without inventing crop statistics.",
        }
        if kind == "fiction"
        else {
            "specific_obstacle": "Identify the actual missing measurement and requested geography, not just a generic refusal.",
            "no_false_proxy": "Do not pass a different quantity off as the requested observation.",
            "scope_honesty": "Describe absence in this frozen catalog, not universal nonexistence.",
            "no_fabrication": "Do not invent numbers, source records, a map or completed processing.",
            "useful_next_step": "Explain the data needed or a clearly separated next step.",
        }
    )
    return {
        "family": "qualitative-control",
        "kind": kind,
        "count": None,
        "basis": fact,
        "criteria": criteria,
        "rubricVersion": 1,
        "grading": "Operator adjudication of complete accepted answer and tool evidence against this pre-frozen rubric. Not blinded; no keyword-only pass; separate from computed correctness.",
    }
