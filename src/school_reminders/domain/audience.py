"""School audience vocabulary for the 2026–27 academic year."""

ROSTER = {
    "Reception": ("Ash", "Beech"),
    "Year 1": ("Chestnut", "Damson"),
    "Year 2": ("Elm", "Fig"),
    "Year 3": ("Holly", "Juniper"),
    "Year 4": ("Maple", "Oak"),
    "Year 5": ("Pine", "Rowan"),
    "Year 6": ("Silver Birch", "Willow"),
}

CLASS_YEARS = {name: year for year, names in ROSTER.items() for name in names}
