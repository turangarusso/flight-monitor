import test from "node:test";
import assert from "node:assert/strict";
import worker, { findCities, groupCities, handle, parseCommand, fmtDay } from "./worker.js";

const offer = (dest, city, out, inn, price, extra = {}) => ({
  source: "ryanair", airline: "Ryanair", origin: "NAP", dest, dest_city: city,
  out_date: out, in_date: inn, price_pp: price, link: `https://x/${dest}/${out}`,
  out_dep: `${out}T10:00:00`, out_arr: `${out}T12:05:00`, in_dep: `${inn}T20:55:00`, in_arr: `${inn}T23:00:00`,
  country_code: "FR", country_name: "Francia", flag: "🇫🇷", ...extra,
});

const data = {
  updated: "2026-10-25T21:56:00Z",
  adults: 2,
  offers: [
    offer("TLS", "Tolosa", "2027-01-23", "2027-01-25", 56.27, {
      hotel: { kind: "hotel", name: "Hotel Ibis Styles", stars: 3, rating: 4.2, reviews: 800, total_eur: 150, link: "https://h" },
      apartment: { kind: "apartment", name: "Capitole Loft", stars: 0, rating: 4.8, reviews: 63, total_eur: 142, link: "https://a" },
    }),
    offer("TLS", "Tolosa", "2027-01-08", "2027-01-11", 59.98),
    offer("TLS", "Tolosa", "2027-01-22", "2027-01-25", 62.27),
    offer("BCN", "Barcellona", "2027-01-15", "2027-01-17", 29.99, { country_name: "Spagna", flag: "🇪🇸" }),
    offer("MXP", "Milano Malpensa", "2026-12-12", "2026-12-14", 30.98, { country_name: "Italia", flag: "🇮🇹" }),
    offer("BGY", "Milano Bergamo", "2026-12-12", "2026-12-14", 31.0, { country_name: "Italia", flag: "🇮🇹" }),
  ],
};

test("parseCommand", () => {
  assert.deepEqual(parseCommand("/voli Tolosa"), { cmd: "voli", arg: "Tolosa" });
  assert.deepEqual(parseCommand("/voli@MioBot  tolosa "), { cmd: "voli", arg: "tolosa" });
  assert.deepEqual(parseCommand("Tolosa"), { cmd: "voli", arg: "Tolosa" });
  assert.equal(fmtDay("2027-01-23"), "sab 23/01");
});

test("findCities: accenti, parziale, IATA, ambigua", () => {
  const cities = groupCities(data.offers);
  assert.equal(findCities(cities, "tolosa")[0].dest, "TLS");
  assert.equal(findCities(cities, "TOLÒSA")[0].dest, "TLS");
  assert.equal(findCities(cities, "tolo")[0].dest, "TLS");
  assert.equal(findCities(cities, "tls")[0].dest, "TLS");
  assert.equal(findCities(cities, "milano").length, 2);
  assert.equal(findCities(cities, "xyz").length, 0);
});

test("/voli Tolosa mostra tutte le date in ordine di data", () => {
  const [msg] = handle("/voli Tolosa", data);
  assert.match(msg, /Tolosa<\/b> 🇫🇷 Francia · 3 voli/);
  assert.ok(msg.indexOf("ven 08/01") < msg.indexOf("ven 22/01") && msg.indexOf("ven 22/01") < msg.indexOf("sab 23/01"));
  assert.match(msg, /sab 23\/01 10:00→12:05 · ritorno lun 25\/01 20:55 · 57 h sul posto/);
  assert.match(msg, /56 €<\/b> a testa \(113 € in 2\)/);
  assert.match(msg, /Prezzi aggiornati il/);
});

test("/voli ambiguo, senza argomento, /top, /paese, sconosciuto", () => {
  assert.match(handle("/voli milano", data)[0], /più città/);
  const list = handle("/voli", data)[0];
  assert.match(list, /Città con offerte \(4\)/);
  assert.ok(list.indexOf("Barcellona") < list.indexOf("Tolosa"));
  assert.match(list, /Tolosa \(Francia\) · da <b>56 €<\/b> · 3 date/);
  assert.equal((handle("/top", data)[0].match(/Prenota/g) || []).length, 6);
  assert.match(handle("/paese italia", data)[0], /Milano Malpensa/);
  assert.doesNotMatch(handle("/paese italia", data)[0], /Tolosa/);
  assert.match(handle("/voli Oslo", data)[0], /Nessun volo trovato/);
  assert.match(handle("/start", data)[0], /Comandi/);
});

test("webhook: segreto e chat autorizzate", async () => {
  const env = { WEBHOOK_SECRET: "s3cret", ALLOWED_CHAT_IDS: "530138459", TELEGRAM_BOT_TOKEN: "T", DATA_URL: "https://data" };
  const sent = [];
  globalThis.fetch = async (url, opts) => {
    if (url === "https://data") return new Response(JSON.stringify(data));
    sent.push(JSON.parse(opts.body));
    return new Response("{}");
  };
  const req = (secret, chatId) => new Request("https://bot", {
    method: "POST",
    headers: { "X-Telegram-Bot-Api-Secret-Token": secret },
    body: JSON.stringify({ message: { chat: { id: chatId }, text: "/voli tolosa" } }),
  });
  assert.equal((await worker.fetch(req("sbagliato", 530138459), env)).status, 403);
  assert.match(await (await worker.fetch(req("s3cret", 999), env)).text(), /non autorizzata/);
  assert.equal(sent.length, 0);                     // chat estranea: nessuna risposta
  assert.match(await (await worker.fetch(req("s3cret", 530138459), env)).text(), /inviati: ok/);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].chat_id, 530138459);
  assert.match(sent[0].text, /Tolosa/);
});

test("/pacchetti e alloggio in /voli", () => {
  const [msg] = handle("/pacchetti", data);
  assert.match(msg, /Pacchetti weekend/);
  assert.match(msg, /🏨 Hotel Ibis Styles ★★★ · 4,2\/5 \(800 recensioni\) · <b>150 €<\/b>/);
  assert.match(msg, /🏠 Appartamento Capitole Loft · 4,8\/5/);
  assert.match(msg, /Totale da <b>255 €<\/b> in 2/);
  assert.doesNotMatch(msg, /Barcellona/);
  assert.match(handle("/voli tolosa", data)[0], /Capitole Loft/);
  assert.match(handle("/pacchetti", { offers: [] })[0], /Nessun pacchetto/);
});
