"""Disclosed geographical conventions from the frozen questions/reference editions."""
ARCTIC = ["Canada", "Denmark", "Finland", "Iceland", "Norway", "Russian Federation", "Sweden", "United States"]
AMAZON = ["Bolivia", "Brazil", "Colombia", "Ecuador", "Guyana", "Peru", "Suriname", "Venezuela, RB"]
HIMALAYA = ["Nepal", "Bhutan", "India", "China", "Pakistan"]
BRICS = ["Brazil", "Russian Federation", "India", "China", "South Africa", "Egypt, Arab Rep.", "Ethiopia", "Iran, Islamic Rep.", "United Arab Emirates", "Indonesia"]
G7 = ["Canada", "France", "Germany", "Italy", "Japan", "United Kingdom", "United States"]

# (indicator, original question, field, permitted values). Lists are scope, not computed answers.
REGIONAL = {
    "734213": ("migration", "Which Eastern African countries had the highest net migration rates in 2019?", "SUBREGION", ["Eastern Africa"]),
    "399319": ("water_volume", "Map the renewable water resources per capita in Middle Eastern countries.", "SUBREGION", ["Western Asia"]),
    "946748": ("population", "Map population density in Southern Asian nations", "SUBREGION", ["Southern Asia"]),
    "498483": ("water_withdrawal", "Show the distribution of water stress in Mediterranean coastal areas?", "SUBREGION", ["Southern Europe", "Northern Africa", "Western Asia"]),
    "441352": ("fertility", "Compare fertility rates between Eastern and Western African countries", "SUBREGION", ["Eastern Africa", "Western Africa"]),
    "598665": ("agriculture", "Show agricultural productivity across Mediterranean countries.", "SUBREGION", ["Southern Europe", "Northern Africa", "Western Asia"]),
    "898861": ("agriculture", "Map the distribution of agricultural productivity in sub-Saharan Africa.", "SUBREGION", ["Western Africa", "Middle Africa", "Southern Africa", "Eastern Africa"]),
    "720013": ("electricity", "Show electric consumption in G7 and BRICS nations", "NAME_EN", G7 + BRICS),
    "965287": ("rural", "Map rural population distribution in Central Asian nations", "SUBREGION", ["Central Asia"]),
    "186506": ("agriculture", "Compare agricultural GDP contribution across Andean countries", "NAME_EN", ["Bolivia", "Colombia", "Ecuador", "Peru"]),
    "535461": ("water_withdrawal", "Display water stress levels in Middle Eastern and North African countries. ", "SUBREGION", ["Northern Africa", "Western Asia"]),
    "526765": ("water_volume", "Compare water usage between Upper and Lower Nile countries. ", "NAME_EN", ["Egypt, Arab Rep.", "Sudan", "South Sudan", "Ethiopia", "Uganda", "Tanzania", "Rwanda", "Burundi", "Congo, Dem. Rep.", "Kenya", "Eritrea"]),
    "222041": ("electricity", "How does electric consumption vary across Arctic nations?", "NAME_EN", ARCTIC),
    "903748": ("forest_percent", "How does forest coverage vary across Amazon Treaty countries? ", "NAME_EN", AMAZON),
    "385630": ("forest_percent", "How does forest coverage vary across Pacific island nations?", "NAME_EN", ["Fiji", "Papua New Guinea", "Solomon Islands", "Vanuatu", "Kiribati", "Marshall Islands", "Federated States of Micronesia", "Nauru", "Palau", "Samoa", "Tonga", "Tuvalu", "New Zealand"]),
    "595832": ("water_volume", "Map water usage patterns in Middle Eastern countries", "SUBREGION", ["Western Asia"]),
    "258248": ("labor", "Show labor force distribution in Arctic Circle countries", "NAME_EN", ARCTIC),
    "901809": ("gdp", "Compare GDP per capita between OECD and non-OECD high-income countries", "INCOME_GRP", ["1. High income: OECD", "2. High income: nonOECD"]),
    "826615": ("agriculture", "Show agricultural GDP contribution in Nordic countries", "NAME_EN", ["Denmark", "Finland", "Iceland", "Norway", "Sweden"]),
    "797835": ("fertility", "Visualize fertility rates across Sub-Saharan Africa", "SUBREGION", ["Western Africa", "Middle Africa", "Southern Africa", "Eastern Africa"]),
    "501368": ("fertility", "How does fertility rate vary across French-speaking African countries?", "NAME_EN", ["Algeria", "Benin", "Burkina Faso", "Burundi", "Cameroon", "Central African Republic", "Chad", "Comoros", "Congo, Rep.", "Congo, Dem. Rep.", "Cote d'Ivoire", "Djibouti", "Gabon", "Guinea", "Madagascar", "Mali", "Mauritania", "Morocco", "Niger", "Senegal", "Togo", "Tunisia"]),
    "945038": ("population", "Show population distribution in Caucasus region\n", "NAME_EN", ["Georgia", "Armenia", "Azerbaijan"]),
    "227822": ("water_volume", "Show water withdrawal patterns in South Asian peninsula", "SUBREGION", ["Southern Asia"]),
    "894468": ("agriculture", "Show agricultural GDP contribution in Himalayan nations.", "NAME_EN", HIMALAYA),
    "596430": ("forest_percent", "Compare forest coverage between Amazon basin countries", "NAME_EN", AMAZON),
    "191153": ("water_volume", "Show water withdrawal patterns in BRICS nations.", "NAME_EN", BRICS),
    "986773": ("population", "Map population distribution across English-speaking Caribbean islands.", "NAME_EN", ["Antigua and Barbuda", "The Bahamas", "Barbados", "Dominica", "Grenada", "Jamaica", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines", "Trinidad and Tobago", "Anguilla", "Bermuda", "British Virgin Islands", "Cayman Islands", "Montserrat", "Turks and Caicos Islands"]),
    "356076": ("forest_percent", "Compare forest coverage between Continental and Maritime Southeast Asia.\n", "SUBREGION", ["South-Eastern Asia"]),
    "169833": ("water_volume", "Show water withdrawal patterns in Himalayan nations.\n", "NAME_EN", HIMALAYA),
    "275666": ("rural", "Compare rural population percentages in Western Asian countries", "SUBREGION", ["Western Asia"]),
}
DERIVED = {
    "734213": ("migration", REGIONAL["734213"][1], "migration_per_thousand"),
    "399319": ("water_volume", REGIONAL["399319"][1], "internal_water_per_capita"),
    "946748": ("population", REGIONAL["946748"][1], "population_density"),
    "170096": ("population", "Show population density patterns across regions.", "population_density"),
    "748943": ("rural", "Show rural population percentages worldwide.", "rural_share"),
    "394050": ("rural", "Map global rural-urban population distribution.\n", "rural_share"),
    "913900": ("forest_percent", "Show rates of deforestation over the last decade.", "forest_change"),
    "275666": ("rural", REGIONAL["275666"][1], "rural_share"),
}
YEAR_OVERRIDES = {"186506": "2022", "894468": "2022", "598665": "2021", "498483": "2020", "734213":"2019", "399319":"2021"}
GROUP_COMPARISONS = {"901809": ("INCOME_GRP", {
    "OECD": ["1. High income: OECD"], "non_OECD": ["2. High income: nonOECD"]}),
    "526765": ("NAME_EN", {"Lower_Nile": ["Egypt, Arab Rep.", "Sudan"],
        "Upper_Nile": ["South Sudan", "Ethiopia", "Uganda", "Tanzania", "Rwanda", "Burundi", "Congo, Dem. Rep.", "Kenya", "Eritrea"]}),
    "356076": ("NAME_EN", {"Continental": ["Myanmar", "Thailand", "Laos", "Cambodia", "Viet Nam"],
        "Maritime": ["Brunei", "East Timor", "Indonesia", "Malaysia", "Philippines", "Singapore"]})}
GROUP_COMPARISONS["441352"] = ("SUBREGION", {"Eastern_Africa": ["Eastern Africa"], "Western_Africa": ["Western Africa"]})


def unit_for(task, standard):
    if task in DERIVED:
        if DERIVED[task][2] == "migration_per_thousand":
            return "net migrants per 1000 people"
        if DERIVED[task][2] == "internal_water_per_capita":
            return "m³ per person per year"
        if DERIVED[task][2] == "population_density":
            return "people/km²"
        return "% of population" if DERIVED[task][2] == "rural_share" else "percentage points (2021 minus 2011)"
    return standard


def assets_for(task, indicator):
    if task == '734213':
        return ('countries','migration','population')
    if task == '399319':
        return ('countries','water_volume','water_withdrawal','population')
    return ("countries", "rural", "population") if task in DERIVED and DERIVED[task][2] == "rural_share" else ("countries", indicator)


def years_for(task, default):
    return {"2011", "2021"} if task == "913900" else {YEAR_OVERRIDES.get(task, default)}
