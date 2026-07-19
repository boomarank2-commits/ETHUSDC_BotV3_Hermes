# Next Action – GPT 1 / neuer Codex-Chat

## Verbindlicher Abschluss davor

Aufgabe 27 ist technisch und fachlich `DONE_100`.

Abschlussbericht:
`handoff/PROTOCOL_V3_TASK_27_2026-07-19.md`

Validierter technischer Abschlusslauf:

- GitHub-CI `29706161878`;
- Head `1b9a47035ebf72d1e00508b8ed78021615363f71`;
- vollständige Suite `1.205 Tests erfolgreich`;
- Compile, PowerShell-Syntax und Whitespace erfolgreich.

Aufgabe 28 darf erst begonnen werden, nachdem auch der nachfolgende Dokumentations-Head grüne GitHub-CI besitzt.

## Exakt nächste Aufgabe

`Aufgabe 28 – Aktueller 730-Tage-Refit und Champion/Challenger/Cash-Entscheidung – NOT_STARTED`

Kein späterer Punkt darf vorgezogen werden.

## Nächster Implementierungsschritt

Vor jeder Änderung erneut vollständig lesen:

1. `AGENTS.md`;
2. `handoff/CURRENT_STATUS.md`;
3. diese Datei;
4. `handoff/PROTOCOL_V3_TASK_27_2026-07-19.md`;
5. `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`;
6. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`;
7. `configs/protocol_v3_contract.json`;
8. die Task-28-Regeln in `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`.

Danach ausschließlich Aufgabe 28 umsetzen:

1. Für einen expliziten Zielanker `T` dieselbe unveränderte Task-15-/Task-22-Auswahlpipeline exakt auf `[T-730 Tage,T)` ausführen.
2. Datenstichtag, Drei-Markt-Snapshot, Code, Pipelinegeneration, Exchange Info, Kosten, Trial-Ledger, Feature-/Regime-Fit-State, Seed und Gate-Identitäten vor dem Refit einfrieren.
3. Den aktuellen Kandidaten oder `NO_TRADE` als vollständiges `FrozenCandidateBundle` mit `as_of_day`, `valid_from=T+24h`, `valid_until`, `entry_enabled_at`, Vorgänger, Wechselgrund und Stressstatus erzeugen.
4. Keine nach `T` bekannten Daten, Outer-Ergebnisse, historischen Hindsight-Werte oder menschliche Interpretation in Auswahl oder Gate lassen.
5. Champion, Challenger und Cash deterministisch und paarweise vergleichen. Fehlende Evidenz, Fristüberschreitung, Daten-/Hashfehler oder nicht bestandene Gates ergeben fail-closed `NO_TRADE`.
6. Bis zur vorgeschriebenen frischen Evidenz bleibt jede Task-28-Ausgabe `NOT_FRESH`, `diagnostic_only`, `canonical_adoption_eligible=false` und `manual_research_shadow_start_required=true`.
7. Der bestehende kanonische Adoption-/Finalpfad darf nicht erreicht oder umgangen werden. Task 29, UI, Paper, Testtrade, Live und Orders bleiben unberührt und gesperrt.
8. Negative Tests mindestens für Zukunftsdaten, falsches 730-Tage-Fenster, veralteten Snapshot, falschen Vorgänger, abgelaufenes Bundle, T+24-Rückwirkung, manipulierte Champion-/Challenger-/Cash-Entscheidung, fehlende Stress-/Gate-Evidenz und neue Hashes über widersprüchlichen Inhalt ergänzen.
9. Erst nach gezielten Tests, vollständiger Suite, Handoff, Commit, Push und grüner GitHub-CI Aufgabe 28 auf `DONE_100` setzen und Aufgabe 29 beginnen.

## Danach verbleibende Aufgaben

- 29 – strikt orderfreier Research-Challenger-Shadow;
- 30 – vollständige UI-/Bedienzustände;
- 31 – Pipeline-Final-Evaluator für ein wirklich frisches versiegeltes Jahr;
- 32 – End-to-End-Parität, Fehler-Injektion und vollständige Abnahme;
- 33 – erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht.

## Harte Sperren

Keine Gates lockern, keine Fake-Trades oder Fake-Reports, kein Audit als Trainingsergebnis, kein Finalclaim aus historischer Diagnostik und keine Aktivierung von Orders, Paper, Testtrade oder Live. Der Bot darf nicht gestartet werden.
