# 03 - Backtest Acceptance

Dieses Dokument definiert, wann ein Backtest fuer den Nutzer brauchbar ist.

---

## 1. Mindestziel

Ein Zielkandidat muss mit `100 USDC` Startkapital im realistischen 365-Tage-Blindtest mindestens erreichen:

```text
+3 USDC/Tag netto
```

Netto bedeutet:

- nach Fees
- nach Slippage
- nach Binance-Regeln
- ohne perfekte Fills
- ohne Lookahead
- ohne Training auf Blindtestdaten

---

## 2. Pflichtfenster

- Training: 730 Tage
- Blindtest: 365 Tage
- Mindestdaten: 1095 vollstaendige UTC-Tage

Der Blindtest darf nicht fuer Training, Optimierung oder Parameterwahl verwendet werden.

---

## 3. Pflichtkennzahlen

Jeder vollstaendige Backtest muss fuer Menschen sichtbar berichten:

- Run-ID
- Status
- Startkapital
- Trainingszeitraum
- Blindtestzeitraum
- Datenstatus
- verwendete Datenquellen
- nicht verwendete/unreife Datenquellen
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
- Sperrgruende
- Empfehlung: mehr Laufzeit, mehr Daten, Feature-Fix oder Code-Fix

---

## 4. Gueltiger Erfolg

Ein Backtest ist nur erfolgreich, wenn:

- Zielwert netto erreicht wird,
- ausreichende Handelsaktivitaet vorhanden ist,
- Profit nicht nur von einem einzelnen Glueckstreffer kommt,
- Drawdown und Verlustphasen erklaert sind,
- Router/Engine nachvollziehbar handeln,
- Reports vollstaendig sind,
- keine Sicherheitsregel verletzt wurde.

---

## 5. Ungueltiger Erfolg

Nicht gueltig:

- 0 Trades und 0 Verlust als Erfolg
- wenige Glueckstrades ohne robuste Wiederholung
- Profit ohne Fees/Slippage
- Profit durch perfekte Fills
- Profit durch Blindtest-Leakage
- Profit durch manuell gelockerte Gates
- Profit ohne Reportnachweis

---

## 6. Schrott-Erkennung

Ein Lauf ist diagnostisch schlecht, wenn:

- keine validen Kandidaten entstehen,
- Router keine Setups hat,
- Router-Trade-Signale 0 sind,
- Engine-Entry-Versuche 0 sind,
- alle Kandidaten an Fees/Slippage scheitern,
- Aktivitaet zu gering ist,
- Zielwert nicht erreicht wird,
- Reports fehlen oder widerspruechlich sind.

Auch ein schlechter Lauf ist wertvoll, wenn er den naechsten echten Blocker beweist.

---

## 7. Diagnosepflicht bei Zielverfehlung

Wenn `+3 USDC/Tag` nicht erreicht werden:

- keine Gates lockern,
- keine Fake-Trades,
- keine neue Strategie blind einbauen,
- zuerst Reports lesen,
- Ursache beweisen,
- kleinstes Folgeticket erzeugen.

Die Diagnose muss mindestens eine Hauptursache nennen:

- Datenproblem
- Featureproblem
- Entryproblem
- Exitproblem
- Kostenproblem
- Routerproblem
- Engineproblem
- Aktivitaetsproblem
- Overfitproblem
- Blindtest-Wiedererkennungsproblem
- echte fehlende Edge

---

## 8. Paper-Trading-Gate

Ein Kandidat darf erst fuer Paper-Trading vorbereitet werden, wenn:

- Backtestziel erreicht,
- Reports vollstaendig,
- Kandidat bewusst uebernommen,
- keine Sperrgruende offen,
- Nutzer freigibt.

---

## 9. Live-Gate

Live bleibt nach erfolgreichem Backtest weiter gesperrt.

Live-Freigabe braucht zusaetzlich:

- Paper-Trading bestaetigt,
- Testtrade erfolgreich,
- API-Keys lokal vorhanden,
- Nutzer bestaetigt bewusst,
- Sicherheitsstatus gruen.
