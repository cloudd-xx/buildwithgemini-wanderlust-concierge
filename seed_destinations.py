"""Seed script for Wanderlust Concierge destination catalog in Firestore."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-6da6214c076e"
COLLECTION_NAME = "destinations"

SAMPLE_DESTINATIONS = [
    {
        "id": "kyoto-japan",
        "name": "Kyoto",
        "country": "Japan",
        "region": "East Asia",
        "description": "Ancient imperial capital known for classical Buddhist temples, traditional tea houses, and historic artisan shopping in Gion.",
        "best_season": "Spring (Cherry Blossoms) or Autumn (Fall Foliage)",
        "budget_tier": "$$",
        "vibe": ["culture", "history", "peaceful", "scenic", "artisan-shopping"],
        "top_attractions": ["Fushimi Inari-taisha", "Kinkaku-ji (Golden Pavilion)", "Arashiyama Bamboo Grove", "Gion Historic Shopping District"],
        "recommended_days": 4,
        "sample_daily_budget_usd": 120
    },
    {
        "id": "amalfi-coast-italy",
        "name": "Amalfi Coast",
        "country": "Italy",
        "region": "Southern Europe",
        "description": "Dramatic coastal stretch with pastel fishing villages, limoncello boutiques, and luxury seaside resorts.",
        "best_season": "May to September",
        "budget_tier": "$$$",
        "vibe": ["romance", "coastal", "luxury", "foodie", "resort-holiday"],
        "top_attractions": ["Positano Cliffside & Boutiques", "Villa Cimbrone in Ravello", "Path of the Gods Hike"],
        "recommended_days": 5,
        "sample_daily_budget_usd": 250
    },
    {
        "id": "banff-canada",
        "name": "Banff National Park",
        "country": "Canada",
        "region": "North America",
        "description": "Canada's oldest national park with turquoise glacial lakes, mountain lodges, and outdoor gear shopping in Banff town.",
        "best_season": "June to August (hiking) or December to March (skiing)",
        "budget_tier": "$$",
        "vibe": ["adventure", "nature", "hiking", "winter-sports"],
        "top_attractions": ["Lake Louise", "Moraine Lake", "Banff Gondola & Sulphur Mountain"],
        "recommended_days": 4,
        "sample_daily_budget_usd": 160
    },
    {
        "id": "oaxaca-mexico",
        "name": "Oaxaca",
        "country": "Mexico",
        "region": "North America",
        "description": "Vibrant culinary & artisan capital celebrated for indigenous craft markets, alebrijes studios, and mezcal distilleries.",
        "best_season": "October to April",
        "budget_tier": "$",
        "vibe": ["foodie", "culture", "artisan-shopping", "vibrant"],
        "top_attractions": ["Mercado 20 de Noviembre & Benito Juárez", "Hierve el Agua", "Monte Albán Ruins", "San Martín Tilcajete Artisan Studios"],
        "recommended_days": 4,
        "sample_daily_budget_usd": 65
    },
    {
        "id": "reykjavik-iceland",
        "name": "Reykjavik & South Coast",
        "country": "Iceland",
        "region": "Northern Europe",
        "description": "Gateway to geothermal wonders, Laugavegur design shopping, waterfalls, and Northern Lights.",
        "best_season": "September to March (Northern Lights) or June to August (Midnight Sun)",
        "budget_tier": "$$$",
        "vibe": ["adventure", "nature", "unique", "scenic"],
        "top_attractions": ["Blue Lagoon Geothermal Spa", "Skógafoss Waterfall", "Reynisfjara Black Sand Beach", "Laugavegur Shopping Street"],
        "recommended_days": 6,
        "sample_daily_budget_usd": 220
    },
    {
        "id": "tokyo-japan",
        "name": "Tokyo",
        "country": "Japan",
        "region": "East Asia",
        "description": "Futuristic entertainment and shopping metropolis featuring Warner Bros Studio Tour Harry Potter, Ghibli Museum, Shibuya & Ginza shopping districts, and Akihabara gaming.",
        "best_season": "March to May or September to November",
        "budget_tier": "$$$",
        "vibe": ["entertainment", "studio-tour", "shopping", "anime-pop-culture", "foodie", "vibrant"],
        "top_attractions": ["Warner Bros. Studio Tour Tokyo - The Making of Harry Potter", "Shibuya & Shinjuku Mega Shopping", "Ginza Luxury Boutiques", "Ghibli Museum", "teamLab Planets Digital Art Studio"],
        "recommended_days": 5,
        "sample_daily_budget_usd": 180
    },
    {
        "id": "orlando-usa",
        "name": "Orlando & Theme Park Capital",
        "country": "United States",
        "region": "North America",
        "description": "The world's premier entertainment holiday destination featuring Universal Studios, theme parks, outlet shopping malls, and family resort recreation.",
        "best_season": "January to May or October to December",
        "budget_tier": "$$$",
        "vibe": ["family-holiday", "theme-parks", "studio-tour", "entertainment", "outlet-shopping"],
        "top_attractions": ["Universal Studios & Islands of Adventure", "Universal Epic Universe", "Walt Disney World Resort", "Orlando International Premium Outlets", "Disney Springs Shopping & Dining"],
        "recommended_days": 5,
        "sample_daily_budget_usd": 220
    },
    {
        "id": "paris-france",
        "name": "Paris",
        "country": "France",
        "region": "Western Europe",
        "description": "Global fashion and culture capital renowned for haute couture boutiques, Champs-Élysées, historic department stores (Galeries Lafayette), and art studios.",
        "best_season": "April to June or September to November",
        "budget_tier": "$$$",
        "vibe": ["fashion", "luxury-shopping", "culture", "art-studios", "romance", "foodie"],
        "top_attractions": ["Champs-Élysées & Avenue Montaigne Shopping", "Galeries Lafayette & Le Marais Boutiques", "Louvre & Musée d'Orsay", "Montmartre Artist Studios", "Eiffel Tower"],
        "recommended_days": 5,
        "sample_daily_budget_usd": 230
    }
]


def seed():
    print(f"Connecting to Firestore for project: {PROJECT_ID}")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    for item in SAMPLE_DESTINATIONS:
        doc_id = item["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(item)
        print(f"  ✓ Seeded destination: {item['name']} ({doc_id})")

    print(f"Successfully seeded {len(SAMPLE_DESTINATIONS)} destinations into '{COLLECTION_NAME}' collection.")


if __name__ == "__main__":
    seed()
