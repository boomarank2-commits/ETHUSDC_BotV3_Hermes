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
- reale Einstiegspunkt-Korrektur:
  `bf9587170ab64073190529039619ec11c7dc1313`
- Pipelinegeneration:
  `protocol_v3_pipeline_sha256:ed966a90c73750a6316d011f239e713d0dcd00669520166bbae8f37275285ebf`
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

1. Einen neuen create-only Task-33-Preflight für den aktuellen Git-Head und die
   neue Pipelinegeneration erzeugen.
2. Origin 1 mit dem neuen restartfähigen CLI über alle acht Cycles ausführen.
3. Den Cross-Cycle-Origin-Report lesen und den belegten Abstand zu
   `3 USDC/Tag` sowie alle Gate-Ablehnungen diagnostizieren.
4. Danach denselben Work-Unit in den vollständigen Zwölf-Origin-Adapter und
   die realen Tasks 19 bis 27 einbinden.
5. Erst nach vollständigem Monatsprozess den UI-Startpfad und Task 33 erneut
   abnehmen.

## Kontrollierter Stopp vor PC-Abschaltung

Der reale Origin-1-Lauf unter Commit
`c846b9a36227b9f00c98ba1275072733ffa07fc5` und Pipelinegeneration
`protocol_v3_pipeline_sha256:ed966a90c73750a6316d011f239e713d0dcd00669520166bbae8f37275285ebf`
wurde auf Nutzerwunsch gestoppt.

Zustand beim Stopp:

- Prozess PID `18824` ist beendet;
- Cycle 1 hatte alle 12 Basisprofile append-only geschrieben;
- Ledger: `121` Events, `119` native Trials, `1` Cache-Reuse;
- Ledger-Head:
  `ef0a8c7e2dc76e40a820a1aa3b18a1e66daefeaf848989f860d90a5375857d15`;
- es existiert noch kein Cycle-1-Artefakt, Intent oder Checkpoint;
- es existiert kein zurückgelassener Transaction-Lock;
- die Finalisten-Quality-Evidenz war noch in Berechnung;
- keine Orders, Paper-, Testtrade- oder Live-Aktion wurde ausgelöst.

Der create-only Start-Preflight bindet noch den Head vor Cycle 1:

`C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\protocol_v3\task33\task33-preflight-c846b9a36227-ed966a90c737-64bec96c1ac5.json`

Dabei wurde eine verbleibende Crash-Recovery-Lücke sichtbar: Ohne bereits
geschriebenes Cycle-Intent blockiert die aktuelle Initial-Ledger-Prüfung den
Wiederanlauf nach partiell appendierten, aber deterministischen Cycle-Trials.
Morgen zuerst diese Lücke fail-closed schließen: Die 12 vorhandenen
Cycle-1-Trials müssen anhand Code, Pipeline, Origin, Cycle, Candidate-ID,
Seed, Fold und Tagesevidenz exakt als erwartete idempotente Prefix-Ereignisse
bewiesen werden. Unverwandte Ledger-Fortschritte müssen weiterhin blockieren.
Erst danach den Run fortsetzen. Die 12 Trials dürfen weder gelöscht noch
dupliziert oder umetikettiert werden.
