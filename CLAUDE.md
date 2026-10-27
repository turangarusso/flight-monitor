# flight-monitor

Monitor gratuito di voli weekend low cost da Napoli (NAP), per 2 persone, con avvisi su Telegram, riepilogo del mattino, pacchetti volo + alloggio e un bot che risponde a comandi. Tutto in italiano (messaggi, commenti, commit).

Per creare progetti simili (altri monitor di prezzi con bot Telegram) c'è la skill `.claude/skills/monitor-prezzi-telegram/`.

## Architettura

```
GitHub Actions (monitor.yml, cron 3 volte al giorno, repo pubblico = minuti gratis)
  monitor.py
    sources/ryanair.py, wizzair.py, google_flights.py   -> list[Offer]  (models.py)
    combos.py      regole orarie (30 h sul posto, fasce), combinazione andata/ritorno
    alerts.py      filtro soglie + anti-spam (solo offerte nuove o scese di >= 3 €)
    packages.py    pacchetti volo + alloggio (sources/hotels.py, SerpApi Google Hotels)
    notify.py      messaggi Telegram (estero e Italia separati, riepilogo, pacchetti)
    storage.py     data/*
  -> commit di data/ su main

Cloudflare Worker (bot/worker.js + bot/hotels.js, deploy con bot.yml)
  webhook Telegram -> legge data/latest.json da raw.githubusercontent.com
  comandi: /voli /top /paese /pacchetti /pacchetto
```

## Dati (`data/`, committati dal workflow)
- `prices.csv`: storico di tutte le offerte trovate.
- `latest.json`: offerte valide attuali + `hotel_rules`; è la fonte dati del bot.
- `alerted.json`: stato con `offers` (anti-spam), `dest_min`, `failures`, `hotel_searches` (budget mensile SerpApi) e `package_history` (rotazione).
- `hotels_cache.json`: cache delle ricerche hotel (3 giorni).
- `last_errors.txt`: errori e avvisi dell'ultimo run. **È il modo per diagnosticare**: i log di Actions non sono scaricabili dalla sessione Claude.

## Comandi
```bash
pip install -r requirements.txt
python -m pytest -q                                         # test Python
cd bot && node --test                                       # test del bot
python monitor.py --dry-run --sources ryanair --digest      # stampa i messaggi, non invia e non salva
```

Lanciare un run vero e leggere il risultato (dalla sessione Claude):
```bash
gh api -X POST repos/turangarusso/flight-monitor/actions/workflows/monitor.yml/dispatches \
  -f ref=main -f 'inputs[sources]=ryanair' -F 'inputs[digest]=true'
gh api "repos/turangarusso/flight-monitor/actions/runs?per_page=1" --jq '.workflow_runs[0] | .id, .status, .conclusion'
# annotazioni (::notice:: / ::error::) di un job:
gh api repos/turangarusso/flight-monitor/check-runs/<job_id>/annotations --jq '.[].message'
git pull origin main && cat data/last_errors.txt
```

## Regole
- Il repo è **pubblico**: mai token, chat_id o chiavi nei file. I segreti stanno nei GitHub Secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SERPAPI_KEY`, `CLOUDFLARE_API_TOKEN`) e **li aggiunge l'utente**: la sessione non può scriverli.
- Ogni modifica va con test: fixture in `tests/fixtures/` (risposte reali semplificate), `tests/test_monitor.py` e `bot/*.test.mjs`.
- I filtri di qualità degli alloggi esistono in Python (`sources/hotels.py`) **e** in JS (`bot/hotels.js`): vanno tenuti allineati. Le soglie stanno in `config.yaml` → `hotels` e arrivano al bot tramite `latest.json`.
- Una fonte rotta non deve bloccare le altre: ogni `fetch()` solleva eccezioni, e `monitor.py` le isola e le conta.
- Le ricerche SerpApi sono limitate (piano gratuito): usare sempre cache e budget, e non aggiungere ricerche nei run delle 13 e delle 20.
- Prima di cambiare i workflow, ricordare che `checkout` usa `ref: main` e il push dei dati riprova con rebase: due run possono sovrapporsi.

## Insidie note
- Ryanair `booking/v4/availability` risponde **409**, Wizz `search/search` risponde **429** (anche da browser). Si usano i fallback: tariffa minima farfnd con orari reali, e calendario Wizz con arrivo stimato (+3 h).
- `fast-flights==2.2` funziona solo con `primp==0.15.0`; le versioni più nuove rifiutano `chrome_126`.
- La mappa rotte Wizz contiene gruppi tipo "Venezia (tutti gli aeroporti)": vanno filtrati.
- Dal container cloud non si raggiungono Ryanair, Wizz, Telegram, Cloudflare e SerpApi (proxy 403): si verifica sempre tramite un workflow e le sue annotazioni.
- Bot: il webhook usa `secret_token` = sha256("flight-monitor:" + token bot); risponde solo a `ALLOWED_CHAT_IDS`. Le operazioni lente (/pacchetto) girano in `ctx.waitUntil`.
- Il deploy del bot registra da solo il sottodominio workers.dev. Il token Cloudflare va creato con il modello "Edit Cloudflare Workers": un token personalizzato senza permessi fallisce.
