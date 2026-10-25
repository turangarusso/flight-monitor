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
