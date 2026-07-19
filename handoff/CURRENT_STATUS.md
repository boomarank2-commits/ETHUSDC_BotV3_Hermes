# Current Status – Protocol v3

Updated: 2026-07-19

## GitHub-Wahrheit

- Repository: `boomarank2-commits/ETHUSDC_BotV3_Hermes`
- Branch: `codex/research-resume-and-ui-state-v1`
- Draft PR: `#17`
- letzter fachlicher Commit: `a65d18048bb404a5da9b3a26f2f19a7e2c160088`
- GitHub-CI: Run `29700342819` erfolgreich, 1.197 Tests
- lokaler Branch und Origin waren nach dem Push identisch

## Protocol-v3-Fortschritt

`26/33 = 78,79 % DONE_100`.

Aufgabe 27 ist aktiv: `IN_PROGRESS`.

In diesem Arbeitsblock abgeschlossen und CI-bestätigt:

- Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State;
- Aufgabe 25 – tägliches MTM-Ledger und getrennte Zeitaggregationen;
- Aufgabe-25-Korrektur – `NO_TRADE`/nicht routbare Bundles können keine Tradezeilen erzeugen;
- Aufgabe 26 – fail-closed Monthly Quality Gate, Stress und Pflichtmetriken.

Für Aufgabe 27 sind Manifest/Seed, 10.000er Circular-Stationary-Bootstrap für `L={5,10,20}`, 500. Ordnungsstatistik, Capture-Ratios und historische Safety-Locks implementiert und CI-grün. Aufgabe 27 ist noch nicht fertig, weil die beiden Benchmarkwerte noch direkt an echte Hindsight-Solver statt nur an content-gehashte Evidenz gebunden werden müssen.

## Sicherheitswahrheit

- Der vorhandene Zeitraum `2025-07-08..2026-07-07` bleibt `consumed_audit` und `NOT_FRESH`.
- Historical Bootstrap und Hindsight bleiben `diagnostic_only`.
- Kein Protocol-v3-Finalstatus vor Aufgabe 31 auf einem wirklich neuen `sealed_final_holdout`.
- Keine automatische Adoption.
- API-Keys, Trading-API, Orders, Paper, Testtrade und Live bleiben gesperrt.
- Der Bot darf noch nicht gestartet oder als Zielerreicher bezeichnet werden.

## Einstieg für GPT 1 / neuen Chat

1. Repository und Branch oben auschecken; PR #17 lesen.
2. `AGENTS.md`, `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` und `handoff/PROTOCOL_V3_TASK_27_IN_PROGRESS_2026-07-19.md` vollständig lesen.
3. Prüfen, dass HEAD mindestens `a65d180` enthält und der Worktree sauber ist.
4. Ausschließlich Aufgabe 27 fortsetzen; Aufgabe 28 darf erst nach Task-27-Tests, Handoff, Commit, Push und grüner CI beginnen.
5. Keine Benchmarkzahl aus Reports, menschlicher Interpretation oder Caller-Claims übernehmen.

Der exakte technische Auftrag steht in `handoff/NEXT_ACTION.md`.
