# 05 - Initial Kanban Tickets

Diese Tickets sind der Startpunkt fuer Hermes. Sie duerfen von Hermes angepasst, aber nicht ohne Grund geloescht werden.

---

## Ticket 001 - Bootstrap pruefen

Ziel:

- Repository lesen
- AGENTS.md lesen
- PROJECT_CONTRACT.md lesen
- Docs lesen
- bestaetigen, dass keine Codearbeit begonnen wurde

Akzeptanz:

- Hermes gibt Plan aus
- keine Dateien geaendert
- keine Ordner erstellt
- Nutzer bestaetigt naechsten Schritt

---

## Ticket 002 - Lokale Arbeitsstruktur planen

Ziel:

- Struktur unter `C:\TradingBot\hermes-agent` planen
- Git-Repo-Unterordner definieren
- lokale Datenordner definieren
- Backtest-Artefakte vom Repo trennen

Akzeptanz:

- klare Ordnerstruktur
- `.gitignore` passt
- keine grossen Daten im Repo

---

## Ticket 003 - Python-Projektstruktur entwerfen

Ziel:

- Modulstruktur fuer Bot entwerfen
- keine Implementierung vor Planfreigabe

Geplante Bereiche:

- core
- data_pipeline
- features
- strategies
- backtest
- paper
- live
- ui
- configs
- reports
- tests

Akzeptanz:

- Architekturplan vorhanden
- Nutzerfreigabe vor Code

---

## Ticket 004 - Config- und Runtime-Schema definieren

Ziel:

- Runtime-Wahrheit definieren
- Candidate/Active Config definieren
- keine zweite Wahrheit zulassen

Akzeptanz:

- Schema-Dokument
- Tests geplant

---

## Ticket 005 - Datenpipeline-Spezifikation

Ziel:

- ETHUSDC Klines
- BTCUSDC Kontext
- ETHBTC Kontext
- Exchange Info
- Fees/Slippage
- Datenqualitaetsreports

Akzeptanz:

- Datenquellen klar
- Mindesthistorien klar
- unreife Daten blockieren nicht falsch

---

## Ticket 006 - Engine-Spezifikation

Ziel:

- Long-only Engine
- Kapitalgrenze
- Binance-Regeln
- Fees
- Slippage
- Position/Portfolio

Akzeptanz:

- keine Shorts/Futures/Margin moeglich
- Tests geplant

---

## Ticket 007 - Backtest-Spezifikation

Ziel:

- 730 Tage Training
- 365 Tage Blindtest
- strikte Trennung
- Reportpflichten

Akzeptanz:

- Backtest darf kein Live-Fake sein
- Blindtestdaten tabu

---

## Ticket 008 - UI-Minimalplan

Ziel:

- Diagnose-UI statt Schoenheits-UI
- Pflichtbuttons
- Statuskarten
- Sperrgruende

Akzeptanz:

- Mensch erkennt Erfolg/Schrott
- keine Handelslogik in UI

---

## Ticket 009 - Teststrategie

Ziel:

- Unit Tests
- Integration Tests
- Smoke Tests
- Report-Schema-Tests
- Safety Tests

Akzeptanz:

- Testplan vorhanden
- Mindesttests vor Code definiert

---

## Ticket 010 - Erste Implementierungsfreigabe

Ziel:

- Nach Planfreigabe erste minimale Projektstruktur erzeugen
- noch keine Trading-Strategie implementieren

Akzeptanz:

- Git sauber
- Testskelett vorhanden
- Handoff geschrieben
