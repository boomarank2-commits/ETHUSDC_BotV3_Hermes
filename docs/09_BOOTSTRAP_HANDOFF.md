# 09 - Bootstrap Handoff

Stand: 2026-07-06

Dieses Handoff beschreibt den aktuellen Zustand nach der ersten GitHub-Vorbereitung.

---

## 1. Was erledigt wurde

Das Repository wurde mit dem kontrollierten Projektanker vorbereitet.

Erstellt wurden:

- README.md
- AGENTS.md
- PROJECT_CONTRACT.md
- .gitignore
- .env.example
- docs/01_HERMES_OPERATING_MODEL.md
- docs/02_AGENT_ROLES.md
- docs/03_BACKTEST_ACCEPTANCE.md
- docs/04_LIVE_SAFETY.md
- docs/05_INITIAL_KANBAN_TICKETS.md
- docs/06_HERMES_BOOTSTRAP_PROMPT.md
- docs/07_LOCAL_NEXT_STEPS.md
- docs/08_HUMAN_BACKTEST_DASHBOARD_FIELDS.md
- docs/09_BOOTSTRAP_HANDOFF.md

---

## 2. Was bewusst NICHT erledigt wurde

Noch nicht erstellt:

- Bot-Code
- Trading-Engine
- Strategien
- Backtest-Code
- UI-Code
- Datenpipeline-Code
- GitHub Actions
- echte Runtime-Configs
- echte Reports

Grund:

Der Bot soll von Hermes/Codex kontrolliert in Tickets gebaut werden. Der Bootstrap legt nur Regeln, Rollen und Abnahmekriterien fest.

---

## 3. Aktueller lokaler Hermes-Stand laut Nutzer

- Hermes installiert
- Hermes-Arbeitsordner: `C:\TradingBot\hermes-agent`
- OpenAI Codex OAuth eingerichtet
- Standardmodell auf `gpt-5.5` gesetzt
- GitHub Token in Hermes `.env` erkannt
- GitHub Skills Hub aktiv
- Codex aktuell wegen Nutzungslimit temporaer nicht verfuegbar

---

## 4. Naechster Schritt

Sobald Codex wieder verfuegbar ist:

1. Lokales Repo klonen:

```powershell
cd C:\TradingBot\hermes-agent
git clone https://github.com/boomarank2-commits/ETHUSDC_BotV3_Hermes.git
cd ETHUSDC_BotV3_Hermes
git status
```

2. Hermes aus dem Arbeitsordner starten:

```powershell
cd C:\TradingBot\hermes-agent
hermes
```

3. Hermes anweisen:

```text
Lies im Repository ETHUSDC_BotV3_Hermes die Datei docs/06_HERMES_BOOTSTRAP_PROMPT.md und fuehre den Prompt aus.
Plane zuerst. Aendere keine Dateien, erstelle keine Ordner und fuehre keinen Code aus, bis ich bestaetige.
```

4. Hermes-Plan extern pruefen lassen.

5. Erst nach Freigabe Phase 1 starten.

---

## 5. Wichtigster Schutz

Hermes darf nicht direkt Code bauen, bevor der erste Plan geprueft wurde.

Der erste Hermes-Output muss nur Plan sein:

- Ordnerstruktur
- GitHub-Struktur
- Kanban-Spalten
- Agentenrollen
- Tickets
- Freigaben
- Risiken

---

## 6. Projektziel bleibt

- ETHUSDC
- USDC
- Binance Spot LONG-only
- 100 USDC Standardkapital
- Ziel: mindestens +3 USDC/Tag im realistischen 365-Tage-Blindtest
- keine Fake-Trades
- keine Fake-Reports
- keine Blindtestdaten im Training
- keine Gate-Lockerung
- Live bleibt gesperrt

---

## 7. Entscheidung offen

Der Nutzer muss als naechstes bestaetigen:

- ob Hermes den Bootstrap-Plan erstellen darf,
- ob danach die lokale Ordnerstruktur angelegt werden darf,
- ob danach die minimale Python-Projektstruktur erstellt werden darf.
