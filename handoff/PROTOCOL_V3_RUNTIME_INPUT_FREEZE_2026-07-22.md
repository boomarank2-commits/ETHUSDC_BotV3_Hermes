# Protocol v3 – Production Runtime Input Freeze

Stand: 2026-07-22

## Ergebnis

Der produktive aktive Lookback-Satz und die exakte `HorizonPolicy` sind jetzt
versioniert, streng validiert und in die Protocol-v3-Pipelinegeneration
eingebunden. Der Task-33-Preflight akzeptiert keine bloß plausiblen positiven
Werte mehr, sondern ausschließlich die exakte eingefrorene Konfiguration.

Eingefrorene Lookbacks:

- `BTCUSDC`: `btc_return_168h`, 168 x 1h;
- `ETHBTC`: `ethbtc_return_72h`, 72 x 1h;
- `ETHUSDC`: `eth_range_20d`, 20 x 1d.

Eingefrorene HorizonPolicy:

- maximaler Labelhorizont: 10.080 Minuten;
- maximale Haltedauer: 10.080 Minuten, entsprechend der Obergrenze des
  `multiday_swing_trend`-Spezialisten;
- Pending-Entry-Latenz: 2 Minuten;
- Ausführungsbar: 1 Minute.

Eine Verlängerung verändert die Pipelinegeneration. Safety Locks bleiben
unverändert: keine Orders, keine Trading-API, kein Paper, Testtrade oder Live.

## Prüfung der 33 Patches und des Ziels

- Die vollständige lokale Suite ist mit 1.336/1.336 Tests grün.
- Die UI zeigt die echte Protocol-v3-Evidenz mit 33/33 und startet keinen alten
  Protocol-v2-Lauf als Ersatz.
- Ein vollständiger realer Protocol-v3-Research-Lauf wurde nicht gestartet.
- `+3 USDC/Tag` wurde daher weder erreicht noch widerlegt; alle echten
  Task-33-Ergebnismetriken bleiben `null`.
- Der alte UI-Ergebniswert von ungefähr `0,0126 USDC/Tag` stammt aus Protocol v2
  und beweist nichts über die 33 Protocol-v3-Patches.

## Verbleibende harte Blocker

1. Die 180 historischen Auswertungszeilen besitzen keine rekonstruierbaren
   Seeds und keine kausalen `daily_net_mtm_usdc`-Reihen. Die aktuelle
   Vertragsgeneration erlaubt deshalb ausschließlich `NO_TRADE`.
2. Es fehlt weiterhin der echte Produktionsadapter vom Drei-Markt-Rohbestand
   durch Task 15 bis 27, zwölf Outer Origins und Task-13-Resume.

Der zweite Blocker darf implementiert werden, kann aber den ersten nicht
rechtmäßig aufheben. Eine Änderung der historischen Trial-/DSR-Behandlung
benötigt eine ausdrückliche Architekturentscheidung und eine neue
Vertragsgeneration; es wurden keine Werte erfunden und keine Gates gelockert.

## Verifikation

- gezielte Runtime-/Pipeline-/Task-33-Tests: 31/31 grün;
- vollständige Suite: 1.336/1.336 grün, Laufzeit 741,3 Sekunden;
- Ruff für alle geänderten Python-Dateien: grün;
- `git diff --check`: grün.

