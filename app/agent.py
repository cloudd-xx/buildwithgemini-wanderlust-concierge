# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from typing import Any, Dict, List

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
import google.genai as genai
from google.genai import types

MODEL = "gemini-3.7-flash"
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-03-6da6214c076e"
LOCATION = "us-east1"
MEMORY_BANK_ID = "8635066245785321472"
COLLECTION_NAME = "destinations"
GCS_BUCKET_NAME = "wanderlust-concierge-assets-qwiklabs-gcp-03-6da6214c076e"

# Initialize Firestore client with explicit project ID
db = firestore.Client(project=FIRESTORE_PROJECT_ID)
storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)


async def generate_memories_callback(callback_context: CallbackContext):
    """Callback to extract and persist durable traveler facts & preferences into Vertex AI Memory Bank."""
    await callback_context.add_session_to_memory()
    return None


def memory_bank_service_builder():
    """Builds the Vertex AI Memory Bank service instance for deployment."""
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location=LOCATION,
        agent_engine_id=MEMORY_BANK_ID,
    )


def list_destinations(vibe: str = "", max_budget_tier: str = "") -> List[Dict[str, Any]]:
    """List travel destinations from the catalog, optionally filtering by vibe or budget tier.

    Args:
        vibe: Optional theme or vibe to filter by (e.g. 'culture', 'nature', 'adventure', 'foodie', 'romance').
        max_budget_tier: Optional maximum budget tier ('$', '$$', '$$$').

    Returns:
        A list of matching destination summaries.
    """
    tier_weights = {"$": 1, "$$": 2, "$$$": 3}
    max_weight = tier_weights.get(max_budget_tier, 3)

    docs = db.collection(COLLECTION_NAME).stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        doc_tier = data.get("budget_tier", "$$")
        doc_weight = tier_weights.get(doc_tier, 2)

        if max_budget_tier and doc_weight > max_weight:
            continue

        if vibe:
            vibes = [v.lower() for v in data.get("vibe", [])]
            if vibe.lower() not in vibes and vibe.lower() not in data.get("description", "").lower():
                continue

        results.append({
            "id": doc.id,
            "name": data.get("name"),
            "country": data.get("country"),
            "region": data.get("region"),
            "budget_tier": data.get("budget_tier"),
            "best_season": data.get("best_season"),
            "vibe": data.get("vibe", []),
            "sample_daily_budget_usd": data.get("sample_daily_budget_usd"),
            "description": data.get("description"),
        })

    return results


def get_destination_details(destination_id: str) -> Dict[str, Any]:
    """Retrieve full details for a specific destination by its ID.

    Args:
        destination_id: The unique ID or slug of the destination (e.g., 'kyoto-japan', 'amalfi-coast-italy').

    Returns:
        The full destination record or an error message if not found.
    """
    doc_ref = db.collection(COLLECTION_NAME).document(destination_id)
    doc = doc_ref.get()
    if not doc.exists:
        # Fallback search by name
        docs = db.collection(COLLECTION_NAME).stream()
        for d in docs:
            data = d.to_dict()
            if destination_id.lower() in data.get("name", "").lower() or destination_id.lower() in d.id:
                return data
        return {"error": f"Destination with ID or name '{destination_id}' was not found in catalog."}

    return doc.to_dict()


def save_destination(
    name: str,
    country: str,
    region: str,
    description: str,
    best_season: str,
    budget_tier: str,
    vibe: List[str],
    top_attractions: List[str],
    recommended_days: int = 3,
    sample_daily_budget_usd: int = 100,
    destination_id: str = ""
) -> Dict[str, Any]:
    """Add a new destination or update an existing one in the Firestore catalog.

    Args:
        name: Name of the destination city/region (e.g., 'Tokyo').
        country: Country where the destination is located (e.g., 'Japan').
        region: Geographic region (e.g., 'East Asia', 'Western Europe').
        description: Brief overview highlighting the destination's appeal.
        best_season: Optimal time of year to visit.
        budget_tier: Estimated budget tier: '$', '$$', or '$$$'.
        vibe: List of vibe tags (e.g., ['culture', 'foodie', 'nightlife']).
        top_attractions: List of top 3-5 highlights/attractions.
        recommended_days: Recommended trip length in days.
        sample_daily_budget_usd: Estimated average daily cost per person in USD.
        destination_id: Optional custom document ID slug. If empty, derived from name and country.

    Returns:
        Status message with the saved destination ID and details.
    """
    if not destination_id:
        slug = f"{name.lower().replace(' ', '-')}-{country.lower().replace(' ', '-')}"
    else:
        slug = destination_id

    data = {
        "id": slug,
        "name": name,
        "country": country,
        "region": region,
        "description": description,
        "best_season": best_season,
        "budget_tier": budget_tier,
        "vibe": vibe,
        "top_attractions": top_attractions,
        "recommended_days": recommended_days,
        "sample_daily_budget_usd": sample_daily_budget_usd,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    doc_ref = db.collection(COLLECTION_NAME).document(slug)
    doc_ref.set(data, merge=True)

    return {
        "status": "success",
        "message": f"Destination '{name}' successfully saved in Firestore with ID '{slug}'.",
        "destination": data
    }


def calculate_trip_budget(
    destination_id: str,
    duration_days: int = 4,
    travelers_count: int = 1,
    travel_style: str = "moderate",
    target_currency: str = "USD"
) -> Dict[str, Any]:
    """Calculate an estimated trip budget breakdown for a destination and travel party.

    Args:
        destination_id: The destination ID or name (e.g., 'kyoto-japan', 'amalfi-coast-italy', 'oaxaca-mexico').
        duration_days: Length of trip in days (default: 4).
        travelers_count: Number of travelers (default: 1).
        travel_style: Travel style tier ('budget', 'moderate', 'luxury').
        target_currency: Preferred currency code for display ('USD', 'EUR', 'JPY', 'MXN', 'CAD', 'GBP').

    Returns:
        A detailed cost breakdown including accommodation, food, activities, local transit, and totals.
    """
    details = get_destination_details(destination_id)
    if "error" in details:
        base_daily_usd = 120
        dest_name = destination_id
    else:
        base_daily_usd = details.get("sample_daily_budget_usd") or 120
        dest_name = details.get("name", destination_id)

    # Style multipliers
    style_multipliers = {
        "budget": 0.65,
        "moderate": 1.0,
        "luxury": 2.2
    }
    multiplier = style_multipliers.get(travel_style.lower(), 1.0)
    adjusted_daily_usd = base_daily_usd * multiplier

    # Approximate currency exchange rates against USD
    exchange_rates = {
        "USD": 1.0,
        "EUR": 0.92,
        "JPY": 152.0,
        "MXN": 19.5,
        "CAD": 1.38,
        "GBP": 0.78
    }
    rate = exchange_rates.get(target_currency.upper(), 1.0)
    curr = target_currency.upper() if target_currency.upper() in exchange_rates else "USD"

    # Category breakdowns per person per day (USD)
    lodging_daily_usd = round(adjusted_daily_usd * 0.45, 2)
    food_daily_usd = round(adjusted_daily_usd * 0.30, 2)
    activities_daily_usd = round(adjusted_daily_usd * 0.15, 2)
    transit_daily_usd = round(adjusted_daily_usd * 0.10, 2)

    daily_per_person = lodging_daily_usd + food_daily_usd + activities_daily_usd + transit_daily_usd
    total_per_person_usd = daily_per_person * duration_days
    total_trip_usd = total_per_person_usd * travelers_count

    return {
        "destination": dest_name,
        "duration_days": duration_days,
        "travelers_count": travelers_count,
        "travel_style": travel_style,
        "currency": curr,
        "daily_breakdown_per_person": {
            "lodging": round(lodging_daily_usd * rate, 2),
            "food_and_dining": round(food_daily_usd * rate, 2),
            "activities_and_tickets": round(activities_daily_usd * rate, 2),
            "local_transit": round(transit_daily_usd * rate, 2),
            "total_daily": round(daily_per_person * rate, 2)
        },
        "totals": {
            "total_per_person": round(total_per_person_usd * rate, 2),
            "total_trip": round(total_trip_usd * rate, 2)
        }
    }


def recommend_hotels(
    destination_id: str,
    budget_tier: str = "$$",
    preferred_area: str = "",
    amenities: str = ""
) -> List[Dict[str, Any]]:
    """Recommend hotels and lodging options for a destination tailored to traveler budget and itinerary.

    Args:
        destination_id: Destination ID or name (e.g. 'kyoto-japan', 'amalfi-coast-italy', 'banff-canada').
        budget_tier: Target budget tier ('$' for budget/hostels, '$$' for boutique/mid-scale, '$$$' for luxury/resorts).
        preferred_area: Optional neighborhood or landmark proximity (e.g. 'Historic District', 'Beachfront', 'City Center').
        amenities: Optional preferred features (e.g. 'breakfast included', 'spa', 'mountain view', 'family friendly').

    Returns:
        A list of curated hotel recommendations with nightly price estimates, key perks, and area highlights.
    """
    dest = get_destination_details(destination_id)
    dest_name = dest.get("name", destination_id)

    # Curated hotel archetypes per tier
    tier_presets = {
        "$": [
            {"name": f"{dest_name} Heritage Guesthouse & Hostel", "type": "Boutique Hostel", "est_nightly_usd": 45, "perks": ["Central location", "Free high-speed WiFi", "Social lounge", "Luggage storage"], "match_reason": "Top-rated budget stay with easy transit access to all key itinerary stops."},
            {"name": f"{dest_name} Travelers Inn", "type": "Economy Hotel", "est_nightly_usd": 65, "perks": ["Ensuite rooms", "Complimentary breakfast", "Quiet neighborhood"], "match_reason": "Clean, highly rated budget lodging ideal for exploring on foot."}
        ],
        "$$": [
            {"name": f"{dest_name} Boutique Garden Hotel", "type": "Boutique Hotel", "est_nightly_usd": 140, "perks": ["Rooftop terrace", "Artisan breakfast", "Concierge tour bookings", "Modern design"], "match_reason": "Charming boutique property centrally situated near dining and cultural attractions."},
            {"name": f"The Grand {dest_name} Suites", "type": "4-Star Hotel", "est_nightly_usd": 185, "perks": ["Fitness center", "Scenic views", "On-site bistro", "Spacious suites"], "match_reason": "Comfortable mid-scale hotel with premium amenities and scenic views."}
        ],
        "$$$": [
            {"name": f"Villa {dest_name} Luxury Resort & Spa", "type": "5-Star Luxury Resort", "est_nightly_usd": 380, "perks": ["Full-service spa", "Michelin-starred dining", "Private airport transfer", "Infinity pool"], "match_reason": "World-class luxury retreat offering panoramic vistas and bespoke concierge service."},
            {"name": f"The Royal {dest_name} Palace Hotel", "type": "Historic Luxury Hotel", "est_nightly_usd": 450, "perks": ["Historic architecture", "Private balcony suites", "Butler service", "Thermal baths"], "match_reason": "Iconic luxury landmark combining historic elegance with high-end comfort."}
        ]
    }

    results = tier_presets.get(budget_tier, tier_presets["$$"])
    if preferred_area:
        for r in results:
            r["location_note"] = f"Located in/near {preferred_area}."
    if amenities:
        for r in results:
            r["amenities_note"] = f"Features requested amenities: {amenities}."

    return results


def compose_itinerary(
    destination_id: str,
    duration_days: int = 3,
    traveler_style: str = "holiday & leisure",
    include_shopping: bool = True,
    include_studios_entertainment: bool = True
) -> Dict[str, Any]:
    """Compose a structured day-by-day travel itinerary with sights, entertainment/studios, shopping spots, and dining.

    Args:
        destination_id: The destination ID or name (e.g. 'tokyo-japan', 'kyoto-japan', 'paris-france', 'orlando-usa').
        duration_days: Length of the trip in days (e.g. 3, 4, 5).
        traveler_style: Style of traveler ('holiday & leisure', 'culture & sights', 'adventure & nature', 'foodie & luxury').
        include_shopping: Whether to weave in nearby shopping districts/markets.
        include_studios_entertainment: Whether to weave in nearby studio tours, entertainment, or theme parks.

    Returns:
        A day-by-day itinerary breakdown with morning, afternoon, evening, shopping/studio stops, and dining tips.
    """
    dest = get_destination_details(destination_id)
    dest_name = dest.get("name", destination_id)
    attractions = dest.get("top_attractions", [f"Highlights of {dest_name}", f"Historic Center of {dest_name}", f"Scenic viewpoint in {dest_name}"])

    days = []
    for day_num in range(1, duration_days + 1):
        main_attraction = attractions[(day_num - 1) % len(attractions)]
        secondary = attractions[day_num % len(attractions)]

        day_plan = {
            "day": day_num,
            "title": f"Day {day_num}: Exploring {dest_name} ({traveler_style})",
            "morning": f"Visit {main_attraction} with scenic morning walking tour.",
            "afternoon": f"Explore {secondary} and local neighborhood attractions.",
            "evening": f"Sunset stroll, local dinner, and evening entertainment in {dest_name}.",
            "recommended_dining": "Local specialty bistro / culinary market."
        }

        if include_shopping:
            day_plan["shopping_stop"] = f"Nearby retail & craft shopping: Local artisan boutiques & district markets in {dest_name}."

        if include_studios_entertainment and (day_num == 1 or day_num == 2 or "studio" in dest_name.lower()):
            day_plan["entertainment_highlight"] = f"Entertainment & studio visit: immersive experience / studio tour in {dest_name}."

        days.append(day_plan)

    return {
        "destination": dest_name,
        "duration_days": duration_days,
        "traveler_style": traveler_style,
        "summary": f"Custom {duration_days}-day travel agent itinerary for {dest_name} tailored for {traveler_style}.",
        "days": days,
        "travel_agent_tips": [
            "Book studio tours, theme park tickets, and museum passes at least 2 weeks in advance.",
            "Schedule shopping in the late afternoon to drop bags off at the hotel before evening dining.",
            "Keep public transit card or pass handy for seamless hopping between districts."
        ]
    }


def get_destination_live_weather(
    destination_id: str
) -> Dict[str, Any]:
    """Fetch live real-time weather and temperature for a destination using Open-Meteo public API.

    Args:
        destination_id: Destination ID or name (e.g. 'tokyo-japan', 'kyoto-japan', 'paris-france', 'oaxaca-mexico').

    Returns:
        Live current weather conditions including temperature (°C), windspeed, and condition.
    """
    import urllib.request
    import json
    import os

    # Approximate coordinates for key destination catalog
    coords_map = {
        "kyoto-japan": (35.0116, 135.7681),
        "tokyo-japan": (35.6762, 139.6503),
        "amalfi-coast-italy": (40.6340, 14.6027),
        "banff-canada": (51.1784, -115.5708),
        "oaxaca-mexico": (17.0732, -96.7266),
        "reykjavik-iceland": (64.1466, -21.9426),
        "orlando-usa": (28.5383, -81.3792),
        "paris-france": (48.8566, 2.3522)
    }

    dest = get_destination_details(destination_id)
    dest_name = dest.get("name", destination_id)

    # Resolve coordinates or default to Tokyo
    lat, lon = coords_map.get(destination_id.lower(), (35.6762, 139.6503))

    # Support optional API key override if environment variable OPEN_METEO_API_KEY is provided
    api_key = os.getenv("OPEN_METEO_API_KEY", "")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    if api_key:
        url += f"&apikey={api_key}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WanderlustConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            current = data.get("current_weather", {})
            temp_c = current.get("temperature")
            temp_f = round((temp_c * 9 / 5) + 32, 1) if temp_c is not None else None

            return {
                "destination": dest_name,
                "temperature_c": temp_c,
                "temperature_f": temp_f,
                "windspeed_kmh": current.get("windspeed"),
                "is_daytime": bool(current.get("is_day", 1)),
                "time_utc": current.get("time"),
                "data_source": "Open-Meteo Public API"
            }
    except Exception as e:
        return {
            "destination": dest_name,
            "error": f"Unable to fetch live weather: {str(e)}",
            "fallback": "Please check seasonal guidelines in destination catalog."
        }


def geocode_address(address: str) -> Dict[str, Any]:
    """Convert a human-readable address or landmark name into geographic coordinates (latitude and longitude).

    Args:
        address: Address, city, or landmark to geocode (e.g. 'Eiffel Tower, Paris', 'Shibuya Crossing, Tokyo').

    Returns:
        A dictionary containing formatted address, latitude, longitude, and place ID.
    """
    import os
    import urllib.parse
    import urllib.request
    import json

    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {
            "error": "GOOGLE_MAPS_API_KEY is not configured or still set to placeholder in .env.",
            "address": address
        }

    encoded_address = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WanderlustConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            results = data.get("results", [])
            if not results:
                return {"error": f"No coordinates found for '{address}'.", "status": data.get("status")}

            first = results[0]
            loc = first.get("geometry", {}).get("location", {})
            return {
                "formatted_address": first.get("formatted_address"),
                "latitude": loc.get("lat"),
                "longitude": loc.get("lng"),
                "place_id": first.get("place_id"),
                "location_type": first.get("geometry", {}).get("location_type")
            }
    except Exception as e:
        return {"error": f"Geocoding request failed: {str(e)}", "address": address}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 1500.0,
    max_results: int = 5
) -> Dict[str, Any]:
    """Find nearby points of interest (restaurants, shopping, attractions, hotels) using Google Places API (New).

    Args:
        latitude: Center point latitude coordinate (e.g. 35.6580).
        longitude: Center point longitude coordinate (e.g. 139.7016).
        place_type: Type of place to search for (e.g. 'restaurant', 'tourist_attraction', 'shopping_mall', 'museum', 'hotel').
        radius_meters: Search radius in meters (default: 1500.0).
        max_results: Maximum number of places to return (default: 5).

    Returns:
        A list of nearby places with name, formatted address, location coordinates, rating, and google maps URI.
    """
    import os
    import urllib.request
    import json

    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {
            "error": "GOOGLE_MAPS_API_KEY is not configured or still set to placeholder in .env.",
            "latitude": latitude,
            "longitude": longitude
        }

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.types,places.googleMapsUri"
    }

    payload = {
        "includedTypes": [place_type],
        "maxResultCount": min(max_results, 10),
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": radius_meters
            }
        }
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            places_raw = data.get("places", [])
            places_clean = []
            for p in places_raw:
                display_name = p.get("displayName", {}).get("text", "Unknown")
                loc = p.get("location", {})
                places_clean.append({
                    "name": display_name,
                    "address": p.get("formattedAddress"),
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                    "rating": p.get("rating"),
                    "types": p.get("types", []),
                    "google_maps_url": p.get("googleMapsUri")
                })

            return {
                "center_location": {"latitude": latitude, "longitude": longitude},
                "place_type": place_type,
                "places_found": len(places_clean),
                "places": places_clean
            }
    except Exception as e:
        return {
            "error": f"Places Nearby Search failed: {str(e)}",
            "latitude": latitude,
            "longitude": longitude,
            "place_type": place_type
        }


async def generate_destination_postcard(
    destination_id: str,
    visual_theme: str = "vintage travel poster with landmark highlights",
    tool_context: ToolContext = None
) -> Dict[str, Any]:
    """Generate an artistic travel postcard image for a destination, save it as an artifact, and upload to public Cloud Storage.

    Args:
        destination_id: Destination ID or name (e.g. 'kyoto-japan', 'tokyo-japan', 'paris-france', 'amalfi-coast-italy').
        visual_theme: Desired artistic style or theme (e.g. 'vintage travel poster', 'golden hour watercolor', 'cyberpunk neon photography').

    Returns:
        A dictionary containing the destination name, public Cloud Storage URL, and artifact status.
    """
    import uuid
    import mimetypes

    dest = get_destination_details(destination_id)
    dest_name = dest.get("name", destination_id)
    attractions = ", ".join(dest.get("top_attractions", []))

    prompt = (
        f"A beautiful, high quality artistic travel postcard illustration of {dest_name}. "
        f"Featuring landmarks: {attractions}. Style: {visual_theme}."
    )

    try:
        # Initialize GenAI Client with vertexai=True and global region as required
        client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": "Image generation completed but no image bytes were returned."}

        # 1. Save artifact to ToolContext for the Playground's Artifacts panel
        artifact_filename = f"{destination_id}_postcard.jpg"
        if tool_context is not None:
            part = types.Part(inline_data=types.Blob(mime_type=mime_type, data=image_bytes))
            await tool_context.save_artifact(artifact_filename, part)

        # 2. Upload directly to Cloud Storage bucket without writing to local disk
        unique_id = uuid.uuid4().hex[:8]
        blob_name = f"postcards/{destination_id}_{unique_id}.jpg"
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob_name}"

        return {
            "destination": dest_name,
            "prompt": prompt,
            "artifact_saved": artifact_filename if tool_context is not None else "no_tool_context",
            "public_image_url": public_url,
            "status": "success"
        }
    except Exception as e:
        return {
            "error": f"Failed to generate postcard: {str(e)}",
            "destination": dest_name
        }


async def generate_destination_video(
    destination_id: str,
    visual_theme: str = "scenic cinematic aerial drone footage at golden hour",
    duration_seconds: int = 5,
    tool_context: ToolContext = None
) -> Dict[str, Any]:
    """Generate a short video for a travel destination using Google's Omni model (gemini-omni-flash-preview) in the global region.
    
    The generated video is saved as an artifact in tool_context and uploaded to public Cloud Storage, returning its public HTTPS URL.

    Args:
        destination_id: Destination ID or name (e.g. 'kyoto-japan', 'tokyo-japan', 'paris-france', 'amalfi-coast-italy').
        visual_theme: Theme or visual prompt for the short video (e.g. 'cinematic drone flight over landmarks at sunrise').
        duration_seconds: Length of the generated video in seconds (between 3 and 10 seconds, default 5).

    Returns:
        A dictionary containing destination info, prompt, public Cloud Storage video URL, and artifact status.
    """
    import asyncio
    import uuid
    import requests
    import google.auth
    import google.auth.transport.requests

    dest = get_destination_details(destination_id)
    dest_name = dest.get("name", destination_id)
    attractions = ", ".join(dest.get("top_attractions", []))

    duration_clamped = max(3, min(10, int(duration_seconds)))
    duration_str = f"{duration_clamped}s"

    prompt = (
        f"A cinematic high quality travel video of {dest_name}. "
        f"Highlights and landmarks: {attractions}. Style: {visual_theme}."
    )

    try:
        # 1. Obtain ADC credentials for Vertex AI global interactions endpoint
        creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        token = creds.token

        gcs_output_folder = f"gs://{GCS_BUCKET_NAME}/videos/"
        interactions_url = f"https://aiplatform.googleapis.com/v1beta1/projects/{FIRESTORE_PROJECT_ID}/locations/global/interactions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        body = {
            "model": "gemini-omni-flash-preview",
            "background": True,
            "input": [
                {
                    "type": "text",
                    "text": prompt
                }
            ],
            "response_format": [
                {
                    "type": "video",
                    "delivery": "uri",
                    "gcs_uri": gcs_output_folder,
                    "aspect_ratio": "16:9",
                    "duration": duration_str
                }
            ],
            "generation_config": {
                "video_config": {
                    "task": "text_to_video"
                }
            }
        }

        # 2. Start asynchronous video generation interaction
        create_resp = requests.post(interactions_url, headers=headers, json=body, timeout=30)
        if create_resp.status_code != 200:
            return {
                "error": f"Failed to start video generation interaction (HTTP {create_resp.status_code}): {create_resp.text}",
                "destination": dest_name
            }

        interaction_id = create_resp.json().get("id")
        if not interaction_id:
            return {"error": "No interaction ID returned from Omni model.", "destination": dest_name}

        poll_url = f"{interactions_url}/{interaction_id}"
        video_gcs_uri = None

        # 3. Poll interaction until completion (up to ~90s)
        for _ in range(30):
            await asyncio.sleep(3)
            poll_resp = requests.get(poll_url, headers=headers, timeout=20)
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                status = poll_data.get("status")
                if status == "completed":
                    steps = poll_data.get("steps", [])
                    for step in steps:
                        if step.get("type") == "model_output":
                            for content in step.get("content", []):
                                if content.get("type") == "video" and content.get("uri"):
                                    video_gcs_uri = content["uri"]
                                    break
                    break
                elif status == "failed":
                    return {"error": f"Omni video generation failed: {poll_data}", "destination": dest_name}

        if not video_gcs_uri:
            return {"error": "Timed out waiting for Omni video generation to complete.", "destination": dest_name}

        # Extract blob path from gs://<bucket>/<blob_name>
        prefix = f"gs://{GCS_BUCKET_NAME}/"
        if video_gcs_uri.startswith(prefix):
            blob_name = video_gcs_uri[len(prefix):]
        else:
            blob_name = video_gcs_uri.split("/", 3)[-1]

        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        video_bytes = blob.download_as_bytes()

        # (1) Save video artifact to ToolContext for the Playground's Artifacts panel
        artifact_filename = f"{destination_id}_video.mp4"
        if tool_context is not None:
            part = types.Part(inline_data=types.Blob(mime_type="video/mp4", data=video_bytes))
            await tool_context.save_artifact(artifact_filename, part)

        # (2) Construct and return public HTTPS Cloud Storage URL
        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob_name}"

        return {
            "destination": dest_name,
            "prompt": prompt,
            "duration": duration_str,
            "artifact_saved": artifact_filename if tool_context is not None else "no_tool_context",
            "public_video_url": public_url,
            "status": "success"
        }
    except Exception as e:
        return {
            "error": f"Failed to generate video with gemini-omni-flash-preview: {str(e)}",
            "destination": dest_name
        }


from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from .a2ui_utils import a2ui_callback

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description="""You are Wanderlust Concierge, an expert travel planning and local guide assistant.
You help travelers compose end-to-end trip plans like a professional travel agent: exploring curated destinations, checking live real-time weather, finding exact locations with Geocoding, discovering nearby attractions/restaurants/shopping with Google Places (New), generating day-by-day itineraries, generating custom travel postcards, estimating trip budgets, recommending matched hotels, and executing Python code in a safe sandbox for complex calculations or data transformations.

MEMORY & ALLERGY MANAGEMENT:
- You strictly remember and track all user allergies (e.g. food allergies like shellfish, peanuts, gluten, dairy; environmental/medication allergies), dietary restrictions, and personal preferences across all conversations via Vertex AI Memory Bank.
- Whenever a user mentions any allergy or dietary restriction, immediately acknowledge and remember it.
- When generating dining options, food recommendations, culinary market stops, or hotel amenities in itineraries, always cross-reference the user's remembered allergies and highlight safe dining alternatives or allergy warnings.

You have access to tools:
- Use `list_destinations` to find destinations matching traveler vibes, budgets, or interests (e.g. 'shopping', 'studio-tour', 'entertainment', 'culture', 'nature', 'foodie').
- Use `get_destination_details` to inspect full details, top attractions, recommended duration, and base costs.
- Use `get_destination_live_weather` to fetch live real-time weather forecast for any destination using the Open-Meteo public API.
- Use `geocode_address` to convert any landmark, district, or address into precise latitude/longitude coordinates via Google Geocoding API.
- Use `find_nearby_places` to find real-time nearby attractions, restaurants, shopping, or museums around coordinates via Google Places API (New).
- Use `generate_destination_postcard` to generate an artistic visual postcard of a destination and retrieve its public image URL.
- Use `generate_destination_video` to generate a short cinematic aerial drone travel video for any destination using Google's Omni model (gemini-omni-flash-preview) in the global region.
- Use `save_destination` when a user wants to add or update a destination in their travel catalog.
- Use `compose_itinerary` to generate a structured travel agent itinerary with morning/afternoon/evening plans, studio/entertainment highlights, nearby shopping stops, and dining.
- Use `calculate_trip_budget` to compute an itemized cost estimate by travel style, trip duration, number of travelers, and target currency.
- Use `recommend_hotels` to provide lodging options tailored to the traveler's budget tier, location preferences, and itinerary needs.""",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=f"projects/11339273979/locations/{LOCATION}/reasoningEngines/{MEMORY_BANK_ID}",
    ),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        list_destinations,
        get_destination_details,
        get_destination_live_weather,
        geocode_address,
        find_nearby_places,
        generate_destination_postcard,
        generate_destination_video,
        save_destination,
        compose_itinerary,
        calculate_trip_budget,
        recommend_hotels
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
