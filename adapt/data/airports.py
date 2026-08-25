"""Comprehensive IATA airport registry for the Passenger Search picker.

Atlas live inventory (via the atlas-flight CLI) is the source of truth for what
is actually bookable - it covers effectively every commercial airport worldwide,
but the CLI exposes no airport-directory endpoint. This registry is therefore a
curated discovery list of major airports across all continents. The UI also
accepts any typed 3-letter code not listed here, so every airport Atlas knows
remains reachable even beyond this list.

Each entry carries a coarse region, which `hubs_for()` uses to pick plausible
connecting points when no through-fare exists for a city pair. Guessing hubs
matters because every candidate costs a live CLI search.

This module is intentionally separate from mock_data.AIRPORTS: that small set
carries minimum-connection-time data used by the risk model, while this
registry exists purely for search/picker purposes.
"""

from dataclasses import dataclass

# Coarse regions - deliberately broad; they only steer hub selection.
SE_ASIA = "SE_ASIA"  # South-East Asia (not to be confused with the SEA airport code)
EASTASIA = "EASTASIA"
SOUTHASIA = "SOUTHASIA"
OCEANIA = "OCEANIA"
MIDEAST = "MIDEAST"  # Middle East / Central Asia / Turkey
EUROPE = "EUROPE"
AFRICA = "AFRICA"
NAMERICA = "NAMERICA"
LATAM = "LATAM"


@dataclass(frozen=True)
class AirportInfo:
    code: str
    city: str
    name: str
    region: str = ""


# (IATA code, city, airport name, region)
_RAW: tuple[tuple[str, str, str, str], ...] = (
    # South-East Asia
    ("KUL", "Kuala Lumpur", "Kuala Lumpur Intl", SE_ASIA),
    ("SZB", "Kuala Lumpur", "Sultan Abdul Aziz Shah", SE_ASIA),
    ("PEN", "Penang", "Penang Intl", SE_ASIA),
    ("BKI", "Kota Kinabalu", "Kota Kinabalu Intl", SE_ASIA),
    ("KCH", "Kuching", "Kuching Intl", SE_ASIA),
    ("LGK", "Langkawi", "Langkawi Intl", SE_ASIA),
    ("JHB", "Johor Bahru", "Senai Intl", SE_ASIA),
    ("SIN", "Singapore", "Changi", SE_ASIA),
    ("BKK", "Bangkok", "Suvarnabhumi", SE_ASIA),
    ("DMK", "Bangkok", "Don Mueang Intl", SE_ASIA),
    ("CNX", "Chiang Mai", "Chiang Mai Intl", SE_ASIA),
    ("HKT", "Phuket", "Phuket Intl", SE_ASIA),
    ("CGK", "Jakarta", "Soekarno-Hatta Intl", SE_ASIA),
    ("DPS", "Denpasar", "Ngurah Rai Intl", SE_ASIA),
    ("SUB", "Surabaya", "Juanda Intl", SE_ASIA),
    ("MNL", "Manila", "Ninoy Aquino Intl", SE_ASIA),
    ("CEB", "Cebu", "Mactan-Cebu Intl", SE_ASIA),
    ("HAN", "Hanoi", "Noi Bai Intl", SE_ASIA),
    ("SGN", "Ho Chi Minh City", "Tan Son Nhat Intl", SE_ASIA),
    ("PNH", "Phnom Penh", "Phnom Penh Intl", SE_ASIA),
    ("RGN", "Yangon", "Yangon Intl", SE_ASIA),
    ("VTE", "Vientiane", "Wattay Intl", SE_ASIA),
    ("BWN", "Bandar Seri Begawan", "Brunei Intl", SE_ASIA),
    # East Asia
    ("NRT", "Tokyo", "Narita Intl", EASTASIA),
    ("HND", "Tokyo", "Haneda", EASTASIA),
    ("KIX", "Osaka", "Kansai Intl", EASTASIA),
    ("NGO", "Nagoya", "Chubu Centrair Intl", EASTASIA),
    ("FUK", "Fukuoka", "Fukuoka", EASTASIA),
    ("CTS", "Sapporo", "New Chitose", EASTASIA),
    ("OKA", "Okinawa", "Naha", EASTASIA),
    ("ICN", "Seoul", "Incheon Intl", EASTASIA),
    ("GMP", "Seoul", "Gimpo Intl", EASTASIA),
    ("PUS", "Busan", "Gimhae Intl", EASTASIA),
    ("PEK", "Beijing", "Capital Intl", EASTASIA),
    ("PKX", "Beijing", "Daxing Intl", EASTASIA),
    ("PVG", "Shanghai", "Pudong Intl", EASTASIA),
    ("SHA", "Shanghai", "Hongqiao Intl", EASTASIA),
    ("CAN", "Guangzhou", "Baiyun Intl", EASTASIA),
    ("SZX", "Shenzhen", "Bao'an Intl", EASTASIA),
    ("CTU", "Chengdu", "Shuangliu Intl", EASTASIA),
    ("XIY", "Xi'an", "Xianyang Intl", EASTASIA),
    ("HKG", "Hong Kong", "Hong Kong Intl", EASTASIA),
    ("MFM", "Macau", "Macau Intl", EASTASIA),
    ("TPE", "Taipei", "Taiwan Taoyuan Intl", EASTASIA),
    ("TSA", "Taipei", "Songshan", EASTASIA),
    ("KHH", "Kaohsiung", "Kaohsiung Intl", EASTASIA),
    # South Asia
    ("DEL", "New Delhi", "Indira Gandhi Intl", SOUTHASIA),
    ("BOM", "Mumbai", "Chhatrapati Shivaji Maharaj Intl", SOUTHASIA),
    ("BLR", "Bengaluru", "Kempegowda Intl", SOUTHASIA),
    ("MAA", "Chennai", "Chennai Intl", SOUTHASIA),
    ("HYD", "Hyderabad", "Rajiv Gandhi Intl", SOUTHASIA),
    ("CCU", "Kolkata", "Netaji Subhas Chandra Bose Intl", SOUTHASIA),
    ("CMB", "Colombo", "Bandaranaike Intl", SOUTHASIA),
    ("DAC", "Dhaka", "Hazrat Shahjalal Intl", SOUTHASIA),
    ("KTM", "Kathmandu", "Tribhuvan Intl", SOUTHASIA),
    ("MLE", "Malé", "Velana Intl", SOUTHASIA),
    # Oceania
    ("SYD", "Sydney", "Kingsford Smith", OCEANIA),
    ("MEL", "Melbourne", "Melbourne", OCEANIA),
    ("BNE", "Brisbane", "Brisbane", OCEANIA),
    ("PER", "Perth", "Perth", OCEANIA),
    ("ADL", "Adelaide", "Adelaide", OCEANIA),
    ("AKL", "Auckland", "Auckland", OCEANIA),
    ("WLG", "Wellington", "Wellington Intl", OCEANIA),
    ("CHC", "Christchurch", "Christchurch Intl", OCEANIA),
    ("NAN", "Nadi", "Nadi Intl", OCEANIA),
    # Middle East & Central Asia
    ("DXB", "Dubai", "Dubai Intl", MIDEAST),
    ("AUH", "Abu Dhabi", "Zayed Intl", MIDEAST),
    ("DOH", "Doha", "Hamad Intl", MIDEAST),
    ("RUH", "Riyadh", "King Khalid Intl", MIDEAST),
    ("JED", "Jeddah", "King Abdulaziz Intl", MIDEAST),
    ("MCT", "Muscat", "Muscat Intl", MIDEAST),
    ("BAH", "Manama", "Bahrain Intl", MIDEAST),
    ("KWI", "Kuwait City", "Kuwait Intl", MIDEAST),
    ("SHJ", "Sharjah", "Sharjah Intl", MIDEAST),
    ("AMM", "Amman", "Queen Alia Intl", MIDEAST),
    ("TLV", "Tel Aviv", "Ben Gurion", MIDEAST),
    ("IST", "Istanbul", "Istanbul", MIDEAST),
    ("SAW", "Istanbul", "Sabiha Gökçen Intl", MIDEAST),
    ("TAS", "Tashkent", "Tashkent Intl", MIDEAST),
    ("ALA", "Almaty", "Almaty Intl", MIDEAST),
    # Europe
    ("LHR", "London", "Heathrow", EUROPE),
    ("LGW", "London", "Gatwick", EUROPE),
    ("STN", "London", "Stansted", EUROPE),
    ("MAN", "Manchester", "Manchester", EUROPE),
    ("EDI", "Edinburgh", "Edinburgh", EUROPE),
    ("DUB", "Dublin", "Dublin", EUROPE),
    ("CDG", "Paris", "Charles de Gaulle", EUROPE),
    ("ORY", "Paris", "Orly", EUROPE),
    ("AMS", "Amsterdam", "Schiphol", EUROPE),
    ("FRA", "Frankfurt", "Frankfurt am Main", EUROPE),
    ("MUC", "Munich", "Munich", EUROPE),
    ("BER", "Berlin", "Brandenburg", EUROPE),
    ("ZRH", "Zurich", "Zurich", EUROPE),
    ("GVA", "Geneva", "Geneva", EUROPE),
    ("VIE", "Vienna", "Vienna Intl", EUROPE),
    ("MAD", "Madrid", "Barajas", EUROPE),
    ("BCN", "Barcelona", "El Prat", EUROPE),
    ("LIS", "Lisbon", "Humberto Delgado", EUROPE),
    ("FCO", "Rome", "Fiumicino", EUROPE),
    ("MXP", "Milan", "Malpensa", EUROPE),
    ("VCE", "Venice", "Marco Polo", EUROPE),
    ("ATH", "Athens", "Athens Intl", EUROPE),
    ("CPH", "Copenhagen", "Kastrup", EUROPE),
    ("OSL", "Oslo", "Gardermoen", EUROPE),
    ("ARN", "Stockholm", "Arlanda", EUROPE),
    ("HEL", "Helsinki", "Helsinki-Vantaa", EUROPE),
    ("WAW", "Warsaw", "Chopin", EUROPE),
    ("PRG", "Prague", "Václav Havel", EUROPE),
    ("BUD", "Budapest", "Ferenc Liszt Intl", EUROPE),
    ("BRU", "Brussels", "Brussels", EUROPE),
    ("LUX", "Luxembourg", "Luxembourg", EUROPE),
    ("KEF", "Reykjavik", "Keflavik Intl", EUROPE),
    # Africa
    ("JNB", "Johannesburg", "O.R. Tambo Intl", AFRICA),
    ("CPT", "Cape Town", "Cape Town Intl", AFRICA),
    ("CAI", "Cairo", "Cairo Intl", AFRICA),
    ("LOS", "Lagos", "Murtala Muhammed Intl", AFRICA),
    ("NBO", "Nairobi", "Jomo Kenyatta Intl", AFRICA),
    ("ADD", "Addis Ababa", "Bole Intl", AFRICA),
    ("CMN", "Casablanca", "Mohammed V Intl", AFRICA),
    ("TUN", "Tunis", "Tunis-Carthage Intl", AFRICA),
    ("ALG", "Algiers", "Houari Boumediene", AFRICA),
    ("ACC", "Accra", "Kotoka Intl", AFRICA),
    ("DAR", "Dar es Salaam", "Julius Nyerere Intl", AFRICA),
    # North America - United States
    ("JFK", "New York", "John F. Kennedy Intl", NAMERICA),
    ("EWR", "Newark", "Newark Liberty Intl", NAMERICA),
    ("LGA", "New York", "LaGuardia", NAMERICA),
    ("BOS", "Boston", "Logan Intl", NAMERICA),
    ("IAD", "Washington", "Dulles Intl", NAMERICA),
    ("DCA", "Washington", "Ronald Reagan National", NAMERICA),
    ("PHL", "Philadelphia", "Philadelphia Intl", NAMERICA),
    ("CLT", "Charlotte", "Charlotte Douglas Intl", NAMERICA),
    ("ATL", "Atlanta", "Hartsfield-Jackson Intl", NAMERICA),
    ("MIA", "Miami", "Miami Intl", NAMERICA),
    ("FLL", "Fort Lauderdale", "Fort Lauderdale-Hollywood Intl", NAMERICA),
    ("MCO", "Orlando", "Orlando Intl", NAMERICA),
    ("TPA", "Tampa", "Tampa Intl", NAMERICA),
    ("ORD", "Chicago", "O'Hare Intl", NAMERICA),
    ("MDW", "Chicago", "Midway Intl", NAMERICA),
    ("MSP", "Minneapolis", "Minneapolis-Saint Paul Intl", NAMERICA),
    ("DTW", "Detroit", "Detroit Metropolitan Wayne County", NAMERICA),
    ("DFW", "Dallas", "Dallas/Fort Worth Intl", NAMERICA),
    ("IAH", "Houston", "George Bush Intercontinental", NAMERICA),
    ("AUS", "Austin", "Austin-Bergstrom Intl", NAMERICA),
    ("DEN", "Denver", "Denver Intl", NAMERICA),
    ("PHX", "Phoenix", "Sky Harbor Intl", NAMERICA),
    ("LAS", "Las Vegas", "Harry Reid Intl", NAMERICA),
    ("SLC", "Salt Lake City", "Salt Lake City Intl", NAMERICA),
    ("SEA", "Seattle", "Seattle-Tacoma Intl", NAMERICA),
    ("PDX", "Portland", "Portland Intl", NAMERICA),
    ("SFO", "San Francisco", "San Francisco Intl", NAMERICA),
    ("LAX", "Los Angeles", "Los Angeles Intl", NAMERICA),
    ("ONT", "Ontario", "Ontario Intl", NAMERICA),
    ("SJC", "San Jose", "San Jose Intl", NAMERICA),
    ("SAN", "San Diego", "San Diego Intl", NAMERICA),
    ("HNL", "Honolulu", "Daniel K. Inouye Intl", NAMERICA),
    ("ANC", "Anchorage", "Ted Stevens Anchorage Intl", NAMERICA),
    # North America - Canada & Mexico
    ("YYZ", "Toronto", "Toronto Pearson Intl", NAMERICA),
    ("YVR", "Vancouver", "Vancouver Intl", NAMERICA),
    ("YUL", "Montreal", "Montreal-Trudeau Intl", NAMERICA),
    ("YYC", "Calgary", "Calgary Intl", NAMERICA),
    ("MEX", "Mexico City", "Benito Juárez Intl", NAMERICA),
    ("CUN", "Cancún", "Cancún Intl", NAMERICA),
    ("GDL", "Guadalajara", "Miguel Hidalgo y Costilla Intl", NAMERICA),
    # Latin America & Caribbean
    ("PTY", "Panama City", "Tocumen Intl", LATAM),
    ("SJU", "San Juan", "Luis Muñoz Marín Intl", LATAM),
    ("BOG", "Bogotá", "El Dorado Intl", LATAM),
    ("MDE", "Medellín", "José María Córdova Intl", LATAM),
    ("LIM", "Lima", "Jorge Chávez Intl", LATAM),
    ("UIO", "Quito", "Mariscal Sucre Intl", LATAM),
    ("SCL", "Santiago", "Arturo Merino Benítez Intl", LATAM),
    ("EZE", "Buenos Aires", "Ministro Pistarini Intl", LATAM),
    ("GRU", "São Paulo", "Guarulhos Intl", LATAM),
    ("GIG", "Rio de Janeiro", "Galeão Intl", LATAM),
)

WORLD_AIRPORTS: dict[str, AirportInfo] = {
    code: AirportInfo(code=code, city=city, name=name, region=region)
    for code, city, name, region in _RAW
}

# Major connecting airports, ordered by how much long-haul traffic they connect.
# Order is only a tiebreak; `hubs_for()` scores by region relevance first.
HUB_CODES: tuple[str, ...] = (
    "DXB", "DOH", "IST", "SIN", "HKG", "AUH", "BKK", "ICN", "NRT", "KUL",
    "LHR", "AMS", "CDG", "FRA", "MUC", "ZRH", "MAD", "VIE", "CPH",
    "DEL", "BOM", "BLR", "CMB",
    "JFK", "ORD", "DFW", "ATL", "LAX", "SFO", "YYZ",
    "ADD", "CAI", "JNB", "MEX", "PTY", "GRU", "SYD",
)

# Regions that plausibly sit between two others. Keys are unordered pairs, so a
# KUL -> AMS search and an AMS -> KUL search consider the same connecting points.
_BRIDGES: dict[frozenset[str], tuple[str, ...]] = {
    frozenset({SE_ASIA, EUROPE}): (MIDEAST, SOUTHASIA),
    frozenset({EASTASIA, EUROPE}): (MIDEAST,),
    frozenset({SOUTHASIA, EUROPE}): (MIDEAST,),
    frozenset({OCEANIA, EUROPE}): (MIDEAST, SE_ASIA),
    frozenset({SE_ASIA, NAMERICA}): (EASTASIA,),
    frozenset({EASTASIA, NAMERICA}): (EASTASIA,),
    frozenset({SOUTHASIA, NAMERICA}): (MIDEAST, EUROPE),
    frozenset({OCEANIA, NAMERICA}): (EASTASIA,),
    frozenset({EUROPE, NAMERICA}): (EUROPE, NAMERICA),
    frozenset({AFRICA, EUROPE}): (EUROPE, MIDEAST),
    frozenset({AFRICA, SE_ASIA}): (MIDEAST,),
    frozenset({AFRICA, NAMERICA}): (EUROPE,),
    frozenset({LATAM, EUROPE}): (EUROPE, NAMERICA),
    frozenset({LATAM, NAMERICA}): (NAMERICA, LATAM),
    frozenset({SE_ASIA, SOUTHASIA}): (SE_ASIA, SOUTHASIA),
    frozenset({SE_ASIA, MIDEAST}): (SE_ASIA, SOUTHASIA),
    frozenset({EUROPE, MIDEAST}): (EUROPE, MIDEAST),
}

# Fallback when a region pair isn't mapped: the world's busiest transfer regions.
_DEFAULT_BRIDGES: tuple[str, ...] = (MIDEAST, EUROPE)


def airport_region(code: str) -> str:
    info = WORLD_AIRPORTS.get(code.upper())
    return info.region if info else ""


def hubs_for(origin: str, destination: str, limit: int = 4) -> list[str]:
    """Plausible connecting airports for a city pair, best candidate first.

    Used only when no through-fare exists: each returned hub costs live CLI
    searches, so the list is scored (bridge region first, then either endpoint's
    own region) and truncated rather than tried exhaustively.
    """
    origin, destination = origin.upper(), destination.upper()
    origin_region = airport_region(origin)
    destination_region = airport_region(destination)
    bridges = _BRIDGES.get(
        frozenset({origin_region, destination_region}), _DEFAULT_BRIDGES
    )

    scored: list[tuple[int, int, str]] = []
    for index, code in enumerate(HUB_CODES):
        if code in (origin, destination):
            continue
        region = airport_region(code)
        score = 0
        if region in bridges:
            score += 3
        if region and region in (origin_region, destination_region):
            score += 2
        if score == 0:
            continue
        scored.append((-score, index, code))

    scored.sort()
    return [code for _, _, code in scored[:limit]]


def airport_city(code: str) -> str:
    """Best-known city name for an IATA code; falls back to the code itself."""
    info = WORLD_AIRPORTS.get(code.upper())
    return info.city if info else code.upper()


def is_valid_iata(code: str) -> bool:
    """Format-level check only - Atlas decides whether the airport is bookable."""
    return len(code) == 3 and code.isalpha()
