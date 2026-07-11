# Sealed-Holdout-Runner

`ethusdc_bot.backtest.sealed_holdout_runner.run_sealed_holdout(...)` ist der
einzige vorgesehene Übergang von einem eingefrorenen Research-Protocol-v2-
Report zu einem expliziten `final_evaluation`-Report. Der Runner startet keine
Live-, Paper- oder Testtrade-Funktion und verwendet weder Kontozugriff noch
API-Schlüssel oder Orders.

## Eingangsvertrag

Der Runner akzeptiert ausschließlich einen unveränderten Production-Report mit
Schema-Version 2. Er verlangt insbesondere:

- `fixture_data_only == false` und `execution_profile == "production_protocol"`;
- `freeze_status == "frozen_for_separate_sealed_holdout"`;
- die vollständige kanonische Safety-Erklärung auf Report-, Protokoll- und
  Cycle-Ebene;
- einen versiegelten, ungeöffneten, nicht konsumierten und nicht evaluierten
  Holdout von genau 365 zusammenhängenden UTC-Kalendertagen;
- den kanonischen Production-Budgetvertrag des Research Protocol v2;
- einen Frozen Candidate, der exakt der höchstgerankte ausgewählte Finalist mit
  bestandenem Selection-Gate ist;
- ein frisch aus der eingebetteten Selection-Evidenz reproduzierbares Gate,
  das an Kandidaten-ID und kanonische Kandidatensignatur gebunden ist.

Unbekannte Top-Level-Felder, manipulierte Bindungen, Fixture-Reports und
bereits konsumierte Fenster werden vor jedem Candle-Zugriff abgewiesen. Der
übergebene `raw_root` muss außerdem dem im eingefrorenen Report gespeicherten
Root entsprechen.

## One-shot- und Crash-Verhalten

Nach vollständiger Vorprüfung und noch vor dem Candle-Load wird unter
`<reports_root>/sealed_holdout_registry/<claim_identity_sha256>.json` atomar
mit `O_EXCL` ein Claim angelegt. Die kanonische Claim-Identität bindet
Research-Run-ID, kanonische Kandidatensignatur, Holdout-Start/-Ende und
Gate-Version. Dadurch bleibt dieselbe Auswertung auch nach bloßer
Neuformatierung oder Umsortierung des Source-JSON gesperrt. Der SHA-256 der
exakten Source-Bytes bleibt zusätzlich als Provenienz im Claim gebunden. Ein
vorhandener Claim blockiert jeden weiteren Versuch bereits vor dem Datenladen.

Der Claim wird bei keinem Fehler entfernt. Das gilt auch bei einem Absturz,
einem Datenfehler oder einem Simulatorfehler: Sobald der Holdout möglicherweise
geöffnet wurde, darf er nicht erneut ausgewertet werden. Nach Erfolg wird
derselbe Registry-Eintrag atomar auf `completed` gesetzt und an den erzeugten
Finalreport samt SHA-256 gebunden.

## Auswertung und Ausgabe

Der Loader erhält ausschließlich die im Report gespeicherten Start- und
Endtage. Anschließend prüft der Runner nochmals:

- exakt `365 * 1440 = 525600` Candles;
- Start um 00:00 UTC und Ende um 23:59 UTC;
- lückenlose 60-Sekunden-Schritte;
- exakt 1440 Candles an jedem der 365 UTC-Tage;
- keine Candle außerhalb des versiegelten Bereichs.

Der Frozen Candidate wird genau einmal mit ETHUSDC Spot LONG, 100 USDC
Trade-Notional, 0,1 % Gebühr je Seite und 5 bps Slippage je Seite simuliert.
Die unveränderte Selection-Evidenz wird um echte Finalmetriken einschließlich
Mark-to-Market-Drawdown und `sealed_holdout_evaluations == 1` ergänzt. Danach
wird das Final-Gate frisch berechnet.

Der atomar geschriebene Report unter
`<reports_root>/sealed_holdout_final/final_<claim_identity_sha256>.json`
besitzt exakt
das von `shadow/adoption.py` verlangte `final_evaluation`-Schema. Ein grüner,
gelber oder roter Report ist strukturell gültig; nur die nachgelagerte
Shadow-Adoption entscheidet anhand des frisch geprüften Gates über die
Shadow-Eignung. Auch ein grüner Report schaltet niemals echtes Trading frei.

Der Runner wird nicht automatisch ausgeführt. Eine reale Finalauswertung ist
eine bewusste, irreversible Einmalaktion mit einem zuvor eingefrorenen
Production-Report.
