# 11 - End-to-End Bot Goal

Diese Datei beschreibt das Zielbild fuer den fertigen Bot aus Nutzersicht.

Der Nutzer soll am Ende nicht manuell viele Skripte starten muessen. Der Bot soll lokal heruntergeladen, eingerichtet und ueber eine UI gesteuert werden koennen.

---

## 1. Zielbild fuer den Nutzer

Am Ende soll der Nutzer lokal haben:

```text
ETHUSDC_BotV3_Hermes
```

Mit einer UI, die mindestens kann:

- Daten pruefen
- fehlende historische Daten herunterladen
- Daten aktualisieren
- Live-Daten sammeln
- Orderbook/BookTicker sammeln
- Backtest starten
- Backtest pausieren
- Backtest fortsetzen
- Backtest abbrechen
- Backtest neu starten
- Reports anzeigen
- Kandidaten vergleichen
- Kandidat uebernehmen, falls erlaubt
- Paper-Trading starten, falls erlaubt
- Testtrade starten, falls erlaubt
- Live vorbereiten, aber gesperrt halten

---

## 2. Ein-Klick-/Gefuehrter Backtest-Ablauf

Der Backtest soll nicht nur ein einzelnes Skript sein.

Wenn der Nutzer in der UI `Backtest starten` klickt, soll die Pipeline nacheinander pruefen und ausfuehren:

1. Runtime-Status pruefen
2. Symbol/Quote pruefen: ETHUSDC / USDC
3. Handelsart pruefen: Binance Spot LONG-only
4. Datenkatalog laden
5. fehlende ETHUSDC-Klines erkennen
6. fehlende Kontextdaten erkennen
7. fehlende Exchange-Info/Fee-Referenz erkennen
8. fehlende Daten herunterladen oder klare Sperre anzeigen
9. Datenqualitaet pruefen
10. Features bauen
11. Training/Blindtest strikt trennen
12. Kandidaten suchen
13. Kandidaten validieren
14. Router bauen
15. Engine-Backtest ausfuehren
16. Fees/Slippage/Binance-Regeln anwenden
17. Reports schreiben
18. UI aktualisieren
19. Kandidat als uebernehmbar oder gesperrt markieren
20. naechsten Schritt anzeigen

---

## 3. Daten-Download und Aktualisierung

Die UI soll nicht nur anzeigen, dass Daten fehlen. Sie soll einen kontrollierten Weg anbieten:

- fehlende Daten erkennen
- Download starten
- Download pausierbar/fortsetzbar machen, wenn sinnvoll
- Duplikate vermeiden
- UTC-Tage pruefen
- Datenkatalog aktualisieren
- Datenqualitaetsreport schreiben

Datenquellen nach Prioritaet:

1. ETHUSDC Klines 1m
2. BTCUSDC Klines 1m
3. ETHBTC Klines 1m
4. Exchange Info
5. Fee/Commission Reference
6. ETHUSDC AggTrades
7. ETHUSDC Trades
8. BookTicker live gesammelt
9. Orderbook live gesammelt

BookTicker und Orderbook duerfen live gesammelt werden, aber erst nach ausreichender Historie fuer Backtest-Entscheidungen genutzt werden.

---

## 4. Live-Datensammlung

Der Bot soll spaeter Live-Daten sammeln koennen, ohne automatisch live zu handeln.

Erlaubt im Sammelmodus:

- BookTicker sammeln
- Orderbook-Snapshots sammeln
- Latenz/Qualitaet loggen
- Datenkatalog aktualisieren
- Reifegrad anzeigen

Nicht erlaubt:

- echte Orders
- automatische Live-Freigabe
- Nutzung unreifer Daten als positiver Backtestvorteil

---

## 5. Vollstaendigkeitstest

Hermes/Codex muessen vor `fertig` pruefen:

- Sind alle Pflichtdateien vorhanden?
- Startet die UI?
- Funktionieren Buttons technisch?
- Werden Sperrgruende korrekt angezeigt?
- Werden fehlende Daten erkannt?
- Wird Download korrekt geplant/ausgefuehrt?
- Wird Backtest korrekt gestartet?
- Werden Reports erzeugt?
- Kann ein schlechter Backtest als schlecht erkannt werden?
- Bleibt Live gesperrt?
- Ist Neustart/Fortsetzung moeglich?

---

## 6. Keine Optik vor Funktion

Die UI darf schlicht sein.

Prioritaet:

1. Sicherheit
2. Vollstaendigkeit
3. Nachvollziehbarkeit
4. Bedienbarkeit
5. Optik

Optik darf verbessert werden, aber nicht vor Daten, Engine, Backtest, Reports und Sperrlogik.

---

## 7. Downloadbarer Zustand

Ein Zustand ist fuer den Nutzer nur dann brauchbar, wenn er lokal reproduzierbar ist:

- Repo klonen
- Abhaengigkeiten installieren
- UI starten
- Daten pruefen/holen
- Backtest starten
- Reports lesen

Dazu braucht das Projekt spaeter:

- Installationsanleitung
- Startskript fuer Windows
- Beispiel-Konfiguration ohne Secrets
- Datenordner-Regeln
- klare Fehlermeldungen
- Handoff/Status

---

## 8. Was Hermes automatisch hinzufuegen soll

Wenn beim Testen etwas fehlt, soll Hermes es nicht ignorieren.

Hermes muss dann ein neues kleinstes Ticket erzeugen, z.B.:

- fehlender Button
- fehlender Downloadstatus
- fehlender Datencheck
- fehlende Reportzeile
- fehlender Sperrgrund
- UI zeigt Erfolg unklar
- Backtest startet nicht reproduzierbar
- Neustart kann nicht fortsetzen
- Live-Sperre unklar

Hermes soll nicht raten, sondern das fehlende Teil aus Test/Report/UI-Beobachtung beweisen.

---

## 9. Zielbild nach Abschluss

Der Nutzer soll am Ende sagen koennen:

```text
Ich lade das Repo herunter, starte die UI, klicke Backtest starten, und der Bot prueft Daten, laedt Fehlendes, baut Features, trainiert, testet blind, schreibt Reports und zeigt mir eindeutig, ob der Kandidat brauchbar ist.
```

Bis dahin bleibt Live gesperrt.
