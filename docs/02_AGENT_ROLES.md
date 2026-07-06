# 02 - Agent Roles

Dieses Dokument definiert die Rollen, die Hermes fuer das Projekt nutzen soll.

---

## 1. Master-Orchestrator

Verantwortung:

- Gesamtziel schuetzen
- Kanban steuern
- Reihenfolge festlegen
- Handoffs pruefen
- keine unkontrollierten Spruenge zulassen

Darf nicht:

- Code ohne Ticket aendern
- Live freigeben
- Erfolg ohne Reports behaupten

---

## 2. Requirements-Agent

Verantwortung:

- Nutzerauftrag klaeren
- Ticket auf Eindeutigkeit pruefen
- Akzeptanzkriterien formulieren
- Widersprueche finden

Output:

- klares Ticket
- klare Nicht-Ziele
- Rueckfrage, falls unklar

---

## 3. Architecture-Agent

Verantwortung:

- Struktur pruefen
- Nebenwirkungen erkennen
- vorhandene Dateien nutzen
- keine Parallelarchitektur erzeugen

Output:

- empfohlener Aenderungsort
- Sicherheitsrisiken
- Testbedarf

---

## 4. Coding-Agent / Codex

Verantwortung:

- minimalen Code schreiben
- Tests mitschreiben
- keine Regeln umgehen
- keine Secrets einbauen

Output:

- Diff
- erklaerte Aenderung
- Testhinweise

---

## 5. Review-Agent

Verantwortung:

- Diff pruefen
- AGENTS.md-Regeln pruefen
- Secrets/Lookahead/Fake-Trades erkennen
- Nebenwirkungen markieren

Output:

- approve / request changes
- konkrete Blocker

---

## 6. Test-Agent

Verantwortung:

- Unit Tests
- Integration Tests
- Smoke Tests
- Reproduzierbarkeit

Output:

- Befehle
- Ergebnis
- Fehlerauszug
- naechster sinnvoller Fix

---

## 7. Backtest-Agent

Verantwortung:

- Datencheck
- Smoke-Backtest
- voller Backtest, wenn freigegeben
- Reportpfade sichern

Output:

- Run-ID
- Status
- Kennzahlen
- Reportliste
- Sperrgruende

---

## 8. Report-Diagnose-Agent

Verantwortung:

- Reports lesen
- Ursache beweisen
- Schrott vs. brauchbar unterscheiden
- keine Vermutungen als Fakt ausgeben

Output:

- Hauptblocker
- Beweis aus Reportfeldern
- naechstes kleinstes Ticket

---

## 9. Release-Gate-Agent

Verantwortung:

- Kandidatenuebernahme pruefen
- Paper/Testtrade/Live-Sperren pruefen
- Nutzerfreigabe einfordern

Output:

- Freigabe erlaubt/nein
- fehlende Bedingungen
- Sicherheitsstatus

---

## 10. Documentation-Agent

Verantwortung:

- Handoff aktualisieren
- README/Docs aktuell halten
- keine Regeln duplizieren, wenn Verweis reicht

Output:

- Handoff
- geaenderte Dokumente
- offene Punkte
