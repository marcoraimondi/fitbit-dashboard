# Google Health API — Guida per il bot

## Setup completato

- Token salvati in `/workspace/.googlehealth/tokens.json`
- Helper di refresh in `/workspace/.googlehealth/gh_refresh.py`
- Script raccolta giornaliera in `/workspace/.googlehealth/gh_daily_collect.py`
- Dati storici in `/workspace/.googlehealth/data/YYYY-MM-DD.json`
- Cron job `googlehealth-daily` attivo: ogni giorno alle 06:00 Europe/Rome raccoglie i dati del giorno precedente

---

## Come rispondere alle domande di salute

### 1. Prima cerca i dati salvati

```python
import json
date = '2026-07-17'
path = f'/workspace/.googlehealth/data/{date}.json'
try:
    data = json.load(open(path))
except FileNotFoundError:
    data = None  # devo raccoglierli
```

### 2. Token — rinnovalo in silenzio

```python
import sys
sys.path.insert(0, '/workspace/.googlehealth')
from gh_refresh import get_valid_token
token = get_valid_token()
# Se scaduto lo rinnova automaticamente via Cloudflare Worker
# Mai dire "token scaduto" all'utente
```

---

## tokens.json

```json
{
  "access_token": "ya29...",
  "refresh_token": "1//...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "1093559756083-osn93vvj22n06aaorkjfot888f3drmd7.apps.googleusercontent.com",
  "scopes": [...]
}
```

Il refresh NON funziona diretto su oauth2.googleapis.com (manca client_secret).
Avviene tramite Cloudflare Worker:
  POST https://odd-cloud-7fd2.marco-raimondi.workers.dev/refresh
  Body: { "refresh_token": "...", "client_id": "..." }
  Risposta: { "access_token": "nuovo_token" }

---

## Struttura JSON giornaliero (data/YYYY-MM-DD.json)

```json
{
  "date": "2026-07-17",
  "steps": 10271,
  "active_kcal": 904.5,
  "sleep": {
    "total_mins": 378, "asleep_mins": 373, "awake_mins": 5,
    "deep_mins": 83, "light_mins": 203, "rem_mins": 87,
    "total_fmt": "6h 18m", "deep_fmt": "1h 23m", "rem_fmt": "1h 27m"
  },
  "heart_rate": { "avg": 80.9, "min": 50, "max": 137, "samples": 26124 },
  "weight": { "kg": null, "date": "2026-07-13" }
}
```

---

## Google Health API — dettagli tecnici

Base URL: https://health.googleapis.com/v4/users/me/dataTypes

Endpoint testati e funzionanti:

- steps              → steps.count          | data: interval.civilStartTime
- active-energy-burned → activeEnergyBurned.kcal  | campo "kcal" (NON "kilocalories"!)
- sleep              → sleep.summary        | data: interval.startTime (NON sampleTime!)
- heart-rate         → heartRate.beatsPerMinute | data: heartRate.sampleTime.physicalTime
- weight             → weight.kilograms     | data: weight.sampleTime.physicalTime

Limitazioni paginazione (pageSize max 5000):
- FC (~3 sec/campione): 5000 pt = ~4 ore → 10 pagine per ~40 ore
- Passi/calorie (~1 min): 5000 pt = ~3,5 giorni → 3 pagine per 7 giorni
- Sonno: 1 punto per notte → 1 pagina basta
- L'API NON supporta filtri per data (startTime/endTime → errore 400)
- Paginare con nextPageToken dalla risposta

Sonno — gotcha:
- Usa interval.startTime per identificare la notte (non sampleTime)
- Stagioni in summary.stagesSummary: [{type, minutes, count}]
- Tipi: AWAKE, LIGHT, DEEP, REM

Calorie — gotcha:
- Il campo si chiama "kcal" (non "kilocalories")

---

## Auth page (rinnovo manuale refresh_token)

https://marcoraimondi.github.io/fitbit-dashboard/auth.html

Il prompt generato include tutte le istruzioni per configurare il bot da zero.
