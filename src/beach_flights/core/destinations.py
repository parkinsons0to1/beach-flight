"""Curated European & Med beach destinations with IANA timezones and offshore SST coords."""

from __future__ import annotations

from beach_flights.models import DestinationInfo

LONDON_ORIGINS: dict[str, str] = {
    "LGW": "Europe/London",
    "LHR": "Europe/London",
}

# Offshore coordinates are placed slightly offshore of each destination's primary beach
# so Open-Meteo's marine ocean grid resolves valid sea surface temperatures (not inland nulls).
DESTINATIONS: dict[str, DestinationInfo] = {
    "AGP": DestinationInfo(
        iata="AGP",
        name="Malaga",
        country="Spain",
        timezone="Europe/Madrid",
        sea_lat=36.69,
        sea_lon=-4.40,
        presets=["winter-sun", "west-med"],
    ),
    "ALC": DestinationInfo(
        iata="ALC",
        name="Alicante",
        country="Spain",
        timezone="Europe/Madrid",
        sea_lat=38.33,
        sea_lon=-0.46,
        presets=["winter-sun", "west-med"],
    ),
    "PMI": DestinationInfo(
        iata="PMI",
        name="Palma de Mallorca",
        country="Spain",
        timezone="Europe/Madrid",
        sea_lat=39.53,
        sea_lon=2.63,
        presets=["west-med"],
    ),
    "IBZ": DestinationInfo(
        iata="IBZ",
        name="Ibiza",
        country="Spain",
        timezone="Europe/Madrid",
        sea_lat=38.88,
        sea_lon=1.42,
        presets=["west-med"],
    ),
    "MAH": DestinationInfo(
        iata="MAH",
        name="Menorca",
        country="Spain",
        timezone="Europe/Madrid",
        sea_lat=39.85,
        sea_lon=4.28,
        presets=["west-med"],
    ),
    "BCN": DestinationInfo(
        iata="BCN",
        name="Barcelona",
        country="Spain",
        timezone="Europe/Madrid",
        sea_lat=41.36,
        sea_lon=2.21,
        presets=["west-med"],
    ),
    "VLC": DestinationInfo(
        iata="VLC",
        name="Valencia",
        country="Spain",
        timezone="Europe/Madrid",
        sea_lat=39.46,
        sea_lon=-0.30,
        presets=["west-med"],
    ),
    "TFS": DestinationInfo(
        iata="TFS",
        name="Tenerife South",
        country="Spain",
        timezone="Atlantic/Canary",
        sea_lat=28.02,
        sea_lon=-16.61,
        presets=["winter-sun"],
    ),
    "LPA": DestinationInfo(
        iata="LPA",
        name="Gran Canaria",
        country="Spain",
        timezone="Atlantic/Canary",
        sea_lat=27.93,
        sea_lon=-15.35,
        presets=["winter-sun"],
    ),
    "ACE": DestinationInfo(
        iata="ACE",
        name="Lanzarote",
        country="Spain",
        timezone="Atlantic/Canary",
        sea_lat=28.91,
        sea_lon=-13.62,
        presets=["winter-sun"],
    ),
    "FUE": DestinationInfo(
        iata="FUE",
        name="Fuerteventura",
        country="Spain",
        timezone="Atlantic/Canary",
        sea_lat=28.45,
        sea_lon=-13.84,
        presets=["winter-sun"],
    ),
    "FAO": DestinationInfo(
        iata="FAO",
        name="Faro (Algarve)",
        country="Portugal",
        timezone="Europe/Lisbon",
        sea_lat=36.98,
        sea_lon=-7.98,
        presets=["winter-sun", "west-med"],
    ),
    "FNC": DestinationInfo(
        iata="FNC",
        name="Madeira (Funchal)",
        country="Portugal",
        timezone="Atlantic/Madeira",
        sea_lat=32.63,
        sea_lon=-16.90,
        presets=["winter-sun", "west-med"],
    ),
    "AGA": DestinationInfo(
        iata="AGA",
        name="Agadir",
        country="Morocco",
        timezone="Africa/Casablanca",
        sea_lat=30.41,
        sea_lon=-9.63,
        presets=["winter-sun"],
    ),
    "NBE": DestinationInfo(
        iata="NBE",
        name="Enfidha / Hammamet",
        country="Tunisia",
        timezone="Africa/Tunis",
        sea_lat=36.38,
        sea_lon=10.63,
        presets=["winter-sun"],
    ),
    "SSH": DestinationInfo(
        iata="SSH",
        name="Sharm el-Sheikh",
        country="Egypt",
        timezone="Africa/Cairo",
        sea_lat=27.90,
        sea_lon=34.36,
        presets=["winter-sun"],
    ),
    "HRG": DestinationInfo(
        iata="HRG",
        name="Hurghada",
        country="Egypt",
        timezone="Africa/Cairo",
        sea_lat=27.23,
        sea_lon=33.86,
        presets=["winter-sun"],
    ),
    "NCE": DestinationInfo(
        iata="NCE",
        name="Nice",
        country="France",
        timezone="Europe/Paris",
        sea_lat=43.67,
        sea_lon=7.25,
        presets=["west-med"],
    ),
    "NAP": DestinationInfo(
        iata="NAP",
        name="Naples / Amalfi",
        country="Italy",
        timezone="Europe/Rome",
        sea_lat=40.78,
        sea_lon=14.25,
        presets=["east-med"],
    ),
    "CAG": DestinationInfo(
        iata="CAG",
        name="Cagliari (Sardinia)",
        country="Italy",
        timezone="Europe/Rome",
        sea_lat=39.18,
        sea_lon=9.15,
        presets=["west-med", "east-med"],
    ),
    "OLB": DestinationInfo(
        iata="OLB",
        name="Olbia (Sardinia)",
        country="Italy",
        timezone="Europe/Rome",
        sea_lat=40.92,
        sea_lon=9.56,
        presets=["east-med"],
    ),
    "PMO": DestinationInfo(
        iata="PMO",
        name="Palermo (Sicily)",
        country="Italy",
        timezone="Europe/Rome",
        sea_lat=38.19,
        sea_lon=13.34,
        presets=["east-med"],
    ),
    "DBV": DestinationInfo(
        iata="DBV",
        name="Dubrovnik",
        country="Croatia",
        timezone="Europe/Zagreb",
        sea_lat=42.63,
        sea_lon=18.08,
        presets=["east-med"],
    ),
    "SPU": DestinationInfo(
        iata="SPU",
        name="Split",
        country="Croatia",
        timezone="Europe/Zagreb",
        sea_lat=43.48,
        sea_lon=16.43,
        presets=["east-med"],
    ),
    "MLA": DestinationInfo(
        iata="MLA",
        name="Malta",
        country="Malta",
        timezone="Europe/Malta",
        sea_lat=35.91,
        sea_lon=14.54,
        presets=["winter-sun", "east-med"],
    ),
    "CFU": DestinationInfo(
        iata="CFU",
        name="Corfu",
        country="Greece",
        timezone="Europe/Athens",
        sea_lat=39.61,
        sea_lon=19.95,
        presets=["east-med"],
    ),
    "HER": DestinationInfo(
        iata="HER",
        name="Heraklion (Crete)",
        country="Greece",
        timezone="Europe/Athens",
        sea_lat=35.36,
        sea_lon=25.17,
        presets=["east-med"],
    ),
    "RHO": DestinationInfo(
        iata="RHO",
        name="Rhodes",
        country="Greece",
        timezone="Europe/Athens",
        sea_lat=36.44,
        sea_lon=28.25,
        presets=["east-med"],
    ),
    "JTR": DestinationInfo(
        iata="JTR",
        name="Santorini",
        country="Greece",
        timezone="Europe/Athens",
        sea_lat=36.38,
        sea_lon=25.50,
        presets=["east-med"],
    ),
    "LCA": DestinationInfo(
        iata="LCA",
        name="Larnaca",
        country="Cyprus",
        timezone="Asia/Nicosia",
        sea_lat=34.89,
        sea_lon=33.67,
        presets=["winter-sun", "east-med"],
    ),
    "PFO": DestinationInfo(
        iata="PFO",
        name="Paphos",
        country="Cyprus",
        timezone="Asia/Nicosia",
        sea_lat=34.74,
        sea_lon=32.41,
        presets=["winter-sun", "east-med"],
    ),
    "AYT": DestinationInfo(
        iata="AYT",
        name="Antalya",
        country="Turkey",
        timezone="Europe/Istanbul",
        sea_lat=36.83,
        sea_lon=30.72,
        presets=["east-med"],
    ),
    "DLM": DestinationInfo(
        iata="DLM",
        name="Dalaman",
        country="Turkey",
        timezone="Europe/Istanbul",
        sea_lat=36.68,
        sea_lon=28.76,
        presets=["east-med"],
    ),
}

PRESET_NAMES = ("winter-sun", "west-med", "east-med", "all")


def resolve_destinations(
    dest_codes: list[str] | None = None,
    preset: str = "winter-sun",
) -> list[DestinationInfo]:
    """Return DestinationInfo entries from explicit IATA codes or a named preset."""
    if dest_codes:
        resolved: list[DestinationInfo] = []
        for raw in dest_codes:
            code = raw.strip().upper()
            if not code:
                continue
            if code not in DESTINATIONS:
                supported = ", ".join(sorted(DESTINATIONS))
                raise ValueError(f"Unknown destination '{code}'. Supported: {supported}")
            resolved.append(DESTINATIONS[code])
        return resolved

    preset_norm = preset.strip().lower()
    if preset_norm == "all":
        return list(DESTINATIONS.values())
    if preset_norm not in PRESET_NAMES:
        raise ValueError(f"Unknown preset '{preset}'. Choose from: {', '.join(PRESET_NAMES)}")
    return [d for d in DESTINATIONS.values() if preset_norm in d.presets]


def get_airport_timezone(iata: str) -> str:
    """Look up IANA timezone for a London origin or beach destination."""
    code = iata.upper()
    if code in LONDON_ORIGINS:
        return LONDON_ORIGINS[code]
    if code in DESTINATIONS:
        return DESTINATIONS[code].timezone
    return "UTC"
