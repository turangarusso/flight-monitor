// Scheletro di bot Telegram su Cloudflare Workers.
// Legge i dati pubblicati dal monitor (DATA_URL = data/latest.json su GitHub)
// e risponde ai comandi. Sostituisci {{...}} e completa handle().
//
// Secret (impostati da bot.yml): TELEGRAM_BOT_TOKEN, WEBHOOK_SECRET, ALLOWED_CHAT_IDS

const MAX_LEN = 3900; // limite Telegram: 4096 caratteri

export const COMMANDS = [
  // compaiono nel menu "/" di Telegram (impostati da bot.yml con setMyCommands)
  { command: "{{COMANDO}}", description: "{{DESCRIZIONE_COMANDO}}" },
  { command: "aiuto", description: "Come si usa il bot" },
];

export const HELP = "{{TESTO_AIUTO}}";

export function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ricerca tollerante: senza maiuscole, accenti e spazi doppi
export function norm(s) {
  return (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
}

export function parseCommand(text) {
  const t = (text || "").trim();
  if (!t.startsWith("/")) return { cmd: "{{COMANDO}}", arg: t }; // testo libero = comando principale
  const m = t.match(/^\/(\w+)(?:@\w+)?\s*(.*)$/s);
  return m ? { cmd: m[1].toLowerCase(), arg: m[2].trim() } : { cmd: "", arg: "" };
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

// Testo del messaggio -> lista di risposte.
// Una risposta è una stringa HTML, oppure un oggetto {async: ...} per operazioni lente
// (chiamate ad API esterne) eseguite in background con ctx.waitUntil.
export function handle(text, data) {
  const { cmd, arg } = parseCommand(text);
  if (cmd === "start" || cmd === "aiuto" || cmd === "help") return [HELP];
  if (cmd === "{{COMANDO}}") {
    // adatta i campi (name, price, link) a quelli scritti da storage.write_latest
    const items = (data.items || []).filter((x) => !arg || norm(x.name).includes(norm(arg)));
    if (!items.length) return [`Nessun risultato per "${esc(arg)}".`];
    return split(items.map((x) => `• ${esc(x.name)} · <b>${Math.round(x.price)} €</b> · <a href="${esc(x.link)}">Apri</a>`));
  }
  return [HELP];
}

// operazioni lente (es. ricerca su un'API esterna): restituisce il testo da inviare
export async function runAsync(env, action) {
  return `TODO: ${esc(action.async)}`;
}

async function loadData(env) {
  const r = await fetch(env.DATA_URL, { cf: { cacheTtl: 60 } });
  if (!r.ok) throw new Error(`dati: HTTP ${r.status}`);
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
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("{{NOME_WORKER}}");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const msg = (await request.json()).message;
    // la risposta HTTP descrive cosa è successo: Telegram la ignora, serve per la diagnosi
    if (!msg || !msg.text) return new Response("ignorato: nessun testo");
    if (!isAllowed(env, msg.chat.id)) return new Response(`ignorato: chat ${msg.chat.id} non autorizzata`);
    const results = [];
    try {
      for (const item of handle(msg.text, await loadData(env))) {
        if (typeof item === "string") {
          results.push(await send(env, msg.chat.id, item));
          continue;
        }
        const job = runAsync(env, item)
          .catch((e) => `⚠️ Operazione non riuscita (${esc(e.message)}).`)
          .then((text) => send(env, msg.chat.id, text));
        if (ctx?.waitUntil) ctx.waitUntil(job); // si risponde subito a Telegram
        else await job;
        results.push("in background");
      }
    } catch (e) {
      results.push(`errore: ${e.message}`);
      results.push(await send(env, msg.chat.id, `⚠️ Non riesco a leggere i dati (${esc(e.message)}).`));
    }
    return new Response(`inviati: ${results.join(" | ")}`);
  },
};
