// Alloggi su richiesta (/pacchetto) tramite Google Hotels su SerpApi.
// Stessi filtri di qualità di sources/hotels.py; le soglie arrivano da
// latest.json ("hotel_rules", copiate da config.yaml).

const API = "https://serpapi.com/search.json";
const ACCOUNT_API = "https://serpapi.com/account.json"; // gratuita: non consuma ricerche
const CACHE_DAYS = 3;

const BAD_WORDS = [
  "hostel", "ostello", "dorm", "shared bathroom", "shared bath", "bagno in comune",
  "bagno condiviso", "capsule", "private room", "camera privata", "room in ", "shared room",
];

function text(p) {
  return [p.name, p.type, p.description, ...(p.amenities || []), ...(p.essential_info || [])]
    .filter(Boolean).join(" ").toLowerCase();
}

function total(p, nights) {
  const t = p.total_rate?.extracted_lowest;
  if (t) return Number(t);
  const n = p.rate_per_night?.extracted_lowest;
  return n ? Number(n) * nights : null;
}

function link(p, city) {
  return p.link || `https://www.google.com/travel/search?q=${encodeURIComponent(`${p.name || ""} ${city}`)}&hl=it`;
}

export function acceptable(p, kind, r = {}) {
  const t = text(p);
  if (BAD_WORDS.some((w) => t.includes(w))) return false;
  const rating = p.overall_rating || 0;
  const reviews = p.reviews || 0;
  if (p.location_rating != null && p.location_rating < (r.min_location_rating ?? 3.5)) return false;
  if (kind === "hotel") {
    return (p.extracted_hotel_class || 0) >= (r.min_stars ?? 3)
      && rating >= (r.min_hotel_rating ?? 4.0)
      && reviews >= (r.min_hotel_reviews ?? 50);
  }
  // appartamenti: deve essere l'alloggio intero, se Google lo specifica
  const info = (p.essential_info || []).join(" ").toLowerCase();
  if (info && !info.includes("entire")) return false;
  return rating >= (r.min_apartment_rating ?? 4.3) && reviews >= (r.min_apartment_reviews ?? 15);
}

export function pickBest(properties, kind, city, nights, r = {}) {
  let best = null;
  for (const p of properties || []) {
    const t = total(p, nights);
    if (!t || t > (r.max_total_eur ?? 250) || !acceptable(p, kind, r)) continue;
    if (!best || t < best.total_eur) {
      best = {
        kind,
        name: p.name || "?",
        stars: Number(p.extracted_hotel_class || 0),
        rating: Number(p.overall_rating || 0),
        reviews: Number(p.reviews || 0),
        total_eur: Math.round(t * 100) / 100,
        link: link(p, city),
      };
    }
  }
  return best;
}

export async function searchesLeft(env) {
  try {
    const r = await fetch(`${ACCOUNT_API}?api_key=${encodeURIComponent(env.SERPAPI_KEY)}`);
    if (!r.ok) return null;
    const left = (await r.json()).total_searches_left;
    return left == null ? null : Number(left);
  } catch {
    return null;
  }
}

function nightsBetween(checkIn, checkOut) {
  return Math.round((Date.parse(checkOut) - Date.parse(checkIn)) / 86400000);
}

// Ricerca con cache di 3 giorni (Cache API di Cloudflare). Restituisce {stay, cached}.
// Con cacheOnly=true non fa ricerche: restituisce null se il risultato non è in cache.
export async function searchStay(env, city, checkIn, checkOut, kind, rules, cache, cacheOnly = false) {
  const key = `https://cache.flight-monitor/${kind}/${encodeURIComponent(city.toLowerCase())}/${checkIn}/${checkOut}`;
  if (cache) {
    const hit = await cache.match(key);
    if (hit) return { stay: await hit.json(), cached: true };
  }
  if (cacheOnly) return null;
  const params = new URLSearchParams({
    engine: "google_hotels",
    q: city,
    check_in_date: checkIn,
    check_out_date: checkOut,
    adults: "2",
    currency: "EUR",
    gl: "it",
    hl: "en",
    sort_by: "3",
    rating: "8",
    api_key: env.SERPAPI_KEY,
  });
  if (kind === "hotel") params.set("hotel_class", "3,4,5");
  else params.set("vacation_rentals", "true");
  const r = await fetch(`${API}?${params}`);
  const data = await r.json();
  if (!r.ok || data.error) throw new Error(data.error || `SerpApi HTTP ${r.status}`);
  const stay = pickBest(data.properties, kind, city, nightsBetween(checkIn, checkOut), rules);
  if (cache) {
    await cache.put(key, new Response(JSON.stringify(stay), {
      headers: { "content-type": "application/json", "cache-control": `max-age=${CACHE_DAYS * 86400}` },
    }));
  }
  return { stay, cached: false };
}
