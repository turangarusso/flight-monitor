# ✈️ Flight monitor Napoli

Controlla in automatico i voli A/R da Napoli (NAP) per i weekend (partenza ven/sab, ritorno dom/lun) verso **qualsiasi destinazione** e ti avvisa su Telegram:

- 🔥 **Super offerte**: ≤ 40 € A/R a persona
- 👍 **Buone offerte**: 40–65 € A/R a persona

Fonti: **Ryanair** (tutte le destinazioni), **Wizz Air** (tutte le rotte da NAP), **Google Flights** (easyJet, Volotea, ITA…, su una lista di destinazioni in `config.yaml`).
Gira gratis su GitHub Actions 3 volte al giorno. Lo storico prezzi viene salvato in `data/prices.csv`.

Scarta i weekend con orari inutilizzabili: almeno **30 ore a destinazione**, andata del sabato che atterra entro le 14, ritorno della domenica che parte dopo le 14 (tutto modificabile in `config.yaml` → `time_rules`). Se il volo più economico ha orari brutti, cerca gli altri voli dello stesso giorno.

Le offerte in **Italia** arrivano in un messaggio separato da quelle all'**estero**. Ogni destinazione occupa una sola riga (la data più economica, con "+N altre date").

Se una fonte non funziona, l'errore viene salvato in `data/last_errors.txt`.

Ogni mattina arriva anche un **riepilogo** con le migliori offerte ancora valide, comprese quelle già notificate.

Gli avvisi durante il giorno arrivano solo per offerte **nuove**, **scese di almeno 3 €** o al **minimo storico** di una destinazione, quindi non riceve duplicati.

## Setup (5 minuti)

1. **Bot Telegram**
   - Su Telegram scrivi a `@BotFather`, invia `/newbot` e copia il **token**.
   - Manda un messaggio qualsiasi al tuo bot, poi apri `https://api.telegram.org/bot<TOKEN>/getUpdates` e copia `"chat":{"id": ...}`: è il **chat_id**.
     (Per avvisare anche chi viaggia con te: crea un gruppo Telegram con quella persona e il bot, e usa il chat_id del gruppo, che inizia con `-`.)
2. **Repo GitHub pubblico** (nei repo pubblici GitHub Actions non consuma i 2000 minuti del tuo piano)
   - Crea un repo pubblico, per esempio `flight-monitor`, e carica questi file.
   - *Settings → Secrets and variables → Actions → New repository secret*: aggiungi `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
3. **Test**: tab *Actions → Monitor voli → Run workflow*.

## Comandi del bot (opzionale, gratis con Cloudflare)

Scrivendo al bot puoi consultare tutte le offerte in qualsiasi momento:

- `/voli Tolosa` (o solo `Tolosa`): tutti i voli per quella città
- `/voli`: elenco delle città con il prezzo minimo
- `/top`: le 10 offerte migliori
- `/paese Spagna`: tutte le città di un paese
- `/pacchetti`: i pacchetti volo + alloggio di stamattina
- `/pacchetto Barcellona` (o `/pacchetto Barcellona 23/01`): cerca subito hotel e appartamento per quella città

Il bot gira su Cloudflare Workers (gratis) e legge `data/latest.json`. Setup una tantum:

1. Crea un account gratuito su https://dash.cloudflare.com e apri **Workers & Pages** una volta, per attivare il sottodominio `workers.dev`.
2. *My Profile → API Tokens → Create Token*, modello **Edit Cloudflare Workers** → copia il token.
3. Nel repo, *Settings → Secrets → Actions*: aggiungi `CLOUDFLARE_API_TOKEN` (l'Account ID viene ricavato in automatico).
4. *Actions → Bot Telegram → Run workflow*. Pubblica il bot, lo collega a Telegram e imposta il menu dei comandi.

Il bot risponde solo alla chat di `TELEGRAM_CHAT_ID`.

## Pacchetti volo + alloggio (opzionale, gratis con SerpApi)

Ogni mattina il monitor cerca su **Google Hotels** l'alloggio per 3 offerte all'estero: il volo più economico più 2 destinazioni **a rotazione** tra le 10 più economiche, così in pochi giorni tutte ricevono un pacchetto. Con `/pacchetto <città>` il bot cerca subito per la città che vuoi, tenendo sempre una riserva di ricerche per il mattino.

Per ogni offerta cerca:
- 🏨 il **hotel più economico di almeno 3 stelle** con voto ≥ 4,0/5 e almeno 50 recensioni;
- 🏠 l'**appartamento intero più economico** con voto ≥ 4,3/5 e almeno 15 recensioni.

Scarta ostelli, camere private, bagni in comune e zone con voto della posizione basso. Nel riepilogo arriva la sezione "📦 Pacchetti weekend" con il totale volo + alloggio, e il bot ha il comando `/pacchetti`.

Setup:
1. Iscriviti gratis su https://serpapi.com (piano Free, 100-250 ricerche al mese).
2. Copia la tua **API key** da https://serpapi.com/manage-api-key
3. Aggiungila nei Secrets del repo come `SERPAPI_KEY`.

Il monitor usa al massimo 90 ricerche al mese (`hotels.monthly_budget` in `config.yaml`) e non ripete la stessa ricerca per 3 giorni. Senza la chiave tutto il resto funziona come prima.

## Personalizzare

Modifica `config.yaml`: soglie di prezzo, mesi in avanti, giorni della settimana, notti, destinazioni Google Flights, oppure disattiva una fonte con `enabled: false`.

## Uso locale

```bash
pip install -r requirements.txt
python -m playwright install chromium     # serve solo per il fallback Wizz Air
python monitor.py --dry-run               # stampa il messaggio, senza inviare né salvare
python monitor.py --dry-run --sources wizzair
python -m pytest -q
```

## Note

- Sono API **non ufficiali** e scraping, per uso personale e a bassa frequenza. Se una compagnia cambia qualcosa, quella fonte smette di funzionare ma le altre continuano: dopo 3 run falliti di fila ricevi un ⚠️ su Telegram.
- I prezzi sono le tariffe base (senza bagaglio grande né posto scelto). Verifica sempre sul sito che ci siano **2 posti** a quel prezzo.
- GitHub sospende i workflow schedulati dopo 60 giorni senza commit: il commit automatico dello storico prezzi lo tiene attivo.

## Per sviluppatori (e per Claude)

- `CLAUDE.md`: mappa del codice, comandi, regole e insidie note di questo progetto. Claude Code lo legge in automatico.
- `.claude/skills/monitor-prezzi-telegram/`: skill riutilizzabile per costruire monitor di prezzi simili (avvisi Telegram, bot con comandi, tutto gratis). Funziona quando apri questo repo con Claude Code. Per averla in tutti i progetti, copia la cartella in `~/.claude/skills/`; per claude.ai, comprimila in zip e caricala da *Impostazioni → Capabilities → Skills*.
