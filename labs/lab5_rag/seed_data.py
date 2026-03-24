import sqlite3

DB_PATH = "ice_news.db"

articles = [
    {
        "headline": "ICE agents are at airports to help TSA ease travel woes. Here’s what we know about their deployment",
        "source": "CNN",
        "published_at": "2026-03-23",
        "url": "https://www.cnn.com/us/live-news/tsa-wait-times-ice-airports-03-23-26",
        "state": "",
        "city": "",
        "county": "",
        "region_type": "national",
        "topic_tags": "tsa,airports,shutdown,ice,national",
        "snippet": "ICE agents were deployed to 14 airports as the Trump administration responded to long TSA delays during the DHS shutdown. The report says agents were seen in places including New York, Houston, Atlanta, and Chicago, but their roles were limited and often unclear.",
        "full_text": "ICE agents were deployed to 14 airports as the Trump administration responded to long TSA delays during the DHS shutdown. The report says agents were seen in places including New York, Houston, Atlanta, and Chicago, but their roles were limited and often unclear."
    },
    {
        "headline": "The ICE Contractor Down the Hall",
        "source": "Curbed / New York Magazine",
        "published_at": "2026-02-24",
        "url": "https://www.curbed.com/article/ice-nyc-immigrant-detention-facilities-business-contracts.html",
        "state": "New York",
        "city": "New York City",
        "county": "",
        "region_type": "city",
        "topic_tags": "nyc,detention,contracts,facilities,ice",
        "snippet": "This article examines ICE’s footprint in and around New York City, including field offices, detention sites, vehicle parking, and private contractors doing business with the agency. It also highlights the agency’s expanding real-estate and contracting presence in the region.",
        "full_text": "This article examines ICE’s footprint in and around New York City, including field offices, detention sites, vehicle parking, and private contractors doing business with the agency. It also highlights the agency’s expanding real-estate and contracting presence in the region."
    },
    {
        "headline": "They’re the Heat on ICE",
        "source": "Intelligencer / New York Magazine",
        "published_at": "2025-12-11",
        "url": "https://nymag.com/intelligencer/article/ice-hands-off-nyc-immigration-raids-protests.html",
        "state": "New York",
        "city": "New York City",
        "county": "",
        "region_type": "city",
        "topic_tags": "nyc,raids,protests,activism,ice",
        "snippet": "The story follows organizers and community members in New York City who mobilized against ICE raids and built resistance networks after federal agents detained street vendors in Manhattan. It focuses on protest tactics, rapid-response organizing, and the local resistance movement.",
        "full_text": "The story follows organizers and community members in New York City who mobilized against ICE raids and built resistance networks after federal agents detained street vendors in Manhattan. It focuses on protest tactics, rapid-response organizing, and the local resistance movement."
    },
    {
        "headline": "2 NJ Women In ICE Custody After Prostitution Bust At NY Hotel",
        "source": "Daily Voice",
        "published_at": "2026-03-24",
        "url": "https://dailyvoice.com/ny/new-windsor/2-nj-women-in-ice-custody-after-prostitution-bust-at-ny-hotel/",
        "state": "New York",
        "city": "East Garden City",
        "county": "",
        "region_type": "city",
        "topic_tags": "new york,long island,arrest,ice,custody",
        "snippet": "A prostitution investigation at a Long Island hotel led to two arrests and subsequent federal immigration action, according to the report. The article centers on two New Jersey women taken into ICE custody after the bust.",
        "full_text": "A prostitution investigation at a Long Island hotel led to two arrests and subsequent federal immigration action, according to the report. The article centers on two New Jersey women taken into ICE custody after the bust."
    },
    {
        "headline": "ICE custody deaths are at a 2-decade high. An Afghan refugee who helped U.S. forces is one of the latest to die.",
        "source": "CBS News",
        "published_at": "2026-03-19",
        "url": "https://www.cbsnews.com/news/ice-detainee-deaths-two-decade-high-last-year/",
        "state": "",
        "city": "",
        "county": "",
        "region_type": "national",
        "topic_tags": "national,detention,deaths,oversight,ice",
        "snippet": "CBS News reports that deaths in ICE custody reached a two-decade high in 2025. The story highlights the death of Mohammad Nazeer Paktiawal after being detained in North Texas and connects the rising death toll to record-high detention levels and concerns about medical care.",
        "full_text": "CBS News reports that deaths in ICE custody reached a two-decade high in 2025. The story highlights the death of Mohammad Nazeer Paktiawal after being detained in North Texas and connects the rising death toll to record-high detention levels and concerns about medical care."
    },
    {
        "headline": "ICE agents seen at Houston airports",
        "source": "Spectrum News",
        "published_at": "2026-03-23",
        "url": "https://spectrumlocalnews.com/tx/south-texas-el-paso/news/2026/03/23/ice-agents-helping-tsa-amid-partial-government-shutdown",
        "state": "Texas",
        "city": "Houston",
        "county": "",
        "region_type": "city",
        "topic_tags": "texas,houston,tsa,airport,shutdown,ice",
        "snippet": "The article reports ICE agents at Houston-area airports during the partial government shutdown as TSA staffing shortages disrupted travel. It ties the airport response in Houston to the broader federal shutdown and security-line delays.",
        "full_text": "The article reports ICE agents at Houston-area airports during the partial government shutdown as TSA staffing shortages disrupted travel. It ties the airport response in Houston to the broader federal shutdown and security-line delays."
    },
    {
        "headline": "As immigrant arrests rise, here’s what to know about ICE operations in Texas",
        "source": "The Texas Tribune",
        "published_at": "2026-01-19",
        "url": "https://www.texastribune.org/2026/01/19/texas-immigration-ice-arrests-raids-police/",
        "state": "Texas",
        "city": "",
        "county": "",
        "region_type": "state",
        "topic_tags": "texas,raids,arrests,operations,ice",
        "snippet": "The Texas Tribune explains how ICE operations in Texas work as immigrant arrests increase under the Trump administration’s crackdown. The piece is framed as a guide to ICE activity in the state, including raids, arrests, and the broader enforcement environment.",
        "full_text": "The Texas Tribune explains how ICE operations in Texas work as immigrant arrests increase under the Trump administration’s crackdown. The piece is framed as a guide to ICE activity in the state, including raids, arrests, and the broader enforcement environment."
    },
    {
        "headline": "Trump deploys ICE to airports, signals national guard next",
        "source": "The National Desk",
        "published_at": "2026-03-23",
        "url": "https://thenationaldesk.com/news/americas-news-now/trump-deploys-ice-to-airports-signals-national-guard-next-dhs-shutdown-tsa-chicago-new-orleans-orlando-atlanta-traveler",
        "state": "",
        "city": "",
        "county": "",
        "region_type": "national",
        "topic_tags": "national,tsa,airports,shutdown,ice",
        "snippet": "This national story reports on the Trump administration’s deployment of ICE agents to airports during the DHS shutdown. It presents the move as part of a broader federal response to mounting TSA delays and signals that National Guard deployment could follow.",
        "full_text": "This national story reports on the Trump administration’s deployment of ICE agents to airports during the DHS shutdown. It presents the move as part of a broader federal response to mounting TSA delays and signals that National Guard deployment could follow."
    },
    {
        "headline": "New York City high school student Dylan Lopez Contreras speaks out after nearly 10 months held in ICE detention",
        "source": "ABC7 Chicago",
        "published_at": "2026-03-20",
        "url": "https://abc7chicago.com/post/new-york-city-high-school-student-dylan-lopez-contreras-speaks-10-months-held-ice-detention/18736219/",
        "state": "New York",
        "city": "New York City",
        "county": "",
        "region_type": "city",
        "topic_tags": "new york city,student,detention,release,ice",
        "snippet": "The article says Dylan Lopez Contreras, a 21-year-old New York City student, spoke publicly after spending nearly 10 months in ICE detention in Pennsylvania. It focuses on his release, his return to New York City, and the public response from family and local leaders.",
        "full_text": "The article says Dylan Lopez Contreras, a 21-year-old New York City student, spoke publicly after spending nearly 10 months in ICE detention in Pennsylvania. It focuses on his release, his return to New York City, and the public response from family and local leaders."
    }
]

state_metrics = [
    {
        "state": "New York",
        "state_abbr": "NY",
        "ice_facility_count": 5,
        "foreign_born_pct": 23.0,
        "non_citizen_pct": 10.0,
        "total_population": 19500000,
        "notes": "Large immigrant population and multiple news stories tied to detention, protests, and contracting activity in New York City."
    },
    {
        "state": "Texas",
        "state_abbr": "TX",
        "ice_facility_count": 21,
        "foreign_born_pct": 17.2,
        "non_citizen_pct": 8.5,
        "total_population": 30000000,
        "notes": "High detention presence and recurring stories about airport deployment, raids, and enforcement operations."
    }
]

def seed_database():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for article in articles:
        cur.execute(
            """
            INSERT OR IGNORE INTO articles
            (headline, source, published_at, url, state, city, county, region_type, topic_tags, snippet, full_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article["headline"],
                article["source"],
                article["published_at"],
                article["url"],
                article["state"],
                article["city"],
                article["county"],
                article["region_type"],
                article["topic_tags"],
                article["snippet"],
                article["full_text"],
            ),
        )

    for metric in state_metrics:
        cur.execute(
            """
            INSERT OR IGNORE INTO state_metrics
            (state, state_abbr, ice_facility_count, foreign_born_pct, non_citizen_pct, total_population, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric["state"],
                metric["state_abbr"],
                metric["ice_facility_count"],
                metric["foreign_born_pct"],
                metric["non_citizen_pct"],
                metric["total_population"],
                metric["notes"],
            ),
        )

    conn.commit()
    conn.close()
    print("sample data inserted successfully.")

if __name__ == "__main__":
    seed_database()