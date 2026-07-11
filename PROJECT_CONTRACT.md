# PROJECT_CONTRACT.md - Projektvertrag ETHUSDC_BotV3_Hermes

Dieser Vertrag beschreibt, was gebaut werden soll und woran Erfolg oder Scheitern gemessen wird.

Die spaeter verbindlich konkretisierten Kapital-, Ziel-, Ampel- und
Shadow-Regeln stehen in `docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md`. Bei
Widerspruechen zu aelteren Ziel- oder Paper-Beschreibungen hat Dokument 31
Vorrang.

---

## 1. Projektgrundsatz

Dieses Projekt ist ein kompletter Neustart.

Alter Bot-Code darf nicht als Codebasis uebernommen werden.
Alte Projektdateien und Erfahrungen duerfen nur als fachliche Referenz dienen.

Das Ziel ist nicht ein weiterer schneller Versuch, sondern eine kontrollierte Entwicklungsfabrik mit Hermes, Codex, GitHub und lokalen Backtests.

---

## 2. Rollen

| Rolle | Aufgabe |
|---|---|
| Hermes | Orchestrator, Planung, Kanban, Agentensteuerung, Schleifenlogik |
| Codex | Primaerer Code-Ausfuehrer |
| GitHub | Sicherung, Versionierung, Issues, Pull Requests |
| GitHub Copilot | Zusatzhilfe fuer Coding/Review |
| ChatGPT/Nutzer | Externe Kontrolle, Freigabe, Entscheidung |
| Lokaler PC | Daten, Backtests, Paper-Trading, spaeter Live-Test |

---

## 3. Trading-System

Pflicht:

- ETHUSDC
- USDC als Kapitalbasis
- Binance Spot LONG-only
- keine Shorts
- kein Margin
- keine Futures
- kein Leverage
- kein Handel anderer Symbole

Kontextdaten duerfen genutzt werden, aber keine Orders ausloesen:

- BTCUSDC
- ETHBTC

---

## 4. Zielwert

Standardrichtwert:

- Startkapital: `100 USDC`
- gewuenschter Richtwert: etwa `+3 USDC/Tag`
- Messung: realistischer 365-Tage-Blindtest
- Nach Kosten: Fees, Slippage, Binance-Regeln

Wichtig:

Der Zielwert ist ein sichtbarer Richtwert und keine Garantie fuer spaetere
Gewinne. Robustheit und Zielerreichung werden getrennt ausgewiesen. Eine
Uebernahme aktiviert zunaechst nur den orderfreien Shadow-Modus; Live bleibt
separat gesperrt.

---

## 5. Backtest-Philosophie

Der Backtest muss realistisch sein.

Verboten:

- perfekte Fills
- Zukunftswissen
- Training auf Blindtestdaten
- versteckte Datenlecks
- nachtraegliches Schoenrechnen
- Weglassen von Fees/Slippage
- Ignorieren von Binance-Regeln

Pflicht:

- 730 Tage Training
- 365 Tage Blindtest
- klare Datenqualitaet
- klare Reports
- klare Sperrgruende
- klare Uebernahmeentscheidung

---

## 6. Projektphasen

### Phase 0 - Bootstrap

- AGENTS.md
- PROJECT_CONTRACT.md
- Hermes Operating Model
- Agentenrollen
- Sicherheitsregeln
- GitHub-Regeln

### Phase 1 - Projektstruktur

- Ordnerstruktur
- Python-Projektsetup
- `.gitignore`
- Config-Schema
- Runtime-Schema
- Report-Schema
- Testskelett

### Phase 2 - Datenpipeline

- ETHUSDC Klines
- BTCUSDC Kontext
- ETHBTC Kontext
- Exchange Info
- Fees/Slippage-Modell
- Datenkatalog
- Datenqualitaetsreports

### Phase 3 - Engine

- Portfolio
- Position
- Binance-Regeln
- Fees
- Slippage
- Execution
- Long-only-Schutz
- Kapitalgrenze

### Phase 4 - Backtest

- Training/Blindtest-Split
- Feature-Build
- Kandidatensuche
- Router
- Engine-Integration
- Reports

### Phase 5 - UI

- Kontroll- und Diagnose-Dashboard
- Startwerte
- Datenstatus
- Backteststatus
- Ergebnisstatus
- Kandidatenuebernahme
- Sperrgruende

### Phase 6 - Paper-Trading

- gleiche Engine wie Backtest
- Paper-Market-Adapter
- Session-Reports

### Phase 7 - Testtrade/Live-Vorbereitung

- Live bleibt gesperrt
- Testtrade-Modus
- API-Key lokal
- Sicherheitspruefung

---

## 7. Menschliche Abnahme

Der Nutzer muss explizit freigeben:

- Start der echten Codeumsetzung nach Bootstrap
- groessere Architekturentscheidungen
- Uebernahme eines Kandidaten
- Paper-Trading-Start
- Testtrade
- Live-Freigabe

---

## 8. Schrott-Erkennung

Ein Backtest gilt als nicht ausreichend, wenn:

- 0 oder fast 0 Trades nur Verluste vermeiden,
- Reports fehlen,
- Fees/Slippage fehlen,
- Blindtest nicht strikt blind ist,
- Zielwert nur durch Glueck oder wenige Ausreisser entsteht,
- Drawdown unklar oder zu hoch ist,
- Router/Engine nicht nachvollziehbar sind,
- keine klare Ursache fuer Scheitern dokumentiert wird.

---

## 9. Handoff-Pflicht

Nach jedem Arbeitszyklus muss ein Handoff existieren:

- Was wurde gemacht?
- Welche Dateien wurden geaendert?
- Welche Tests wurden ausgefuehrt?
- Welche Reports wurden erzeugt?
- Was ist der aktuelle Blocker?
- Was ist das naechste kleinste Ticket?
- Ist Nutzerfreigabe noetig?

---

## 10. Keine Erfolgsluegen

Wenn der Zielwert nicht erreicht wird, muss das System ehrlich melden:

- Ziel nicht erreicht,
- warum nicht,
- welche Daten/Reports das beweisen,
- welcher minimale naechste Schritt sinnvoll ist.
