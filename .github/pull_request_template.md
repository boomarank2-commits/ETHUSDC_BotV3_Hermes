# Pull Request Checklist

## Zweck

Was wird geaendert und warum?

## Ticket / Bezug

- Issue/Ticket:
- Report/Blocker:

## Art der Aenderung

- [ ] Dokumentation
- [ ] Tests
- [ ] Config/Schema
- [ ] Datenpipeline
- [ ] Engine
- [ ] Backtest
- [ ] Paper
- [ ] Live/Testtrade
- [ ] UI
- [ ] Sonstiges

## Sicherheitscheck

- [ ] Keine Secrets committed
- [ ] Keine Fake-Trades
- [ ] Keine Fake-Reports
- [ ] Keine Blindtestdaten im Training
- [ ] Keine Quality-Gate-Lockerung nur fuer bessere Zahlen
- [ ] Keine automatische Live-Aktivierung
- [ ] Live bleibt gesperrt
- [ ] Keine zweite Wahrheit eingefuehrt

## Tests

Ausgefuehrt:

```text
# Befehle hier eintragen
```

Ergebnis:

```text
# Ergebnis hier eintragen
```

## Backtest / Diagnose

Falls relevant:

- Run-ID:
- Status:
- usdc_per_day:
- total_profit_usdc:
- trades:
- Hauptblocker:
- Reportpfad:

## Handoff

- [ ] Handoff aktualisiert
- [ ] Naechster kleinster Schritt dokumentiert
- [ ] Nutzerfreigabe erforderlich: ja/nein

## Reviewer-Hinweise

Was muss besonders geprueft werden?
