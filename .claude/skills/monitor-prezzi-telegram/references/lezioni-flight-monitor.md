# Lezioni dal progetto flight-monitor

Problemi reali incontrati costruendo il monitor voli da Napoli, in ordine cronologico, con la causa e la soluzione. Consultalo quando un sintomo ti sembra familiare.

| # | Sintomo | Causa | Soluzione |
|---|---|---|---|
| 1 | L'utente voleva "Skyscanner" | Nessuna API gratuita, scraping bloccato | Fonti alternative: Ryanair `farfnd` (tutte le destinazioni con una chiamata), Wizz API non ufficiale, Google Flights con `fast-flights`; più tardi SerpApi per gli hotel |
| 2 | Primo run: solo Ryanair, Wizz e Google falliti, log illeggibili | Log di Actions non scaricabili dalla sessione | `data/last_errors.txt` committato a ogni run + annotazioni `::notice::`/`::error::` |
| 3 | Wizz: 404 su `wizzair.com/buildnumber` | Endpoint della versione API spostato | Provare più URL; come ultima risorsa aprire il sito con Playwright e leggere la versione dalle richieste `be.wizzair.com/<ver>/Api` |
| 4 | Google Flights: `Invalid impersonate: chrome_126` | `primp` aggiornato e incompatibile con `fast-flights==2.2` | Fissare `primp==0.15.0` in `requirements.txt` |
| 5 | Offerta "economica" inutile: sabato 20:05 → domenica 06:00 | Il filtro guardava solo le date | Regole orarie in config: almeno 30 h sul posto, atterraggio del sabato entro le 14, ritorno della domenica dopo le 14; funzione unica `valid_trip` + `best_combos` (la combinazione valida più economica) |
| 6 | Ryanair availability → 409, Wizz search → 429 (anche da browser) | API di dettaglio protette | Fallback: tariffa minima con orari reali (Ryanair) e calendario con arrivo stimato (Wizz). Scriverlo in `last_errors.txt` e dirlo all'utente: si perdono le alternative con orari migliori |
| 7 | Messaggio Telegram da 200 righe | Ogni data era una riga | Una voce per destinazione, la data migliore + fino a 4 altre date elencate; il resto con `/voli <città>` |
| 8 | Città sconosciute (Skopje, Tirana) | Mancava il paese | Paese e bandiera da `countryCode` della fonte; per le liste statiche si aggiunge in config |
| 9 | "Venezia" e "Venezia (tutti gli aeroporti)" doppie | La mappa rotte Wizz contiene gruppi di aeroporti | Filtrare `isFakeStation` / "tutti gli aeroporti" |
| 10 | Troppe destinazioni italiane mescolate | Una sola lista | Messaggio separato per l'Italia (`ITALIAN_AIRPORTS`) |
| 11 | "Tolosa è sparita: si è rotto?" | Anti-spam: l'offerta era già stata notificata | Riepilogo del mattino con tutte le offerte valide, anche quelle già viste |
| 12 | Push dei dati fallito | Un run programmato e uno manuale sovrapposti; `checkout` partiva dal commit dell'evento | `checkout ref: main` + `git pull --rebase -X theirs` con 3 tentativi |
| 13 | Il bot non risponde | Sottodominio workers.dev appena creato / messaggi scartati da `drop_pending_updates` durante i deploy | Diagnosi con `getWebhookInfo` + richiesta simulata al Worker; risposta HTTP descrittiva del Worker |
| 14 | Deploy: "You need to register a workers.dev subdomain" | Account Cloudflare nuovo | `PUT /accounts/<id>/workers/subdomain` nel workflow |
| 15 | Token Cloudflare: "Choose a permission" | Creato come Custom Token senza scegliere i permessi | Usare il modello "Edit Cloudflare Workers" → Use template |
| 16 | La sessione non riesce a salvare i Secrets | Il proxy blocca `actions/secrets` | L'utente li aggiunge a mano; il workflow controlla che ci siano e lo dice con `::warning::` invece di fallire |
| 17 | A ogni deploy l'utente riceveva "Comandi" | Il test di deploy usava la chat vera | Test silenzioso con una chat non autorizzata |
| 18 | Barcellona mai nei pacchetti hotel | Si cercavano solo i 3 voli più economici | 1 posto fisso al più economico + 2 a rotazione tra i primi 10; `/pacchetto <città>` su richiesta con cache e riserva di ricerche |
| 19 | Hotel "catapecchia" e bagni in comune | Il prezzo più basso non garantisce la qualità | Filtri: hotel 3+ stelle con voto ≥ 4,0 e almeno 50 recensioni; appartamenti interi con voto ≥ 4,3; esclusi ostelli, camere private, "shared bathroom"; voto della posizione ≥ 3,5; testi richiesti in inglese (`hl=en`) per filtrare in modo affidabile |

## Numeri utili
- GitHub Actions: repo pubblico = minuti illimitati sui runner standard; privato = 2000 min/mese per account.
- Telegram: messaggi fino a 4096 caratteri (spezzare a circa 3900); HTML con `parse_mode: "HTML"`, fare l'escape di `& < > "`.
- Cloudflare Workers gratis: 100.000 richieste/giorno.
- SerpApi gratis: 100-250 ricerche/mese (verificare); l'Account API non consuma ricerche.
- Affiliazioni voli: circa 1-1,5% (non bastano per guadagnare); hotel 4-8%, esperienze, eSIM e assicurazioni 8-15%.
