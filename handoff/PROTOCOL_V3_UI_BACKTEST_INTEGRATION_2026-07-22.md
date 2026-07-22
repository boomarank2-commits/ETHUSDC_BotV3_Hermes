# Protocol v3 – UI-Backtest-Integrationsdiagnose

Stand: 2026-07-22

## Ergebnis

Die native Tkinter-UI wurde real über `START_DASHBOARD.bat` gestartet und per sichtbarem Desktop-Klick bedient. Dabei wurde bewiesen, dass der bisherige Hauptbutton nicht die Protocol-v3-Kette verwendete:

- Buttonaktion: `pr12_production_starter_supervised_context_protocol_v2`;
- alter UI-Laufpfad: UI → PowerShell-Starter → Supervisor → Protocol-v2-Runner;
- die Protocol-v3-Ansicht besaß ohne Provider nur leere Default-Evidenz und zeigte veraltet `30/33`, Aufgabe 31 `NOT_STARTED`;
- der letzte sichtbare Protocol-v2-WFV-Lauf erreichte nur `0,012592 USDC/Tag`, Zielabstand `-2,987408 USDC/Tag`, und bestand die Quality Gates nicht.

Der falsche Runner wurde nicht erneut gestartet.

## Korrektur

- Die Desktop-UI lädt nun ausschließlich einen vollständig validierten create-only Task-33-Preflight aus dem externen Runtime-Root.
- Eingebetteter Drei-Markt-Datensnapshot, öffentliche Exchange-Info und aktuelle Pipelinegeneration werden erneut semantisch geprüft.
- Die Protocol-v3-Ansicht zeigt 33/33, Run-ID, Reportdigest, echte Blocker, Lifecycle, Daten-Watermark, `NO_TRADE` und `bot_start_allowed=false`.
- Der Hauptbutton heißt `Protocol v3 Backtest prüfen / starten`.
- Ein Klick öffnet bei blockiertem Preflight den exakten Blockerstatus und startet ausdrücklich nicht den alten Protocol-v2-Runner.
- Nur ein `READY_FOR_FULL_RESEARCH_RUN`-Preflight könnte die nächste Stufe erreichen; solange der reale Produktionsrunner fehlt, bleibt auch dieser Fall fail-closed.

## Reale UI-Abnahme

Der sichtbare Klick zeigte:

- `BLOCKED_INSUFFICIENT_TRIAL_HISTORY`;
- `INSUFFICIENT_TRIAL_HISTORY`;
- `MISSING_FROZEN_ACTIVE_LOOKBACKS`;
- `MISSING_FROZEN_HORIZON_POLICY`;
- `MISSING_PRODUCTION_OUTER_ORIGIN_ADAPTER`;
- Hinweis, dass Protocol v2 nicht als Protocol-v3-Test gestartet wird.

Die Protocol-v3-Detailansicht zeigte danach:

- `33/33 DONE_100 = 100.0 %`;
- Task-33-Run-ID `task33-preflight-713ccbaa3b11-ea4cb7750cea-f1782ba70088`;
- Reportdigest `846778919948f80019efc19ae131b17604a35f269c3481a07030da08d26cc616`;
- voller Research-Lauf gestartet: `False`;
- Release/Botstart: `NO_TRADE / False`.

## Historische Trial-Diagnose

Die vorhandenen mehrgigabytegroßen Protocol-v2-Reports wurden read-only per begrenzter Binärsuche geprüft. Kandidatenparameter sind vorhanden, aber die Pflichtfelder `seed` und `daily_net_mtm_usdc` fehlen. Damit können die 180 beobachteten Zeilen nicht vollständig und unabhängig attestiert werden. Der historische Lower-Bound-Status darf nicht entfernt werden.

## Verifikation

- 36 gezielte UI-/Protocol-v3-Tests grün;
- vollständige Suite: 1.330/1.330 Tests grün;
- Ruff, Python-Compile und Whitespace grün;
- keine Orders, API-Keys, privaten Endpunkte, Paper-, Testtrade- oder Live-Aktion;
- kein Research- oder Finalfenster gestartet.

## Offene Grenze

Die UI-Verkabelung ist korrigiert. Ein echter Protocol-v3-Backtest bleibt unmöglich, bis produktive Lookbacks, HorizonPolicy und der reale Task-15-bis-27-/Outer-Origin-Adapter versioniert implementiert sind. Wegen der nicht rekonstruierbaren historischen Trial-Inventur bleibt selbst danach `NO_TRADE` die einzige zulässige Freigabeentscheidung, sofern keine neue ausdrücklich genehmigte Vertragsstrategie dieses Problem rechtmäßig löst.
