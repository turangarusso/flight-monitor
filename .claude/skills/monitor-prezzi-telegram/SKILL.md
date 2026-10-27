---
name: monitor-prezzi-telegram
description: Costruisce un monitor di prezzi gratuito e automatico (voli, hotel, prodotti, biglietti, affitti, qualsiasi cosa con un prezzo che cambia) che gira da solo su GitHub Actions, salva lo storico, avvisa su Telegram quando trova offerte e ha un bot Telegram che risponde a comandi (es. /voli Tolosa) tramite Cloudflare Workers. Usala ogni volta che l'utente vuole "tenere d'occhio" o "monitorare" prezzi o disponibilità, ricevere notifiche/avvisi su Telegram, fare uno scraper schedulato, un bot Telegram con comandi, oppure automatizzare qualcosa "gratis" e "senza server", anche se non nomina GitHub, Telegram o Cloudflare.
---

# Monitor di prezzi con avvisi e bot Telegram (costo 0 €)

Questa skill raccoglie l'architettura e le lezioni del progetto `flight-monitor`. Quel progetto cerca voli weekend low cost da Napoli, applica filtri di orario e qualità, invia avvisi e riepiloghi su Telegram, propone pacchetti volo + hotel e risponde a comandi.

Lo schema vale per qualsiasi prezzo che cambia nel tempo. Riusalo invece di reinventarlo: ogni pezzo esiste perché senza ci siamo fatti male.

## 1. Chiarire prima di scrivere codice

Chiedi all'utente (meglio con domande a scelta multipla):
- **Cosa** monitorare e **da dove**: sito, città di partenza, prodotto.
- **Soglie**: prezzo massimo, eventualmente in più fasce ("super offerta" ≤ X, "buona" ≤ Y).
- **Vincoli di qualità** che un prezzo basso da solo non garantisce. Esempi: orari utilizzabili (non partire sabato alle 20 e tornare domenica alle 6), hotel non catapecchia, niente bagno in comune.
- **Frequenza** (di solito 2-3 volte al giorno) e **canale di avviso** (Telegram consigliato).
- **Budget**: di solito 0 €, quindi solo servizi gratuiti.

Un vincolo scoperto tardi costa un giro di modifiche. Chiedi esplicitamente: "cosa renderebbe inutile un'offerta anche se costa poco?"

## 2. Scegliere la fonte dei dati

In ordine di preferenza:
1. **API ufficiale gratuita** del sito.
2. **API non ufficiale** usata dal sito stesso (si trova con gli strumenti di rete del browser). Esempi: Ryanair `farfnd`, Wizz `be.wizzair.com/<versione>/Api`.
3. **Libreria di scraping** mantenuta (es. `fast-flights` per Google Flights). Fissa la versione, comprese le dipendenze.
4. **Servizio con piano gratuito** (es. SerpApi per Google Hotels: 100-250 ricerche al mese).

Regole pratiche:
- Bassa frequenza e pause tra le richieste, per non farsi bloccare. Rispetta i termini d'uso: niente login automatici e niente aggiramento di captcha.
- Alcuni siti danno **API di dettaglio protette** (409/429 anche dal browser). Prevedi sempre un **fallback** con i dati meno precisi ma disponibili, e scrivilo nei log.
- Skyscanner, Booking, Airbnb ed Expedia non hanno API gratuite e bloccano lo scraping: dillo subito all'utente e proponi un'alternativa.

## 3. Architettura standard (tutta gratuita)

```
GitHub Actions (cron, repo PUBBLICO → minuti illimitati)
  monitor.py → sources/* → filtri → anti-spam → notify (Telegram)
             → data/ (storico CSV, latest.json, stato) committati su main
Cloudflare Worker (webhook Telegram, sempre acceso)
  legge data/latest.json da raw.githubusercontent.com → risponde ai comandi
```

- Usa un **repo pubblico**: i 2000 minuti al mese di GitHub sono per account e condivisi tra i repo privati, mentre nei repo pubblici i minuti sono illimitati. I segreti restano nei Secrets, e nei file pubblici finiscono solo codice e prezzi.
- Il bot gira su **Cloudflare Workers** perché GitHub Actions non può ricevere messaggi in tempo reale. In alternativa lascia solo gli avvisi, senza comandi.

Parti dai modelli in `assets/templates/` (sostituisci i `{{SEGNAPOSTO}}`):
- `monitor.yml`: cron, concurrency, push dei dati con retry;
- `bot.yml`: deploy del Worker, sottodominio, webhook, comandi, test silenzioso;
- `worker.js`: scheletro del bot (webhook, autorizzazione, comandi, `waitUntil`);
- `wrangler.toml`;
- `notify.py`: invio Telegram con messaggi spezzati sotto i 4096 caratteri;
- `storage.py`: stato, `latest.json`, `last_errors.txt`.

## 4. Struttura del codice

- `sources/<fonte>.py` con una funzione `fetch(cfg) -> list[Offer]`. Ogni fonte **solleva eccezioni**; `monitor.py` le isola, conta i fallimenti consecutivi e avvisa su Telegram solo dopo N run falliti, così una fonte rotta non blocca le altre.
- Un **modello comune** (`dataclass Offer`) con una `key` stabile, per esempio compagnia + destinazione + date.
- **Filtri** separati dalle fonti, testabili da soli (es. `combos.py` per le regole orarie).
- **Anti-spam con stato** (`data/alerted.json`): avvisa solo per offerte nuove, scese di almeno X € o al minimo storico.
- Aggiungi subito un **riepilogo** periodico con le offerte ancora valide. Senza riepilogo l'utente pensa che il monitor sia rotto quando un'offerta già notificata "sparisce".
- Nei messaggi:
  - una riga per elemento, con le **altre date elencate** (mai "+N altre date" senza mostrarle);
  - contesto utile come paese e bandiera accanto alla città;
  - sezioni separate per categorie diverse (es. Italia ed estero).
- `config.yaml` per tutte le soglie, perché l'utente le cambierà.
- `data/latest.json` con le offerte valide di **tutte** le fonti: se una fonte non ha girato in quel run, tieni le sue offerte precedenti. È ciò che legge il bot.

## 5. Affidabilità (lezioni pagate care)

- `actions/checkout` con **`ref: main`**: senza, il run parte dal commit dell'evento e il push dei dati va in conflitto.
- Usa **`concurrency`** e un push con `git pull --rebase -X theirs` e 3 tentativi.
- Usa un **minuto "storto" nel cron** (es. `17 5 * * *`), non `0`: i cron allo scoccare dell'ora arrivano con molto ritardo.
- Scrivi **`data/last_errors.txt`** a ogni run con errori e avvisi delle fonti (fallback attivati, 429…). Usa anche annotazioni `::notice::`/`::error::` nei workflow. Claude spesso **non può scaricare i log di Actions**, ma può leggere i file del repo e le annotazioni con `gh api .../check-runs/<job>/annotations`.
- GitHub sospende i cron dopo 60 giorni senza attività: il commit automatico dei dati lo evita.
- Fissa le versioni delle librerie di scraping e delle loro dipendenze (es. `fast-flights==2.2` richiede `primp==0.15.0`).

## 6. Bot Telegram su Cloudflare Workers

- **Webhook** con `secret_token`. Ricavalo dal token del bot (`sha256("<progetto>:" + token)`) nel workflow, così l'utente non deve creare un secret in più.
- Usa **`ALLOWED_CHAT_IDS`** e non rispondere agli estranei.
- Per operazioni lente (chiamate a servizi esterni) rispondi subito "🔎 Cerco…" e continua in **`ctx.waitUntil`**. Telegram altrimenti potrebbe rimandare il messaggio.
- Il deploy si fa da workflow con `npx wrangler@3 deploy` + `wrangler secret put`. Se l'account non ha un sottodominio workers.dev, **registralo via API** (`PUT /accounts/<id>/workers/subdomain`). Ricava l'Account ID dal token (`GET /accounts`).
- Imposta `setMyCommands` (menu "/") e `setWebhook` con `drop_pending_updates`.
- Per verificare il deploy usa un **test silenzioso**: un POST al Worker da una chat non autorizzata deve rispondere "non autorizzata". Un test con la chat vera scriverebbe all'utente a ogni deploy.
- La risposta HTTP del Worker descrive cosa è successo (Telegram la ignora): rende possibile la diagnosi.
- Scrivendo solo il nome ("Tolosa") il bot dovrebbe capire. La ricerca ignora maiuscole e accenti, accetta nomi parziali e codici.

## 7. Servizi a quota gratuita (es. SerpApi)

- Usa una **cache** (file in `data/` per il monitor, Cache API per il Worker) di qualche giorno.
- Tieni un **budget mensile** nello stato e leggi le ricerche rimaste con l'**Account API**, che non consuma ricerche. Il bot su richiesta lascia una **riserva** per i run automatici.
- Spendi le ricerche dove servono: 1 posto fisso al migliore + posti **a rotazione** tra i successivi (chi non è mai stato proposto ha la precedenza). Così non escono sempre le stesse destinazioni.
- Se la stessa logica di filtro esiste in Python e in JS, passa le soglie al bot dentro `latest.json` e tieni i test di entrambe sulle **stesse fixture**.

## 8. Test

- **Fixture** con risposte reali semplificate in `tests/fixtures/`. Includi i casi limite che contano: il volo con orari pessimi, l'ostello, il bagno in comune, il prezzo in valuta estera.
- `pytest` per Python e `node --test` per il Worker, con `fetch` simulato (`globalThis.fetch = async (url) => ...`).
- Il container di Claude spesso non raggiunge i siti esterni (proxy). La verifica vera si fa lanciando il workflow (`gh api -X POST .../dispatches`), aspettando la fine e leggendo `data/` e le annotazioni.

## 9. Cosa deve fare l'utente (Claude non può)

Guidalo passo passo, una cosa alla volta, con link diretti:
1. **Bot Telegram**: @BotFather → `/newbot` → token. Scrivere "ciao" al **proprio** bot (non a BotFather), poi aprire `https://api.telegram.org/bot<TOKEN>/getUpdates` e prendere `chat.id`. Se compare `"result":[]`, non ha ancora scritto al bot.
2. **Repo pubblico** su GitHub. Se la sessione non può creare repo, l'utente crea un repo vuoto e Claude lo collega e fa il push.
3. **Secrets** (*Settings → Secrets and variables → Actions → Repository secrets*): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, eventuali chiavi API. La sessione di solito **non può scriverli**: chiedili all'utente e verifica dopo con un run (un workflow che dice "manca il secret" vuol dire nome sbagliato o sezione sbagliata).
4. **Cloudflare**: account gratuito → *API Tokens → Create Token* → modello **"Edit Cloudflare Workers"** → **Use template**. Un "Custom Token" senza permessi scelti fallisce ("Choose a permission").
5. Se un token passa in chat, consiglia di rigenerarlo (Roll) dopo la configurazione.

## 10. Checklist finale

- [ ] Run manuale verde e messaggio di prova arrivato su Telegram.
- [ ] `data/last_errors.txt` senza errori, oppure solo fallback noti spiegati all'utente.
- [ ] Secondo run: nessun avviso duplicato.
- [ ] Bot: `/aiuto` e un comando reale funzionano; il workflow del bot è verde e il test silenzioso è ok.
- [ ] README con setup, comandi e personalizzazione; `CLAUDE.md` con mappa del codice, comandi e insidie.
- [ ] Nessun segreto nei file: controlla con grep il token e il chat_id.

Per esempi concreti dei problemi incontrati e di come sono stati risolti, leggi `references/lezioni-flight-monitor.md` quando devi diagnosticare qualcosa di simile.
