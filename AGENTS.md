# AGENTS.md - Harte Arbeitsregeln fuer Hermes, Codex, Copilot und alle Agenten

Diese Datei ist der verbindliche Arbeitsvertrag fuer alle Agenten in diesem Repository.

Wenn ein Agent unsicher ist, gilt:

1. Nicht raten.
2. Keine Dateien aendern.
3. Diagnose oder Rueckfrage erstellen.
4. Erst nach Freigabe weiterarbeiten.

---

## 1. Rollenmodell

- **Hermes** ist das Gehirn des Projekts: Orchestrierung, Planung, Kanban, Schleifensteuerung, Handoff, Qualitaetskontrolle.
- **Codex** ist der primaere Code-Ausfuehrer fuer Implementierung, Refactoring, Tests und groessere Codearbeiten.
- **GitHub** ist Sicherung, Versionierung, Issues, Pull Requests und historischer Nachweis.
- **GitHub Copilot** ist optionaler Zusatz fuer Coding/Review, aber nicht Projektwahrheit.
- **ChatGPT/Nutzer** bleibt externe Entscheidungs- und Freigabeinstanz.
- **Lokaler PC** ist die Wahrheit fuer grosse historische Daten, Backtests, Paper-Trading und spaetere Live-Tests.

---

## 2. Projektziel

Baue von null ein lokales ETHUSDC Binance Spot LONG-only Trading-Bot-System.

Pflichtwerte:

- Symbol: `ETHUSDC`
- Quote/Kapitalbasis: `USDC`
- Handelsart: Binance Spot LONG-only
- Standard-Startkapital: `100 USDC`
- Standard-Risikoprofil: `mittel`
- Trainingsfenster: `730 Tage`
- Blindtest: `365 Tage`
- Mindestdatenziel: `1095 vollstaendige UTC-Tage ETHUSDC-Klines`
- Kontextdaten: `BTCUSDC` und `ETHBTC`
- Zusatzdaten: AggTrades, Trades, Exchange Info, Fees, Slippage, BookTicker, Orderbook

Zielkandidat:

- mindestens `+3 USDC/Tag` im realistischen 365-Tage-Blindtest,
- nach Fees, Slippage und Binance-Regeln,
- ohne Lookahead,
- ohne Blindtestdaten im Training,
- mit nachvollziehbaren Reports.

---

## 3. Verbotene Abkuerzungen

Strikt verboten:

- Fake-Trades
- Fake-Reports
- perfekte Backtest-Fills
- Blindtestdaten im Training
- Quality-Gate-Lockerung nur fuer bessere Zahlen
- nachtraegliche Report-Schoenfaerbung
- echte API-Keys oder Secrets im Repository
- automatische Live-Aktivierung
- UI-Handelslogik
- manuelle Strategie-Erzwingung ueber die UI
- zweite Wahrheit neben Runtime, Progress, Summary, Candidate Config, Active Config und Git-Stand
- Behauptung `fertig`, wenn Tests, Reports und Abnahme fehlen

---

## 4. Entwicklungsregel

Jede Aenderung muss klein, nachvollziehbar und testbar sein.

Standardablauf:

1. Ticket erstellen.
2. Requirements-Agent prueft Ticket.
3. Architecture-Agent prueft Struktur/Nebenwirkungen.
4. Codex implementiert minimal.
5. Review-Agent prueft Diff und Regeln.
6. Test-Agent fuehrt Tests aus.
7. Backtest-Agent fuehrt passenden Smoke-Test oder Backtest aus.
8. Report-Diagnose-Agent liest Reports.
9. Wenn Ziel nicht erreicht: Ursache beweisen und kleinstes Folgeticket erzeugen.
10. Handoff aktualisieren.

Kein Agent darf eine grosse Architektur neu erfinden, wenn ein kleinerer, sauberer Schritt reicht.

---

## 5. GitHub-Regeln

- Keine Secrets committen.
- `.env`, Binance Keys, API Keys, private Tokens, grosse Rohdaten und grosse Backtest-Artefakte duerfen nicht ins Repository.
- Jede relevante Aenderung muss per Commit nachvollziehbar sein.
- Fuer groessere Codearbeiten: Branch + Pull Request bevorzugen.
- Commit-Nachrichten muessen Zweck und Sicherheitsrelevanz kurz nennen.

---

## 6. Backtest-Regeln

Ein Backtest-Kandidat ist nur brauchbar, wenn Reports mindestens zeigen:

- Run-ID
- Status
- Startkapital
- Trainingszeitraum
- Blindtestzeitraum
- Datenstatus
- verwendete Datenquellen
- nicht verwendete oder unreife Datenquellen
- getestete Kandidaten
- valide Kandidaten
- beste Situation / bestes Setup
- Router-Setups
- Router-Trade-Signale
- Engine-Entry-Versuche
- echte Trades
- Netto-USDC pro Tag
- Gesamtprofit
- Fees
- Slippage
- Drawdown
- Winrate
- Profit-Factor
- aktive Tage
- No-Trade-Tage
- Haupt-Ablehnungsgruende
- Kandidat uebernehmbar ja/nein
- Sperrgrund, falls nicht uebernehmbar

Ein leerer oder fast leerer Blindtest ist kein Erfolg, nur weil keine Verluste entstehen.

---

## 7. UI-Regeln

Optik ist zweitrangig. Eindeutigkeit ist Pflicht.

Die UI muss fuer den Nutzer sichtbar machen:

- Ist der Bot bereit?
- Laeuft gerade ein Backtest?
- Welche Phase laeuft?
- Sind Daten vollstaendig?
- Ist der Backtest erfolgreich?
- Ist der Backtest schlecht?
- Warum ist er schlecht?
- Darf der Kandidat uebernommen werden?
- Ist Paper/Testtrade/Live gesperrt oder freigegeben?
- Welcher Sperrgrund existiert?

Pflichtbuttons:

- Backtest starten
- Backtest pausieren
- Backtest fortsetzen
- Backtest abbrechen
- Backtest Neustart
- Daten pruefen / aktualisieren
- Neuen Backtest uebernehmen
- Bot auf Null setzen
- Testtrade starten
- Paper-Trading starten
- Live vorbereiten, aber gesperrt bis Freigabe

---

## 8. Live-Sperre

Live-Trading darf niemals automatisch starten.

Live bleibt gesperrt, bis:

1. realistischer Backtest bestanden,
2. Kandidat bewusst uebernommen,
3. Paper-Trading stabil bestaetigt,
4. Nutzer bewusst freigegeben,
5. API-Keys lokal vorhanden und nicht im Repository,
6. Testtrade erfolgreich dokumentiert.

---

## 9. Wenn das Ziel nicht erreicht wird

Wenn der Bot nicht mindestens `+3 USDC/Tag` im realistischen Blindtest erreicht:

- keine Gates lockern,
- keine Fake-Trades,
- keine Ergebnis-Schoenfaerbung,
- Reports lesen,
- Ursache beweisen,
- naechstes kleinstes Ticket erstellen.

Gueltige Ursachenanalyse muss sagen, ob das Problem liegt bei:

- Datenabdeckung,
- Feature-Build,
- Cluster/Situationserkennung,
- Entry,
- Exit,
- Fees/Slippage,
- Binance-Regeln,
- Router,
- Engine,
- zu wenig Aktivitaet,
- Overfitting,
- Blindtest-Wiedererkennung,
- echter fehlender Edge.

---

## 10. Fertig-Definition

Ein Zustand ist erst `fertig`, wenn alle Punkte zutreffen:

- Tests gruen,
- Backtest-Reports vorhanden,
- realistischer 365-Tage-Blindtest bestanden,
- Zielwert erreicht oder klare belegte Diagnose vorhanden,
- keine verbotenen Abkuerzungen,
- Git-Stand sauber,
- Handoff aktualisiert,
- Nutzer hat naechsten Schritt bestaetigt.

---

## 11. Protocol-v3-Arbeits- und Evidenzvertrag

Protocol-v3-Vertragsgeneration: `3.0.0`
Maschinenlesbarer Vertrag: `configs/protocol_v3_contract.json`
Kanonischer Zusatzvertrag: `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
Verbindliche Reihenfolge: `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`

Fuer Protocol v3 gelten zusaetzlich folgende harte Agentenregeln:

1. Es ist immer genau eine Aufgabe aus Dokument 41 aktiv. Eine spaetere Aufgabe beginnt erst, wenn die vorherige Aufgabe mit Tests, Handoff und Git-Synchronitaet `DONE_100` erreicht hat.
2. Champion ist die versionierte monatliche Auswahlpipeline, nicht ein einzelner fixer Kandidat.
3. Der Zeitraum `2025-07-08..2026-07-07` bleibt dauerhaft `consumed_audit` und `NOT_FRESH`.
4. Reine Rohmarktbeobachtungen aus einem frueheren Pseudo-OOS duerfen in einer spaeteren Origin als kausale Historie erscheinen. Fruehere PnL, Rankings, Reports, Gate-Ergebnisse und menschliche Ergebnisinterpretationen duerfen niemals in spaetere Fits gelangen.
5. `monthly_process_oos` auf der vorhandenen Historie bleibt `diagnostic_only` und kann weder Adoption noch Protocol-v3-Finalstatus erzeugen.
6. Ein `research_challenger_shadow` ist separat, manuell und strikt orderfrei. Er darf keine Adoption, Orders, Trading-API, Paper-, Testtrade- oder Live-Freigabe ausloesen.
7. Ein Protocol-v3-Finalstatus ist nur durch einen getrennten Pipeline-Final-Evaluator auf einem vorab registrierten, wirklich neuen `sealed_final_holdout` moeglich.
8. Protocol v2 und der bestehende Single-Candidate-Finalpfad bleiben erhalten, duerfen aber keinen Protocol-v3-Finalstatus behaupten.
9. Fehlende oder widerspruechliche Manifest-/Dokumentversionen blockieren fail-closed. Kein Agent darf die Sperre durch Annahmen oder stillschweigende Defaults umgehen.
