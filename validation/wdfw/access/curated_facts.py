"""Hand-curated access facts for the 20 MVP waters (validation only).

Every fact is (state, value, evidence) where evidence is a list of (source_key, quote).
build_access_dataset.py checks that each quote appears verbatim (after whitespace and
punctuation normalization) in the cached official source, and refuses to build otherwise.

States: YES / NO / LIMITED / UNKNOWN. UNKNOWN means no authoritative source states it;
it never means NO. A "NO" must be backed by an explicit official statement or field.

Source keys:
  LP:<slug>        WDFW lowland-lake page   https://wdfw.wa.gov/fishing/locations/lowland-lakes/<slug>
  WAS:<slug>       WDFW water access site   https://wdfw.wa.gov/places-to-go/water-access-sites/<slug>
  GIS:<id>         WDFW ShoreFishingSites feature (AccessSiteID) Description
  WDFWLANDS        https://wdfw.wa.gov/places-to-go/water-access-sites (pass statement)
  DP               https://parks.wa.gov/passes-permits/get-park-pass/discover-pass
  ECO              https://www.nwtoxicalgae.org/ (WA Dept of Ecology)
  M:<url>          land-manager page (URL as fetched)
"""

BGL = "M:https://parks.wa.gov/find-parks/state-parks/battle-ground-lake-state-park"
LACAMAS = "M:https://clark.wa.gov/public-works/lacamas-regional-park"
KLINE = "M:https://clark.wa.gov/public-works/salmon-creek-regional-park/klineline-pond"
CLARKFEES = "M:https://clark.wa.gov/public-works/parking-fees"
GREEN = "M:https://www.seattle.gov/parks/parks/green-lake-park"
ANGLE = "M:https://www.seatacwa.gov/Community-and-recreation/Parks-and-trails/Angle-Lake-Park"
KENT = "M:https://www.kentwa.gov/departments/kent-parks/parks-places/parks-trails/lake-meridian-park"
MARTHA = "M:https://snohomishcountywa.gov/Facilities/Facility/Details/Martha-Lake-88"
LACEY = "M:https://cityoflacey.org/city-government/city-departments/parks-and-recreation/parks-and-facilities/municipal-parks/woodland-creek-community-park"
LAKEWOOD = "M:https://cityoflakewood.us/american-lake-park/"
TPU = "M:https://www.mytpu.org/community-environment-parks/parks-recreation/alder-lake-park/"
TPUFEES = "M:https://www.mytpu.org/community-environment-parks/parks-recreation/reservations-fees/"
BRADLEY = "M:https://www.puyallupwa.gov/2503/Bradley-Lake-Park"
SPAN = "M:https://www.piercecountywa.gov/1336/Spanaway-Park"
SNOCOPASS = "M:https://snohomishcountywa.gov/5281/Passes"

PASS_WDFW = ("YES", "Discover Pass or WDFW Vehicle Access Pass",
             [("WDFWLANDS", "A Discover Pass or Vehicle Access Pass is required at all WDFW recreation lands."),
              ("WDFWLANDS", "A Vehicle Access Pass provides access only to WDFW lands and is provided with the purchase of many hunting and fishing licenses.")])
FEE_WDFW = ("YES", "Pass only: Discover Pass ($10/day, $45/yr) or Vehicle Access Pass (included with many WDFW licenses)",
            [("WDFWLANDS", "A Discover Pass or Vehicle Access Pass is required at all WDFW recreation lands."),
             ("DP", "The one-day pass is $10.")])
HOURS_WDFW = ("UNKNOWN", "WDFW publishes seasonal open dates for access areas but no daily hours", [])


def was(slug, season_quote, parking_quote, platform_quote, extra=None):
    ap = {"ap_id": "wdfw-was:" + slug, "name": "WDFW water access area", "manager": "WDFW",
          "manager_type": "wdfw_water_access", "url": "https://wdfw.wa.gov/places-to-go/water-access-sites/" + slug,
          "coords_from": "WAS:" + slug,
          "parking_available": ("YES", parking_quote.split(": ")[1] + " lot(s)", [("WAS:" + slug, parking_quote)]),
          "fishing_platform": (("NO" if platform_quote.endswith("None") else "YES"), platform_quote,
                               [("WAS:" + slug, platform_quote)]),
          "seasonal_access": ("YES", season_quote.split(": ", 1)[1], [("WAS:" + slug, season_quote)]),
          "pass_required": PASS_WDFW, "parking_or_access_fee": FEE_WDFW, "operating_hours": HOURS_WDFW,
          "closure_channel": ("LIMITED", "No notice section; detect changes by hashing the access-site page", [])}
    if extra:
        ap.update(extra)
    return ap


FACTS = {
    "wa-w-battle-ground-lake": {
        "bank_fishing_status": ("LIMITED", "Limited bank access; a trail around the lake leads to shore spots",
                                [("LP:battle-ground-lake", "The lake offers limited bank access"),
                                 ("GIS:10030", "Trail around entire lake that leads to shore fishing spots")]),
        "fishing_pier_or_dock": ("YES", "Dock at the boat ramp",
                                 [("LP:battle-ground-lake", "limited bank access and a dock"), ("GIS:10029", "Boat ramp and dock")]),
        "rule_notes": [("LP:battle-ground-lake", "Fishing for or retaining grass carp is prohibited.")],
        "access_points": [{
            "ap_id": "wa-parks:battle-ground-lake-state-park", "name": "Battle Ground Lake State Park",
            "manager": "Washington State Parks", "manager_type": "state_park", "url": BGL[2:], "primary": True,
            "public_access": ("YES", "Lake is inside the state park", [("LP:battle-ground-lake", "Located inside Battle Ground Lake State Park")]),
            "parking_available": ("YES", "Park parking; Discover Pass required",
                                  [("LP:battle-ground-lake", "A Discover Pass is necessary to park at this lake.")]),
            "pass_required": ("YES", "Discover Pass (not needed if staying in a registered campsite)",
                              [("LP:battle-ground-lake", "A Discover Pass is necessary to park at this lake."),
                               ("LP:battle-ground-lake", "The Discover Pass is not necessary if staying in a registered campsite."),
                               ("DP", "A Discover Pass is required for parking at Washington State Parks")]),
            "parking_or_access_fee": ("YES", "Discover Pass $10/day or $45/yr; watercraft launch $7/day",
                                      [(BGL, "Annual Pass: $45 One-day Pass: $10 Watercraft Launch Fee: $7 for the day")]),
            "operating_hours": ("YES", "Summer 6:30 a.m.-dusk; winter 8:00 a.m.-dusk",
                                [(BGL, "Hours Summer: 6:30 a.m. - Dusk Winter: 8:00 a.m. - Dusk")]),
            "seasonal_access": ("LIMITED", "Off-season changes are on a separate Winter Schedule page (not captured)",
                                [(BGL, "Learn about seasonal closures and operational changes during the off-season on the Winter Schedule page")]),
            "closure_channel": ("YES", "Structured 'Alerts' block on the State Parks park page",
                                [(BGL, "Battle Ground Lake State Park Alerts Burn Ban - Level 1")]),
        }],
    },
    "wa-w-lacamas-lake": {
        "bank_fishing_status": ("LIMITED", "Limited public shore access; about 400 ft around the ramp; Round Lake (SE end) has good bank access",
                                [("LP:lacamas-lake", "Shore access is limited to the public."),
                                 ("LP:lacamas-lake", "Round Lake, located at the southeast end of the lake provides good bank access"),
                                 ("GIS:10291", "400 feet of shore fishing around the ramp")]),
        "fishing_pier_or_dock": ("UNKNOWN", "No official source mentions a fishing pier or dock", []),
        "access_points": [{
            "ap_id": "clark-county:lacamas-regional-park", "name": "Lacamas Regional Park (Round Lake)",
            "manager": "Clark County Parks", "manager_type": "county_park", "url": LACAMAS[2:], "primary": True,
            "public_access": ("YES", "County regional park with fishing", [(LACAMAS, "This 312-acre park has fishing, hiking and recreational opportunities")]),
            "parking_available": ("YES", "26 spaces + 1 disabled stall",
                                  [(LACAMAS, "26 parking spaces, plus 1 disabled parking stall"),
                                   ("GIS:10292", "Vehicle parking area with access to the shore")]),
            "parking_or_access_fee": ("NO", "Not one of the four Clark County regional parks that charge parking (closed list)",
                                      [(CLARKFEES, "Clark County charges daily parking fees year-round at four county regional parks"),
                                       (CLARKFEES, "Lewisville Regional Park, Salmon Creek Regional Park/Klineline Pond and Vancouver Lake Regional Park")],
                                      "MEDIUM"),
            "pass_required": ("UNKNOWN", "Not stated", []),
            "operating_hours": ("YES", "7 a.m. to dusk", [(LACAMAS, "Hours 7 a.m. to dusk (one half-hour after sunset)")]),
            "seasonal_access": ("UNKNOWN", "Not stated", []),
            "closure_channel": ("YES", "Project/closure updates posted on the park page",
                                [(LACAMAS, "Construction to replace a trail at Lacamas Regional Park is progressing.")]),
        }],
        "data_conflicts": ["The boat-ramp shore area (GIS) is not on the Clark County park page; its manager is not identified in sources used."],
    },
    "wa-w-klineline-pond": {
        "bank_fishing_status": ("YES", "Great bank access in the park", [("LP:klineline-pond", "The lake offers great bank access")]),
        "fishing_pier_or_dock": ("YES", "Fishing/observation platforms (3 WDFW pier points)",
                                 [(KLINE, "fishing/observation platforms"), ("GIS:10286", "Fishing pier")]),
        "rule_notes": [("LP:klineline-pond", "floating devices on the pond are restricted"),
                       ("LP:klineline-pond", "Fishing for or retaining grass carp is prohibited.")],
        "access_points": [{
            "ap_id": "clark-county:salmon-creek-klineline", "name": "Salmon Creek Regional Park/Klineline Pond",
            "manager": "Clark County Parks", "manager_type": "county_park", "url": KLINE[2:], "primary": True,
            "public_access": ("YES", "County regional park", [(KLINE, "Salmon Creek Regional Park/Klineline Pond is a popular spot")]),
            "parking_available": ("YES", "Parking incl. ADA", [(KLINE, "Parking, including ADA parking")]),
            "parking_or_access_fee": ("YES", "$5/day vehicle parking fee (or $40 county annual pass); 12 fee-free days in 2026",
                                      [(KLINE, "A $ 5-per-day vehicle parking fee is charged at the Klineline Pond entrance to the park."),
                                       (CLARKFEES, "An annual pass can be purchased for $40 online or from a fee collector."),
                                       (CLARKFEES, "Twelve parking fee-free days, including some weekdays, some weekend days, some federal holidays and other observances.")]),
            "pass_required": ("NO", "No Discover Pass; Discover Pass is not accepted (pay the county fee)",
                              [(CLARKFEES, "Passes from other agencies, such as the Washington State Parks Discover Pass, are NOT accepted at the four county regional parks listed above.")]),
            "operating_hours": ("YES", "7 a.m. to dusk", [(KLINE, "Hours 7 a.m. to dusk")]),
            "seasonal_access": ("UNKNOWN", "Not stated", []),
            "closure_channel": ("LIMITED", "Project section on the park page; no dedicated alert block", []),
        }],
    },
    "wa-w-green-lake-king": {
        "bank_fishing_status": ("YES", "City park surrounds the entire lake",
                                [("LP:green-lake-king", "extends around the entire lake providing excellent shoreline access to anglers")]),
        "fishing_pier_or_dock": ("YES", "Fishing docks on the south, east and northeast shores",
                                 [("LP:green-lake-king", "fishing docks are located at the south, east and northeast shores of the lake")]),
        "access_points": [{
            "ap_id": "seattle-parks:green-lake-park", "name": "Green Lake Park", "manager": "Seattle Parks and Recreation",
            "manager_type": "city_park", "url": GREEN[2:], "primary": True,
            "public_access": ("YES", "City park", [("LP:green-lake-king", "Green Lake Park, managed by Seattle Parks and Recreation")]),
            "parking_available": ("UNKNOWN", "Not stated on the official park page", []),
            "parking_or_access_fee": ("UNKNOWN", "Not stated", []),
            "pass_required": ("UNKNOWN", "Not stated", []),
            "operating_hours": ("YES", "4 a.m.-11:30 p.m.", [(GREEN, "4 am-11:30 pm")]),
            "seasonal_access": ("UNKNOWN", "Not stated", []),
            "closure_channel": ("LIMITED", "No notice block observed; page-hash monitoring only", []),
        }],
    },
    "wa-w-angle-lake": {
        "bank_fishing_status": ("LIMITED", "Fishing pier and some shoreline",
                                [("LP:angle-lake", "fishing pier and some shoreline")]),
        "fishing_pier_or_dock": ("YES", "Fishing pier (replacement scheduled; construction from January)",
                                 [("GIS:10012", "Public pier"),
                                  (ANGLE, "The fishing pier and boat ramp are scheduled for replacement with construction starting winter 2026")]),
        "current_notices": [(ANGLE, "The boat ramp is currently closed due to damage beyond repair.")],
        "access_points": [{
            "ap_id": "seatac:angle-lake-park", "name": "Angle Lake Park", "manager": "City of SeaTac",
            "manager_type": "city_park", "url": ANGLE[2:], "primary": True,
            "public_access": ("YES", "City park with bank access and pier",
                              [("LP:angle-lake", "Anglers can access the lake at Angle Lake Park where there is a boat launch, bank access, and a fishing pier available.")]),
            "parking_available": ("YES", "Parking listed as a park feature", [(ANGLE, "Picnic Tables Parking Open space Trails Restrooms Boat launch Fishing")]),
            "parking_or_access_fee": ("UNKNOWN", "Not stated", []),
            "pass_required": ("UNKNOWN", "Not stated", []),
            "operating_hours": ("YES", "Dawn to dusk daily except federal holidays; gate unlocked by 8 a.m.",
                                [(ANGLE, "Angle Lake Park is open from dawn until dusk every day, excluding federal holidays."),
                                 (ANGLE, "We unlock the park’s gate by 8 a.m. and lock it every evening.")]),
            "seasonal_access": ("UNKNOWN", "Not stated", []),
            "closure_channel": ("YES", "Dated 'Announcement' block on the park page",
                                [(ANGLE, "Angle Lake Park Announcement Posted 10/26/2026")]),
        }],
    },
    "wa-w-lake-meridian": {
        "bank_fishing_status": ("LIMITED", "Fishing is from the city park dock; wider shore access not described",
                                [("LP:lake-meridian", "Fishing pier at public park"), ("GIS:10343", "Large public dock")]),
        "fishing_pier_or_dock": ("YES", "Large public dock at the city park", [(KENT, "go fishing from the dock")]),
        "access_points": [
            {"ap_id": "kent:lake-meridian-park", "name": "Lake Meridian Park", "manager": "City of Kent",
             "manager_type": "city_park", "url": KENT[2:], "primary": True,
             "public_access": ("YES", "City park; WDFW ramp nearby",
                               [("LP:lake-meridian", "Both the WDFW and the City of Kent provide access to the lake on the southeast shore via a concrete boat ramp and fishing pier, respectively.")]),
             "parking_available": ("YES", "Parking listed as a park feature", [(KENT, "Features Parking Restrooms")]),
             "parking_or_access_fee": ("UNKNOWN", "Parking fee not stated; boat launch $8/day (Kent)",
                                       [(KENT, "PUBLIC BOAT LAUNCH FEES: $8.00/Day (daily launch pass)")]),
             "pass_required": ("UNKNOWN", "Not stated", []),
             "operating_hours": ("YES", "Dawn to dusk", [(KENT, "MyKentParks@KentWA.gov Dawn to Dusk")]),
             "seasonal_access": ("UNKNOWN", "Not stated", []),
             "closure_channel": ("YES", "'Park Updates/Announcements' section on the park page", [(KENT, "Park Updates/Announcements")])},
            was("lake-meridian-479", "Access area open: Year-round", "Parking lots: 1", "Fishing platforms: None"),
        ],
        "data_conflicts": ["WDFW lists the boat ramp as a WDFW water access area (Discover Pass/VAP), while Kent sells an $8/day launch pass at the same lake. WDFW notes that some WDFW-owned sites are managed by other agencies under their rules. Which pass or fee applies at the ramp needs confirmation."],
    },
    "wa-w-martha-alderwood-manor": {
        "bank_fishing_status": ("LIMITED", "Piers at the county park; very limited shore at the WDFW launch",
                                [("LP:martha-alderwood-manor", "Shoreline access at WDFW boat ramp and fishing pier at public park"),
                                 ("GIS:10479", "Very limited shore fishing at boat launch")]),
        "fishing_pier_or_dock": ("YES", "Fishing dock/piers at Martha Lake Park (WDFW says two, the county says 'a fishing dock')",
                                 [("LP:martha-alderwood-manor", "two large fishing piers"), (MARTHA, "The park includes a fishing dock")]),
        "rule_notes": [("LP:martha-alderwood-manor", "This lake is one of only twelve waters in Snohomish County managed with a seasonal fishing closure.")],
        "access_points": [
            {"ap_id": "snoco:martha-lake-park", "name": "Martha Lake Park", "manager": "Snohomish County Parks",
             "manager_type": "county_park", "url": MARTHA[2:], "primary": True,
             "public_access": ("YES", "County park", [("LP:martha-alderwood-manor", "Martha Lake Park (Snohomish County Parks) also offers parking and toilets")]),
             "parking_available": ("YES", "Parking + disabled parking", [("LP:martha-alderwood-manor", "Martha Lake Park (Snohomish County Parks) also offers parking and toilets")]),
             "parking_or_access_fee": ("NO", "Not one of the county parks that charge a day-use fee (closed list: Flowing Lake, Kayak Point, Wenberg)",
                                       [(SNOCOPASS, "Passes can be used at all of our parks that charge a day-use fee ( Flowing Lake Park, Kayak Point")], "MEDIUM"),
             "pass_required": ("UNKNOWN", "Not stated", []),
             "operating_hours": ("YES", "7 a.m. to dusk (20 min after sunset)", [(MARTHA, "Hours 7 a.m. - Dusk (20 minutes after sunset)")]),
             "seasonal_access": ("LIMITED", "Permanent restroom closed November-March",
                                 [(MARTHA, "The permanent restroom is winterized and closed November-March.")]),
             "closure_channel": ("YES", "County closure / burn-ban / alerts link from the park page",
                                 [(MARTHA, "Check for park closure, burn ban info and alerts here.")])},
            was("martha-lake-470", "Access area open: 4th Saturday in April - October 31", "Parking lots: 1", "Fishing platforms: None"),
        ],
    },
    "wa-w-ward-lake": {
        "bank_fishing_status": ("LIMITED", "Around the boat launch; limited by vegetation",
                                [("LP:ward-lake", "Bank fishing includes the area around the boat launch on the east side of the lake."),
                                 ("GIS:10708", "Shore fishing, limited by vegetation")]),
        "fishing_pier_or_dock": ("NO", "WDFW access lists no fishing platform", [("WAS:ward-lake-694", "Fishing platforms: None")]),
        "access_points": [dict(was("ward-lake-694", "Access area open: 4th Saturday in April - September 30", "Parking lots: 1", "Fishing platforms: None"), primary=True,
                               public_access=("YES", "WDFW water access area", [("LP:ward-lake", "Bank fishing includes the area around the boat launch")]))],
    },
    "wa-w-longs-pond": {
        "bank_fishing_status": ("YES", "Good shore access in Woodland Creek Community Park",
                                [("LP:longs-pond", "Woodland Creek community Park provides good shore access and a fishing dock")]),
        "fishing_pier_or_dock": ("YES", "Fishing dock, open during park hours",
                                 [(LACEY, "Longs Pond features a year-round fishing pond and dock open during normal park hours.")]),
        "rule_notes": [("LP:longs-pond", "Open for juvenile anglers, senior anglers and anglers with a disability who possess a designated harvester companion card only."),
                       ("LP:longs-pond", "Two-pole fishing is NOT allowed")],
        "data_conflicts": ["WDFW's first sentence says 'juveniles-only (age 14 and under)' but its special restriction also admits seniors and disabled anglers.",
                           "The City of Lacey page says 'No fishing license is required'. That is a regulatory claim from a non-regulator, so it is NOT used; WDFW rules govern."],
        "access_points": [{
            "ap_id": "lacey:woodland-creek-community-park", "name": "Woodland Creek Community Park", "manager": "City of Lacey",
            "manager_type": "city_park", "url": LACEY[2:], "primary": True,
            "public_access": ("YES", "City park", [(LACEY, "with Longs Pond serving as a centerpiece")]),
            "parking_available": ("YES", "Park parking lot (official history mentions it; capacity not stated)",
                                  [(LACEY, "the picnic shelters, restrooms, play equipment, trails, and parking lot were constructed")], "MEDIUM"),
            "parking_or_access_fee": ("UNKNOWN", "Not stated", []),
            "pass_required": ("UNKNOWN", "Not stated", []),
            "operating_hours": ("YES", "7 a.m. to dark", [(LACEY, "HOURS: 7AM - Dark")]),
            "seasonal_access": ("YES", "Year-round fishing pond", [(LACEY, "Longs Pond features a year-round fishing pond")]),
            "closure_channel": ("LIMITED", "Project notices on the park page; no alert block", []),
        }],
    },
    "wa-w-american-lake": {
        "bank_fishing_status": ("YES", "Large shore area at the WDFW access (400+ ft); docks and 300+ ft at a park",
                                [("LP:american-lake", "The WDFW access area has a large area for shore based fishing."),
                                 ("GIS:10009", "Over 400 feet of shore fishing at boat launch")]),
        "fishing_pier_or_dock": ("YES", "Public docks", [("GIS:10010", "Public docks, over 300 feet of shore fishing")]),
        "access_points": [
            dict(was("american-lake-244", "Access area open: Year-round", "Parking lots: 1", "Fishing platforms: None"), primary=True,
                 public_access=("YES", "WDFW water access area", [("LP:american-lake", "The WDFW access area has a large area for shore based fishing.")])),
            {"ap_id": "lakewood:american-lake-park", "name": "American Lake Park", "manager": "City of Lakewood",
             "manager_type": "city_park", "url": LAKEWOOD[2:],
             "public_access": ("YES", "City park with boat launch", [(LAKEWOOD, "Boat launch fees apply at a single launch rate of $15")]),
             "parking_available": ("UNKNOWN", "Not stated", []),
             "parking_or_access_fee": ("YES", "Boat launch $15 (cards only); parking fee not stated",
                                       [(LAKEWOOD, "Boat launch fees apply at a single launch rate of $15 (CREDIT/DEBIT CARDS ONLY)")]),
             "pass_required": ("UNKNOWN", "Not stated", []),
             "operating_hours": ("UNKNOWN", "Not stated on the park page", []),
             "seasonal_access": ("UNKNOWN", "Not stated", []),
             "closure_channel": ("LIMITED", "City news posts; no park alert block", [])},
        ],
    },
    "wa-w-alder-lake": {
        "bank_fishing_status": ("YES", "Plenty of public shore access along SR 7 and in Tacoma Power parks",
                                [("LP:alder-lake", "There is plenty of public shore access along SR 7 and in a few of Tacoma Power's parks, access areas, and campground.")]),
        "fishing_pier_or_dock": ("UNKNOWN", "Not stated", []),
        "access_points": [{
            "ap_id": "tacoma-power:alder-lake-park", "name": "Alder Lake Park", "manager": "Tacoma Power (Tacoma Public Utilities)",
            "manager_type": "utility_park", "url": TPU[2:], "primary": True,
            "public_access": ("YES", "Day-use access to Alder Lake", [(TPU, "Alder Lake Park offers day-use access to Alder Lake")]),
            "parking_available": ("YES", "Day-use parking", [(TPU, "Parking Information Parking fee: $10 on Fridays, Saturdays, Sundays, and holidays between")]),
            "parking_or_access_fee": ("YES", "$10 day-use parking Fri-Sun and holidays, Memorial Day to Labor Day; season pass $70",
                                      [(TPU, "Parking fee: $10 on Fridays, Saturdays, Sundays, and holidays between"),
                                       (TPUFEES, "Season day-use parking pass: $70")]),
            "pass_required": ("NO", "Discover Pass not required",
                              [(TPUFEES, "A Discover Pass is not required to access Tacoma Power parks, boat launches, or day-use areas.")]),
            "operating_hours": ("UNKNOWN", "Not stated", []),
            "seasonal_access": ("YES", "All Tacoma Power parks closed Dec. 20-Jan. 1; access varies with lake level",
                                [(TPU, "All parks are closed Dec. 20"),
                                 (TPU, "Boat launch access, swim areas, and lake levels may vary throughout the year.")]),
            "closure_channel": ("LIMITED", "Notes on the park page plus a lake-level page; no alert block", []),
        }],
    },
    "wa-w-mineral-lake": {
        "bank_fishing_status": ("LIMITED", "Access is limited; most shore fishing is from docks; 150 ft south of the ramp",
                                [("LP:mineral-lake", "Access is limited."),
                                 ("LP:mineral-lake", "Most shore fishing is from public fishing docks at the west end of the lake and docks at Mineral Lake Resort."),
                                 ("GIS:10502", "150 feet of shore fishing south of the ramp")]),
        "fishing_pier_or_dock": ("YES", "Public fishing docks at the west end; 1 platform at the WDFW access",
                                 [("LP:mineral-lake", "public fishing docks at the west end of the lake"), ("WAS:mineral-lake-485", "Fishing platforms: 1")]),
        "access_points": [dict(was("mineral-lake-485", "Access area open: Year-round", "Parking lots: 3", "Fishing platforms: 1"), primary=True,
                               public_access=("YES", "WDFW water access area", [("LP:mineral-lake", "The state boat launch is small")]))],
    },
    "wa-w-lake-bradley": {
        "bank_fishing_status": ("YES", "Good shoreline access, but ONLY for juveniles (14 and under), seniors (70+) and disabled anglers",
                                [("LP:lake-bradley", "Good shoreline access"),
                                 ("GIS:10078", "shore fishing, open only to juveniles (14 and younger), seniors (70+), and disabled persons")]),
        "fishing_pier_or_dock": ("YES", "Public pier (same eligibility restriction)",
                                 [("GIS:10079", "Public pier, open only to juveniles (14 and younger), seniors (70+), and disabled persons")]),
        "rule_notes": [("LP:lake-bradley", "Lake Bradley is open year round only for juvenile anglers, senior anglers, and anglers with a disability who possess a designated harvester companion card."),
                       ("LP:lake-bradley", "Two-pole fishing is NOT allowed")],
        "access_points": [{
            "ap_id": "puyallup:bradley-lake-park", "name": "Bradley Lake Park", "manager": "City of Puyallup",
            "manager_type": "city_park", "url": BRADLEY[2:], "primary": True,
            "public_access": ("YES", "City park with fishing areas", [(BRADLEY, "This park now includes fishing areas")]),
            "parking_available": ("YES", "Parking listed as a feature", [(BRADLEY, "Restrooms | Parking | Trails")]),
            "parking_or_access_fee": ("UNKNOWN", "Not stated", []),
            "pass_required": ("UNKNOWN", "Not stated", []),
            "operating_hours": ("YES", "Oct-Feb 6 a.m.-8 p.m.; Mar-Sep 6 a.m.-10 p.m.",
                                [(BRADLEY, "October - February: 6:00AM - 8:00PM March- September: 6:00AM - 10:00PM")]),
            "seasonal_access": ("YES", "Seasonal hours (above)", [(BRADLEY, "October - February: 6:00AM - 8:00PM")]),
            "closure_channel": ("LIMITED", "City news flash; no park alert block. The domain moved cityofpuyallup.org -> puyallupwa.gov and the page ID changed", []),
        }],
    },
    "wa-w-spanaway-lake": {
        "bank_fishing_status": ("YES", "Good shoreline access in Spanaway Park",
                                [("LP:spanaway-lake", "Shoreline access is good in Spanaway Park")]),
        "fishing_pier_or_dock": ("YES", "Fishing pier exists but is CLOSED for reconstruction (county: reopening 2027)",
                                 [(SPAN, "fishing pier (closed, under construction)"),
                                  (SPAN, "The project is scheduled for completion, with the dock reopening to the public in 2027.")]),
        "current_notices": [(SPAN, "Spanaway Park will be closed to vehicles, boats, and bikes from Saturday, October 24 through January 11, 2027, during the Fantasy Lights season."),
                            (SPAN, "Walkers may enter the park daily from 7:00 a.m. to 11:00 a.m."),
                            ("ECO", "Spanaway Lake 10/27/2026")],
        "access_points": [{
            "ap_id": "pierce-county:spanaway-park", "name": "Spanaway Park", "manager": "Pierce County Parks",
            "manager_type": "county_park", "url": SPAN[2:], "primary": True,
            "public_access": ("YES", "County park (vehicle closure Oct 24, 2026-Jan 11, 2027)",
                              [(SPAN, "Dive into aquatic activities with two swim beaches, a boat launch, and a fishing pier."),
                               ("LP:spanaway-lake", "Shoreline access is good in Spanaway Park")]),
            "parking_available": ("YES", "Park parking (seasonal fee); no vehicles during the Fantasy Lights closure",
                                  [(SPAN, "The boat launch and trailer parking are open for public use."), (SPAN, "Seasonal parking is $3.00")]),
            "parking_or_access_fee": ("YES", "Seasonal parking $3; boat launch $10", [(SPAN, "Boat Launch is $10.00* Seasonal parking is $3.00")]),
            "pass_required": ("UNKNOWN", "Not stated", []),
            "operating_hours": ("YES", "Seasonal schedule on the park page", [(SPAN, "The park will be open during the following hours, unless otherwise posted at the park.")]),
            "seasonal_access": ("YES", "Closed to vehicles Oct 24-Jan 11 (Fantasy Lights); closed Thanksgiving and Dec 25",
                                [(SPAN, "Spanaway Park will be closed to vehicles, boats, and bikes from Saturday, October 24 through January 11, 2027")]),
            "closure_channel": ("YES", "Dated closure notices at the top of the park page", [(SPAN, "Temporary Park Closure for Fantasy Lights")]),
        }],
    },
    "wa-w-lake-kapowsin": {
        "bank_fishing_status": ("LIMITED", "Walk-in areas along Oroville Rd; limited shore at the access; trail around the lake",
                                [("LP:lake-kapowsin", "There are walk in fishing areas along Oroville Rd."),
                                 ("GIS:10326", "Public dock, limited shore fishing"),
                                 ("GIS:10327", "Trail around lake provides additional shore fishing")]),
        "fishing_pier_or_dock": ("UNKNOWN", "CONFLICT: the GIS shore layer says 'Public dock'; the WDFW access page lists no fishing platforms", [
            ("GIS:10326", "Public dock, limited shore fishing"), ("WAS:lake-kapowsin-437", "Fishing platforms: None")], "LOW"),
        "data_conflicts": ["Dock: GIS 'Public dock' vs access-site 'Fishing platforms: None' (possibly a boarding dock). Needs human review."],
        "access_points": [dict(was("lake-kapowsin-437", "Access area open: Year-round", "Parking lots: 1", "Fishing platforms: None"), primary=True,
                               public_access=("YES", "WDFW water access area", [("LP:lake-kapowsin", "There are walk in fishing areas along Oroville Rd.")]))],
    },
    "wa-w-lake-whitman": {
        "bank_fishing_status": ("LIMITED", "Limited, at the boat launch",
                                [("LP:lake-whitman", "Shoreline access is limited, but accessible"), ("GIS:10433", "Limited shore fishing at boat launch")]),
        "fishing_pier_or_dock": ("NO", "No fishing platform at the WDFW access", [("WAS:lake-whitman-717", "Fishing platforms: None")]),
        "access_points": [dict(was("lake-whitman-717", "Access area open: Year-round", "Parking lots: 1", "Fishing platforms: None"), primary=True,
                               public_access=("YES", "WDFW water access area", [("LP:lake-whitman", "Shoreline access is limited, but accessible")]))],
    },
    "wa-w-tanwax-lake": {
        "bank_fishing_status": ("LIMITED", "Limited at the WDFW ramp; private resorts also offer dock/bank access",
                                [("GIS:10673", "Limited shore fishing access"),
                                 ("LP:tanwax-lake", "Multiple resorts and area around boat ramp provides adequate shoreline fishing access")]),
        "fishing_pier_or_dock": ("NO", "No public fishing platform; docks only at private resorts",
                                 [("WAS:tanwax-lake-666", "Fishing platforms: None"),
                                  ("LP:tanwax-lake", "Two private resorts also provide boat rentals, dock and bank access.")]),
        "rule_notes": [("LP:tanwax-lake", "Crappie is managed with a 9-inch minimum size and a 10 fish bag limit."),
                       ("LP:tanwax-lake", "Two-pole fishing is NOT allowed")],
        "access_points": [dict(was("tanwax-lake-666", "Access area open: Year-round", "Parking lots: 1", "Fishing platforms: None"), primary=True,
                               public_access=("YES", "WDFW access on the south shore", [("LP:tanwax-lake", "A WDFW access on the south shore provides a paved boat ramp and toilets.")]))],
    },
    "wa-w-clear-lake-pierce": {
        "bank_fishing_status": ("LIMITED", "Limited, from the public launch", [("LP:clear-lake-pierce", "Limited shoreline access from public launch")]),
        "fishing_pier_or_dock": ("NO", "No fishing platform at the WDFW access", [("WAS:clear-lake-309", "Fishing platforms: None")]),
        "rule_notes": [("LP:clear-lake-pierce", "Clear Lake is open to fishing from the fourth Saturday in April to October 31."),
                       ("LP:clear-lake-pierce", "Chumming is permitted.")],
        "access_points": [dict(was("clear-lake-309", "Access area open: Year-round. Open to vehicles only during the regulated sport fishing season(s).", "Parking lots: 1", "Fishing platforms: None"), primary=True,
                               public_access=("YES", "WDFW access on the northwest shore", [("LP:clear-lake-pierce", "The WDFW access on the northwest shore has a paved boat ramp with toilets and adequate parking.")]))],
    },
    "wa-w-bonney-lake": {
        "bank_fishing_status": ("LIMITED", "Limited shoreline access", [("LP:bonney-lake", "Limited shoreline access")]),
        "fishing_pier_or_dock": ("NO", "No fishing platform at the WDFW access", [("WAS:bonney-lake-273", "Fishing platforms: None")]),
        "access_points": [dict(was("bonney-lake-273", "Access area open: Year-round", "Parking lots: 1", "Fishing platforms: None"), primary=True,
                               public_access=("YES", "WDFW boat ramp on the northwest shore", [("LP:bonney-lake", "The lake has a WDFW boat ramp on the northwest shore")]),
                               parking_available=("LIMITED", "Limited parking; no restroom",
                                                  [("LP:bonney-lake", "with a shallow gravel ramp, no restroom, and limited parking."), ("WAS:bonney-lake-273", "Parking lots: 1")]))],
    },
    "wa-w-rapjohn-lake": {
        "bank_fishing_status": ("LIMITED", "Limited, at the boat launch",
                                [("LP:rapjohn-lake", "Limited shoreline access"), ("GIS:10585", "Limited shore fishing at boat launch")]),
        "fishing_pier_or_dock": ("NO", "No fishing platform at the WDFW access", [("WAS:rapjohn-lake-558", "Fishing platforms: None")]),
        "rule_notes": [("LP:rapjohn-lake", "Rapjohn Lake is currently open from the fourth Saturday in April through October 31")],
        "access_points": [dict(was("rapjohn-lake-558", "Access area open: Year-round", "Parking lots: 1", "Fishing platforms: None"), primary=True,
                               public_access=("YES", "WDFW water access area", [("LP:rapjohn-lake", "Limited shoreline access")]))],
    },
}
