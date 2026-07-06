# 04 - Live Safety

Dieses Dokument definiert die Live-Sicherheitsregeln.

---

## 1. Grundsatz

Live-Trading darf niemals automatisch starten.

Das Projekt darf Live-Code vorbereiten, aber Live bleibt technisch gesperrt, bis alle Gates bestanden sind und der Nutzer bewusst freigibt.

---

## 2. Handelsgrenzen

Erlaubt:

- ETHUSDC kaufen
- ETHUSDC verkaufen
- in USDC bleiben
- nicht handeln

Verboten:

- Shorts
- Margin
- Futures
- Leverage
- andere Handelspaare
- geliehenes Kapital
- automatische Kapitalerhoehung

---

## 3. API-Key-Regeln

- API-Keys liegen nur lokal in `.env` oder sicherem lokalen Secret-Speicher.
- Keine Keys ins Repository.
- Keine Keys in Reports.
- Keine Keys in Logs.
- Keine Keys in Screenshots.
- `.env` bleibt in `.gitignore`.

---

## 4. Live-Gates

Live darf erst vorbereitet werden, wenn:

1. realistischer Backtest bestanden,
2. Kandidat bewusst uebernommen,
3. Paper-Trading bestaetigt,
4. Testtrade erfolgreich,
5. Nutzerfreigabe vorhanden,
6. Runtime konsistent,
7. Active Config gueltig,
8. API-Keys lokal vorhanden,
9. Kapitalgrenze geprueft,
10. Binance-Regeln geladen.

---

## 5. Sperrzustaende

Live bleibt gesperrt bei:

- fehlender Active Config
- inkonsistenter Runtime
- fehlenden Reports
- nicht bestandenem Backtest
- nicht bestandenem Paper-Trading
- offenem Sicherheitsblocker
- fehlenden Binance-Regeln
- fehlendem Fee-/Slippage-Modell
- fehlender Nutzerfreigabe
- offener Position aus anderem Modus

---

## 6. Testtrade

Testtrade ist ein eigener Modus und ersetzt keine Live-Freigabe.

Testtrade muss dokumentieren:

- Zeitpunkt
- Symbol
- Ordertyp
- erwartete Menge
- tatsaechliche Menge
- Preis
- Fees
- Slippage
- Binance-Regelpruefung
- Ergebnis
- Fehler/Sperrgrund

---

## 7. Paper-Trading

Paper-Trading muss dieselbe Engine nutzen wie Backtest und Live.

Unterschiede duerfen nur in Market-Adapter und Order-Ausfuehrung liegen.

Paper-Trading muss zeigen:

- Signale
- Router-Entscheidungen
- virtuelle Entries/Exits
- virtuelle Fees/Slippage
- Abweichungen zum Backtest
- Session-Report

---

## 8. Not-Aus

Das System braucht eine klare Not-Aus-Logik:

- Live stoppen
- keine neuen Orders
- offene Position sichtbar machen
- manuellen Eingriff ermoeglichen
- Fehler reporten

---

## 9. Keine Erfolgsgarantie

Ein erfolgreicher Backtest ist keine Garantie fuer Live-Gewinne.

Deshalb gilt:

Backtest -> Paper -> Testtrade -> bewusste Live-Freigabe

Keine Stufe darf uebersprungen werden.
