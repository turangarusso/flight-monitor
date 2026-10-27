import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pickBest, searchStay } from "./hotels.js";
import worker, { handle, runPackage } from "./worker.js";

const fixture = (name) => JSON.parse(readFileSync(new URL(`../tests/fixtures/${name}`, import.meta.url)));
const hotels = fixture("serpapi_hotels_sample.json");
const rentals = fixture("serpapi_rentals_sample.json");
const rules = { min_stars: 3, min_hotel_rating: 4.0, min_hotel_reviews: 50, min_apartment_rating: 4.3,
  min_apartment_reviews: 15, min_location_rating: 3.5, max_total_eur: 250 };

// stessi risultati dei test Python
test("filtri di qualità come in Python", () => {
  const h = pickBest(hotels.properties, "hotel", "Tolosa", 2, rules);
  assert.deepEqual([h.name, h.stars, h.total_eur], ["Hotel Ibis Styles", 3, 150]);
  const a = pickBest(rentals.properties, "apartment", "Tolosa", 2, rules);
  assert.deepEqual([a.name, a.rating, a.total_eur], ["Capitole Loft", 4.8, 142]);
});

function memoryCache() {
  const m = new Map();
  return { match: async (k) => (m.has(k) ? new Response(m.get(k)) : undefined), put: async (k, r) => m.set(k, await r.text()) };
}

function mockFetch(left = 100) {
  const calls = [];
  globalThis.fetch = async (url) => {
    const u = String(url);
    calls.push(u);
    if (u.includes("account.json")) return new Response(JSON.stringify({ total_searches_left: left }));
    return new Response(JSON.stringify(u.includes("vacation_rentals") ? rentals : hotels));
  };
  return calls;
}

const offer = { dest: "BCN", dest_city: "Barcellona", out_date: "2027-02-26", in_date: "2027-02-28", price_pp: 48.98,
  airline: "Ryanair", link: "https://f", out_dep: "2027-02-26T09:00:00", out_arr: "2027-02-26T11:00:00",
  in_dep: "2027-02-28T19:00:00", country_name: "Spagna", flag: "🇪🇸" };
const data = { adults: 2, hotel_rules: rules, offers: [offer, { ...offer, out_date: "2027-01-22", in_date: "2027-01-24", price_pp: 55 }] };

test("/pacchetto sceglie il volo più economico o quello della data", () => {
  const [msg, action] = handle("/pacchetto barcellona", data);
  assert.match(msg, /Cerco hotel e appartamenti a <b>Barcellona<\/b> per ven 26\/02 → dom 28\/02/);
  assert.equal(action.offer.price_pp, 48.98);
  assert.equal(handle("/pacchetto Barcellona 22/01", data)[1].offer.price_pp, 55);
  assert.match(handle("/pacchetto Barcellona 01/03", data)[0], /Date disponibili: ven 22\/01, ven 26\/02/);
  assert.match(handle("/pacchetto", data)[0], /Scrivi la città/);
});

test("runPackage: ricerca, poi cache senza nuove ricerche", async () => {
  const env = { SERPAPI_KEY: "k" };
  const cache = memoryCache();
  const action = handle("/pacchetto barcellona", data)[1];
  let calls = mockFetch();
  const msg = await runPackage(env, action, cache);
  assert.match(msg, /🏨 Hotel Ibis Styles ★★★ · 4,2\/5/);
  assert.match(msg, /🏠 Appartamento Capitole Loft/);
  assert.match(msg, /Totale da <b>240 €<\/b> in 2/);
  assert.equal(calls.filter((u) => u.includes("search.json")).length, 2);
  calls = mockFetch();
  await runPackage(env, action, cache);
  assert.equal(calls.length, 0); // tutto dalla cache, nemmeno l'account API
});

test("runPackage: riserva per i pacchetti del mattino", async () => {
  mockFetch(21);
  const msg = await runPackage({ SERPAPI_KEY: "k", HOTEL_RESERVE: "20" }, handle("/pacchetto barcellona", data)[1], memoryCache());
  assert.match(msg, /finite per questo mese \(ne restano 21/);
  assert.match(await runPackage({}, handle("/pacchetto barcellona", data)[1], null), /non configurata/);
});

test("offerta con alloggio già calcolato: nessuna ricerca", () => {
  const withStay = { ...data, offers: [{ ...offer, hotel: { kind: "hotel", name: "H", stars: 4, rating: 4.5, reviews: 99, total_eur: 120, link: "x" } }] };
  const out = handle("/pacchetto barcellona", withStay);
  assert.equal(out.length, 1);
  assert.match(out[0], /🏨 H ★★★★/);
});

test("webhook: risponde subito e cerca in background", async () => {
  const sent = [];
  globalThis.fetch = async (url, opts) => {
    const u = String(url);
    if (u === "https://data") return new Response(JSON.stringify(data));
    if (u.includes("account.json")) return new Response(JSON.stringify({ total_searches_left: 100 }));
    if (u.includes("serpapi")) return new Response(JSON.stringify(u.includes("vacation_rentals") ? rentals : hotels));
    sent.push(JSON.parse(opts.body).text);
    return new Response("{}");
  };
  const jobs = [];
  const env = { WEBHOOK_SECRET: "s", ALLOWED_CHAT_IDS: "1", TELEGRAM_BOT_TOKEN: "T", DATA_URL: "https://data", SERPAPI_KEY: "k" };
  const res = await worker.fetch(new Request("https://bot", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": "s" },
    body: JSON.stringify({ message: { chat: { id: 1 }, text: "/pacchetto barcellona" } }),
  }), env, { waitUntil: (p) => jobs.push(p) });
  assert.match(await res.text(), /pacchetto in background/);
  assert.equal(sent.length, 1);            // "Cerco…" inviato subito
  await Promise.all(jobs);
  assert.equal(sent.length, 2);
  assert.match(sent[1], /Capitole Loft/);
});
