// Bot Telegram per consultare le offerte trovate dal monitor.
// Gira su Cloudflare Workers (gratis, sempre acceso) e legge data/latest.json
// dal repo GitHub pubblico.
//
// Comandi: /voli <città>, /voli, /top, /paese <nome>, /aiuto
// Scrivere solo il nome di una città equivale a /voli <città>.

const MAX_LEN = 3900; // limite Telegram 4096 caratteri
const DAYS = ["dom", "lun", "mar", "mer", "gio", "ven", "sab"];

export const HELP = [
  "✈️ <b>Comandi</b>",
  "",
  "/voli <i>città</i> – tutti i voli per una città (es. <code>/voli Tolosa</code>)",
  "/voli – elenco delle città con il prezzo minimo",
  "/top – le 10 offerte migliori di adesso",
  "/paese <i>nome</i> – tutte le città di un paese (es. <code>/paese Spagna</code>)",
  "/pacchetti – volo + hotel o appartamento di qualità (aggiornati ogni mattina)",
  "",
  "Puoi anche scrivere solo il nome della città.",
].join("\n");

export const COMMANDS = [
  { command: "voli", description: "Voli per una città (es. /voli Tolosa)" },
  { command: "top", description: "Le 10 offerte migliori di adesso" },
  { command: "paese", description: "Città di un paese (es. /paese Spagna)" },
  { command: "pacchetti", description: "Volo + hotel o appartamento" },
  { command: "aiuto", description: "Come si usa il bot" },
];

export function norm(s) {
  return (s || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

export function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// "2027-01-23" o "2027-01-23T10:00:00" -> "sab 23/01"
export function fmtDay(iso) {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${DAYS[wd]} ${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}`;
}

const hhmm = (iso) => (iso && iso.length >= 16 ? iso.slice(11, 16) : "");

function hoursAtDest(o) {
  if (!o.out_arr || !o.in_dep) return null;
  return Math.round((Date.parse(o.in_dep + "Z") - Date.parse(o.out_arr + "Z")) / 3600000);
}

export function parseCommand(text) {
  const t = (text || "").trim();
  if (!t.startsWith("/")) return { cmd: "voli", arg: t };
  const m = t.match(/^\/(\w+)(?:@\w+)?\s*(.*)$/s);
  return m ? { cmd: m[1].toLowerCase(), arg: m[2].trim() } : { cmd: "", arg: "" };
}

// Raggruppa le offerte per destinazione (IATA)
export function groupCities(offers) {
  const map = new Map();
  for (const o of offers) {
    if (!map.has(o.dest)) {
      map.set(o.dest, {
        dest: o.dest,
        city: o.dest_city,
        flag: o.flag || "",
        country: o.country_name || "",
        offers: [],
      });
    }
    map.get(o.dest).offers.push(o);
  }
  const cities = [...map.values()];
  for (const c of cities) c.offers.sort((a, b) => a.price_pp - b.price_pp || a.out_date.localeCompare(b.out_date));
  return cities.sort((a, b) => a.offers[0].price_pp - b.offers[0].price_pp);
}

// Città che corrispondono alla ricerca: codice IATA, nome esatto, poi nome parziale
export function findCities(cities, query) {
  const q = norm(query);
  if (!q) return [];
  const iata = cities.filter((c) => c.dest.toLowerCase() === q);
  if (iata.length) return iata;
  const exact = cities.filter((c) => norm(c.city) === q);
  if (exact.length) return exact;
  return cities.filter((c) => norm(c.city).includes(q) || norm(`${c.city} ${c.country}`).includes(q));
}

function cityTitle(c) {
  const country = [c.flag, c.country].filter(Boolean).join(" ");
  return `<b>${esc(c.city)}</b>${country ? " " + esc(country) : ""}`;
}

export function offerLine(o, adults) {
  const out = o.out_dep
    ? `${fmtDay(o.out_date)} ${hhmm(o.out_dep)}→${hhmm(o.out_arr)}`
    : fmtDay(o.out_date);
  const back = o.in_dep ? `${fmtDay(o.in_date)} ${hhmm(o.in_dep)}` : fmtDay(o.in_date);
  const h = hoursAtDest(o);
  return (
    `• ${out} · ritorno ${back}${h != null ? ` · ${h} h sul posto` : ""}\n` +
    `   <b>${Math.round(o.price_pp)} €</b> a testa (${Math.round(o.price_pp * adults)} € in ${adults}) · ` +
    `${esc(o.airline)} · <a href="${esc(o.link)}">Prenota</a>` +
    stays(o).map((st) => "\n" + stayLine(st)).join("") +
    (stays(o).length ? `\n   💶 Totale da <b>${Math.round(packageTotal(o, adults))} €</b> in ${adults}` : "")
  );
}

export function stayLine(st) {
  const icon = st.kind === "hotel" ? "🏨" : "🏠";
  const label = st.kind === "hotel" ? "" : "Appartamento ";
  const stars = st.stars ? " " + "★".repeat(st.stars) : "";
  const rating = st.rating.toFixed(1).replace(".", ",");
  return `   ${icon} ${label}${esc(st.name)}${stars} · ${rating}/5 (${st.reviews} recensioni) · ` +
    `<b>${Math.round(st.total_eur)} €</b> · <a href="${esc(st.link)}">Vedi</a>`;
}

function stays(o) {
  return [o.hotel, o.apartment].filter(Boolean);
}

// prezzo totale volo (per tutti) + alloggio più economico
export function packageTotal(o, adults) {
  const s = stays(o);
  if (!s.length) return null;
  return o.price_pp * adults + Math.min(...s.map((x) => x.total_eur));
}

export function split(lines) {
  const out = [];
  let cur = "";
  for (const line of lines) {
    if (cur.length + line.length + 1 > MAX_LEN) {
      out.push(cur);
      cur = "";
    }
    cur += line + "\n";
  }
  if (cur.trim()) out.push(cur);
  return out;
}

function updatedLine(data) {
  if (!data.updated) return "";
  const d = new Date(data.updated);
  const s = new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(d);
  return `<i>Prezzi aggiornati il ${s}. Possono cambiare: verifica sul sito.</i>`;
}

function listCities(cities, title) {
  const lines = [title, ""];
  for (const c of cities) {
    const n = c.offers.length;
    lines.push(`${c.flag} ${esc(c.city)}${c.country ? ` (${esc(c.country)})` : ""} · da <b>${Math.round(c.offers[0].price_pp)} €</b> · ${n} ${n === 1 ? "data" : "date"}`);
  }
  lines.push("", "Scrivi /voli seguito dal nome della città per vedere tutte le date.");
  return lines;
}

// Testo del comando -> lista di messaggi HTML da inviare
export function handle(text, data) {
  const { cmd, arg } = parseCommand(text);
  const adults = data.adults || 2;
  const cities = groupCities(data.offers || []);
  const footer = ["", updatedLine(data)];

  if (cmd === "start" || cmd === "aiuto" || cmd === "help") return [HELP];

  if (cmd === "top") {
    const best = [...(data.offers || [])].sort((a, b) => a.price_pp - b.price_pp).slice(0, 10);
    if (!best.length) return ["Nessuna offerta valida in questo momento."];
    const lines = ["🏆 <b>Le 10 offerte migliori</b>"];
    for (const o of best) {
      const c = cities.find((x) => x.dest === o.dest);
      lines.push("", cityTitle(c), offerLine(o, adults));
    }
    return split([...lines, ...footer]);
  }

  if (cmd === "pacchetti") {
    const pk = (data.offers || []).filter((o) => stays(o).length)
      .sort((a, b) => packageTotal(a, adults) - packageTotal(b, adults));
    if (!pk.length) {
      return ["Nessun pacchetto disponibile ora. I pacchetti volo + alloggio vengono calcolati ogni mattina."];
    }
    const lines = ["📦 <b>Pacchetti weekend (volo + dove dormire)</b>"];
    for (const o of pk) {
      const c = cities.find((x) => x.dest === o.dest);
      lines.push("", cityTitle(c), offerLine(o, adults));
    }
    return split([...lines, ...footer]);
  }

  if (cmd === "paese") {
    if (!arg) return ["Scrivi il paese, ad esempio <code>/paese Spagna</code>."];
    const q = norm(arg);
    const found = cities.filter((c) => norm(c.country).includes(q));
    if (!found.length) return [`Nessuna offerta per il paese "${esc(arg)}".`];
    return split([...listCities(found, `${found[0].flag} <b>${esc(found[0].country)}</b>`), ...footer]);
  }

  if (cmd === "voli") {
    if (!arg) {
      if (!cities.length) return ["Nessuna offerta valida in questo momento."];
      return split([...listCities(cities, `✈️ <b>Città con offerte (${cities.length})</b>`), ...footer]);
    }
    const found = findCities(cities, arg);
    if (!found.length) {
      return [`Nessun volo trovato per "${esc(arg)}". Scrivi /voli per vedere tutte le città disponibili.`];
    }
    if (found.length > 1) {
      return split(listCities(found, `Ho trovato più città per "${esc(arg)}":`));
    }
    const c = found[0];
    const offers = [...c.offers].sort((a, b) => a.out_date.localeCompare(b.out_date) || a.price_pp - b.price_pp);
    const lines = [`✈️ ${cityTitle(c)} · ${offers.length} ${offers.length === 1 ? "volo" : "voli"}`];
    for (const o of offers) lines.push("", offerLine(o, adults));
    return split([...lines, ...footer]);
  }

  return [HELP];
}

async function loadData(env) {
  const r = await fetch(env.DATA_URL, { cf: { cacheTtl: 60 } });
  if (!r.ok) throw new Error(`latest.json: HTTP ${r.status}`);
  return r.json();
}

async function send(env, chatId, text) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML", disable_web_page_preview: true }),
  });
  return r.ok ? "ok" : `HTTP ${r.status} ${(await r.text()).slice(0, 200)}`;
}

export function isAllowed(env, chatId) {
  const allowed = (env.ALLOWED_CHAT_IDS || "").split(",").map((s) => s.trim()).filter(Boolean);
  return allowed.includes(String(chatId));
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("flight-monitor bot");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const update = await request.json();
    const msg = update.message;
    // la risposta HTTP descrive cosa è successo (Telegram la ignora, serve per la diagnosi)
    if (!msg || !msg.text) return new Response("ignorato: nessun testo");
    // risponde solo alle chat autorizzate; agli altri non dice nulla
    if (!isAllowed(env, msg.chat.id)) {
      console.log(`chat ${msg.chat.id} non autorizzata`);
      return new Response(`ignorato: chat ${msg.chat.id} non autorizzata`);
    }
    const results = [];
    try {
      for (const text of handle(msg.text, await loadData(env))) results.push(await send(env, msg.chat.id, text));
    } catch (e) {
      results.push(`errore: ${e.message}`);
      results.push(await send(env, msg.chat.id, `⚠️ Non riesco a leggere le offerte (${esc(e.message)}). Riprova tra poco.`));
    }
    console.log(results.join(" | "));
    return new Response(`inviati: ${results.join(" | ")}`);
  },
};
