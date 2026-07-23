# Protocol v3 – konservative Legacy-Multiplicity-Remediation

Stand: 2026-07-23

## Auftrag und Entscheidung

Der Nutzer hat ausdrücklich eine neue konservative Vertragsgeneration
freigegeben: Alle 180 belegten historischen Auswertungszeilen zählen als
unabhängige Versuche ausschließlich für die Multiple-Testing-Strafe. Fehlende
Trial-Identitäten, Seeds, PnL-Werte, Rankings, Gate-Ergebnisse und tägliche
MTM-Reihen werden nicht rekonstruiert oder erfunden.

GitHub-Issue: `#22`

## Umsetzung

- Neuer Vertrag:
  `configs/protocol_v3_legacy_multiplicity_contract.json`
- Neue fail-closed Implementierung:
  `src/ethusdc_bot/protocol_v3/legacy_multiplicity.py`
- Stabile API-Fassade:
  `src/ethusdc_bot/protocol_v3/legacy_multiplicity_api.py`
- Task-18-DSR-Vertrag auf
  `protocol_v3_exact_deflated_sharpe_with_legacy_floor_v2` angehoben.
- Task-33-Preflight-Vertrag auf
  `protocol_v3_real_research_preflight_with_legacy_floor_v2` angehoben.
- Pipelinegeneration bindet Vertrag, Implementierung und API.

## Exakte Rechenregel

```text
N_raw = 180 + Anzahl aller vollständigen nativen unabhängigen Trials
```

Die 180 Legacy-Zeilen liefern keine Tagesreihen. Vollständige native Trials aus
anderen Monats-Origins erhöhen `N_raw`, werden aber nicht mit dem aktuellen
360-Tage-Raster in Sharpe-Streuung oder Korrelation vermischt. Diese beiden
Statistiken verwenden ausschließlich mindestens zwei vollständige native Trials
auf exakt demselben zusammenhängenden 360-Tage-UTC-Raster.

Der Legacy-Floor allein kann niemals einen DSR-Pass oder eine Kandidatenfreigabe
erzeugen. Ein fehlender oder widersprüchlicher kanonischer Legacy-Import
blockiert weiterhin `INSUFFICIENT_TRIAL_HISTORY`.

## Verifikation

- 23 gezielte Legacy-Multiplicity-/DSR-/Task-33-Tests: grün.
- 102 zusammenhängende Trial-Ledger-/Matrix-/PBO-/DSR-/Selection-/
  Task-33-/Pipeline-Vertragstests: grün.
- Vollständige Suite: 1.347/1.347 Tests grün, Laufzeit 734,1 Sekunden.
- Ruff für alle geänderten Python-Dateien: grün.
- Adversarial Tests belegen:
  - anderes Origin-Raster zählt für `N_raw`, nicht für Same-Grid-Statistik;
  - lückenhaftes 360-Tage-Raster blockiert fail-closed;
  - rehashte Preflight-Umgehung wird abgelehnt;
  - 179 statt 180 beobachtete Legacy-Zeilen blockieren weiter.

## Sicherheitsstatus

- keine Gates gelockert;
- keine Fake-Trials, Seeds, Tagesreihen, Trades oder Reports;
- keine API-Keys, privaten Endpunkte oder Trading-API;
- keine Orders, kein Paper-, Testtrade- oder Live-Start;
- kein Final-Holdout registriert oder verbraucht;
- `NO_TRADE`, Adoption und Botstart bleiben gesperrt.

## Verbleibender Blocker

Nach einem neuen create-only Task-33-Preflight muss ausschließlich
`MISSING_PRODUCTION_OUTER_ORIGIN_ADAPTER` verbleiben. Erst nach grünem Commit
und neuem Report darf Issue `#21` als nächste getrennte Remediation beginnen.
