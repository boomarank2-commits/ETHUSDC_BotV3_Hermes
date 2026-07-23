# Protocol v3 – restartfähiger Production-Origin-Work-Unit

Stand: 2026-07-23

GitHub-Issue: `#21`

Branch/PR: `codex/research-resume-and-ui-state-v1`, Draft-PR `#17`

## Ergebnis

Der bislang offene Task-13-Produktionsbaustein für einen vollständigen
monatlichen Origin ist implementiert.

- Ein Origin führt exakt die acht vorab begrenzten Inner-Cycles aus.
- Jeder Cycle wird an den aktuellen Pre-Run-Manifest-, Code-, Pipeline-,
  Daten-, Kontext-, Exchange-, Fold- und permanenten Ledger-Stand gebunden.
- Der Task-13-Kandidatenslot enthält eine echte, nicht synthetische
  Task-15-Entscheidung.
- Cycle-Artefakt, create-only Intent und committed Task-13-Checkpoint bilden
  eine eindeutige Transaktion.
- Ein Neustart überspringt ausschließlich vollständig validierte und committed
  Cycles. Ein Crash nach Cycle-Artefakt oder Intent kann nur am exakt passenden
  Ledger-Head geheilt werden.
- Stale oder unklare Locks werden nicht automatisch überschrieben.
- Nach Cycle 8 werden die vollständige 96-Profil-Matrix, PBO und DSR am
  aktuellen Ledger-Head neu berechnet und die Origin-Auswahl ebenfalls
  create-only und transaktional committed.

## Task-15-Artefaktintegrität

Der Origin-Report enthält nun alle acht vollständigen Task-15-Entscheidungen.
Weil jede Entscheidung dieselbe große 96x360-Matrix transitiv bindet, werden
die kanonischen JSON-Entscheidungen deterministisch per
`gzip_base64_canonical_json_v1` gespeichert.

Je Archiv werden komprimierter und unkomprimierter SHA-256, Decision-ID,
Decision-SHA und Cycle-Index geprüft. Kleine Bindungsbelege werden exakt aus
dem validierten Vollartefakt abgeleitet. Task 23 kann die gewählte vollständige
Entscheidung wiederherstellen; der Report wächst nicht auf unkontrollierte
Gigabyte-Größe.

Der Validator prüft außerdem:

- genau acht geordnete Entscheidungen;
- exakte Code-, Pipeline-, Fold-, Kandidateninventar- und Ledger-Bindung;
- vollständige Matrix-/PBO-/Development-Support-Bindung;
- exakte Übereinstimmung der Zusammenfassungen;
- bei `READY_CANDIDATE` den lexikographisch besten Gewinner über alle Cycles;
- bei `NO_TRADE`, dass kein Cycle einen Kandidaten ausgewählt hat.

## Preflight und Ausführung

Der neue CLI ist:

`scripts/run_protocol_v3_production_origin_work_unit.py`

Ein frischer Run verlangt exakt den im Task-33-Preflight gespeicherten
Ledger-Head und Event-Count. Ein Resume verlangt, dass die Cycle-1-Identität
genau diesen ursprünglichen Head bindet.

Der CLI darf entweder einen `READY_FOR_FULL_RESEARCH_RUN`-Preflight oder
ausschließlich den einzelnen Blocker
`MISSING_PRODUCTION_OUTER_ORIGIN_ADAPTER` konsumieren. Letzteres ist nur die
kontrollierte Ausführung des Adapters, der diesen Blocker beheben soll; es
erteilt keine Task-33-, Paper-, Testtrade-, Live- oder Adoption-Freigabe.

## Verifikation

- technischer Commit:
  `d4ce888a27eaacc57f0a0200e355426688c780e0`
- Pipelinegeneration:
  `protocol_v3_pipeline_sha256:bd9731059e4808ea66e688628c1972eafe5f7d2fcf2d7f28f388f27e613de038`
- vollständige lokale Suite: `1.377/1.377` grün
- direkt betroffene Suite: `24/24` grün
- Scoped Ruff, Compile und `git diff --check`: grün
- Sicherheitsstatus: Orders, Trading-API, Paper, Testtrade, Live und Adoption
  bleiben gesperrt

## Ehrlicher Zielstatus

Das Ziel `+3 USDC/Tag` ist noch nicht erreicht und unter der neuen Generation
noch nicht real ausgewertet. Die bisherigen Origin-1-Artefakte gehören zu
älteren Code-/Pipelinegenerationen und bleiben unbrauchbar.

## Exakt nächster Schritt

1. Einen neuen create-only Task-33-Preflight für Commit `d4ce888` und die neue
   Pipelinegeneration erzeugen.
2. Origin 1 mit dem neuen restartfähigen CLI über alle acht Cycles ausführen.
3. Den Cross-Cycle-Origin-Report lesen und den belegten Abstand zu
   `3 USDC/Tag` sowie alle Gate-Ablehnungen diagnostizieren.
4. Danach denselben Work-Unit in den vollständigen Zwölf-Origin-Adapter und
   die realen Tasks 19 bis 27 einbinden.
5. Erst nach vollständigem Monatsprozess den UI-Startpfad und Task 33 erneut
   abnehmen.
