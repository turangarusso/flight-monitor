# Memoria del progetto: cosa abbiamo deciso e perché

Riassunto della conversazione che ha creato `flight-monitor`. Serve a riprendere il lavoro in una nuova sessione senza rifare le stesse domande. I dettagli tecnici sono in `CLAUDE.md`, la ricetta riutilizzabile è nella skill `.claude/skills/monitor-prezzi-telegram/`.

## Chi lo usa e cosa vuole
- Viaggia in **2 persone** da **Napoli (NAP)**, solo **weekend**: partenza ven/sab, ritorno dom/lun, 1-3 notti, nei prossimi 4 mesi.
- **Destinazioni**: ovunque. Italia ed estero vanno tenuti **separati**.
- **Budget volo A/R a persona**: 🔥 ≤ 40 €, 👍 40-65 € (vuole vedere anche questi).
- **Orari**: un volo economico con orari inutilizzabili non serve. Regole: almeno **30 h sul posto**, sabato atterraggio entro le 14, domenica ritorno dopo le 14. Venerdì sera va bene, lunedì nessun limite (gli è stato proposto di limitarlo, non ha ancora deciso).
- **Alloggio**: niente catapecchie e niente bagno in comune. Va bene un **appartamento intero** o un **hotel ≥ 3 stelle** con buone recensioni.
- **Costo totale: 0 €**, tutto automatico e schedulato.
- Parla italiano; preferisce spiegazioni semplici e passi uno alla volta, con link diretti.
- Vuole vedere **tutte le informazioni** nel messaggio: paese accanto alla città, tutte le date. Non frasi tipo "+N altre date".

## Cosa esiste (stato al 27/10/2026)
- **Repo pubblico** `turangarusso/flight-monitor` su GitHub. È pubblico perché così GitHub Actions non consuma i 2000 minuti mensili del piano gratuito, che servono ad altri suoi workflow.
- **Monitor** su GitHub Actions 3 volte al giorno. La mattina gira con tutte le fonti, manda il riepilogo e calcola i pacchetti.
- **Fonti voli**:
  - Ryanair: orari reali; la ricerca dettagliata è bloccata (409), quindi usa solo la tariffa più bassa del weekend.
  - Wizz Air: orario di partenza reale e arrivo stimato a +3 h; la ricerca dettagliata è bloccata (429).
  - Google Flights: 22 destinazioni in config, 1 volta al giorno.
- **Telegram**:
  - avvisi solo per offerte nuove o scese di ≥ 3 €;
  - riepilogo del mattino con tutte le offerte valide;
  - estero e Italia in messaggi separati;
  - una voce per città con paese e bandiera e fino a 4 altre date.
- **Pacchetti volo + alloggio**: Google Hotels via SerpApi (piano gratuito). Ogni mattina 1 pacchetto per il volo più economico + 2 a rotazione tra le 10 destinazioni più economiche. Budget di 90 ricerche al mese, cache di 3 giorni.
- **Bot con comandi** su Cloudflare Workers (`flight-monitor-bot.<sottodominio>.workers.dev`): `/voli <città>`, `/voli`, `/top`, `/paese <nome>`, `/pacchetti`, `/pacchetto <città> [gg/mm]`. Risponde solo alla sua chat.
- **Secrets su GitHub**, li ha aggiunti l'utente: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CLOUDFLARE_API_TOKEN`, `SERPAPI_KEY`.

## Decisioni prese (e alternative scartate)
| Decisione | Perché |
|---|---|
| Niente Skyscanner | Nessuna API gratuita, scraping bloccato e contro i termini d'uso |
| Ryanair + Wizz + Google Flights | Coprono quasi tutti i voli a 20-60 € da NAP, gratis |
| Telegram invece di email | Notifiche immediate sul telefono, gratis, e permette i comandi |
| GitHub Actions, repo pubblico | Gratis senza consumare i minuti del piano |
| Cloudflare Workers per i comandi | Serve un server sempre acceso; il piano gratuito basta |
| Riepilogo del mattino | L'utente pensava che il monitor fosse rotto quando Tolosa non veniva rinotificata (era l'anti-spam) |
| SerpApi per gli hotel | Booking, Airbnb ed Expedia non hanno API gratuite; Amadeus Self-Service sta chiudendo |
| Pacchetti a rotazione + `/pacchetto` su richiesta | Barcellona non usciva mai: erano solo i 3 voli più economici. L'utente ha chiesto la rotazione |
| CLAUDE.md + skill, non un agent | L'agent non conserva conoscenza; la skill è riutilizzabile per altri monitor |

## Cose aperte / da ricordare
- **Rigenerare il token Cloudflare** (Roll) e aggiornare il Secret: è passato in chat. Stesso discorso, se vuole, per il token del bot Telegram (BotFather → `/revoke`).
- **Ritorni del lunedì all'alba** (es. 05:55): decidere se impostare `inbound_depart_after.MON` in `config.yaml`.
- **SerpApi**: verificare se il piano gratuito dà 100 o 250 ricerche al mese. Con 250 si può alzare `hotels.monthly_budget` a ~240.
- **Ryanair availability (409)**: per ora si perdono i voli con orari migliori ma un po' più cari. Possibile tentativo futuro: richiesta dal browser automatico (Wizz però ha bloccato anche quello).
- **Skill**: il pulsante "Save skill" non compare. Gli è stato inviato lo zip da caricare in claude.ai → Impostazioni → Capabilities → Skills.
- **Idea Instagram**: è stato preparato un piano di marketing per una pagina di offerte voli. Punti chiave:
  - i voli sono l'esca, i guadagni arrivano da hotel/esperienze/eSIM/assicurazioni, sponsor e contenuti premium;
  - canale Telegram pubblico come strumento principale;
  - sponsor si cercano attivamente con un media kit.
  Possibili passi futuri: grafiche automatiche dal monitor, canale Telegram pubblico, più aeroporti di partenza.
