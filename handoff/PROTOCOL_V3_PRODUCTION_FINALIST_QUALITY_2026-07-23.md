# Protocol v3 – reale Finalisten-Qualität und Task-15-Bindung

Stand: 2026-07-23

GitHub-Issue: `#21`

Branch/PR: `codex/research-resume-and-ui-state-v1`, Draft-PR `#17`

## Ergebnis

Der bisher belegte kleinste Blocker im Produktionspfad ist geschlossen:

- Jeder der zwei Finalisten eines Inner-Cycles erhält echte,
  training-only Quality-Evidenz.
- Die Evidenz enthält die exakten sechs 60-Tage-WFV-Folds, einen
  kontinuierlichen 360-Tage-Validierungslauf, den vollständigen
  730-Tage-Trainingslauf, Joint- und Slippage-Stress, alle eingefrorenen
  numerischen Parameternachbarn sowie Rolling-, Temporal- und
  Regime-Evidenz.
- Sämtliche Simulationen verwenden den Protocol-v3-Intrabar-Simulator,
  Binance-Regeln sowie die eingefrorenen Kostenprofile.
- Der Produktions-CLI lädt dafür den vollständigen 730-Tage-
  Entwicklungszeitraum und nicht mehr nur die 360 Validierungstage.
- Task 15 wird nicht mehr durch vom Aufrufer gelieferte Entscheidungen
  gespeist. Erst nach Vorliegen aller acht Cycles werden die vollständige
  96-Profil-Matrix, PBO und DSR neu berechnet und daraus intern acht echte,
  vollständig gebundene Task-15-Entscheidungen erzeugt.
- Ein Kandidat kann nur bei vollständiger Matrix-, PBO-, DSR- und
  Quality-Gate-Evidenz konkurrieren. Fixture-Evidenz bleibt im
  Produktionspfad verboten.

## DSR-Performance ohne Formeländerung

Die skalare DSR-Berechnung hatte dieselben Trial-Statistiken und dieselbe
Korrelationsmatrix für jedes Profil erneut aufgebaut. Das machte die
vollständige 96-Profil-Origin-Auswahl unnötig teuer.

Der neue versionierte Batch-Nachweis berechnet Trial-Inventar,
Korrelationsmatrix, `N_eff`, `sigma_sr` und `SR0` einmal gemeinsam. Die
profilbezogene DSR-Formel bleibt unverändert. Tests vergleichen Batch- und
Skalarergebnis exakt und der Validator berechnet die gemeinsamen und
profilbezogenen Werte erneut.

## Verifikation

- technischer Commit:
  `c5e9c0997385462148d3b7ba86e51db735edb6f1`
- Pipelinegeneration:
  `protocol_v3_pipeline_sha256:9e5e6e9d9491ac7fffd5dc23ce17d7bdf9f78a50cd9c9db587c1dcd924f5fe41`
- direkt betroffene Suite: `60/60` grün
- vollständige lokale Suite: `1.371/1.371` grün
- Scoped Ruff, Compile und `git diff --check`: grün
- Sicherheitsstatus: keine Orders, keine API-Keys, kein Paper, Testtrade,
  Live oder Adoption

## Ehrlicher Zielstatus

Das Ziel `+3 USDC/Tag` ist mit diesem Commit weder ausgewertet noch erreicht.
Die alten Origin-1-Artefakte der Commits `950c763` und `8fcfb6e` gehören zu
älteren Pipelinegenerationen. Sie dürfen nicht umetikettiert oder in die neue
Auswahl gemischt werden.

## Exakt nächster Produktionsschritt

Vor einem neuen Lauf fehlt weiterhin der vollständige Task-13-Origin-
Work-Unit, der Registration, Claim, Pre-Run-Manifest, Run-Fingerprint,
Pipelinegeneration, Code-Commit, Trial-Ledger-Head, acht Cycle-Artefakte und
die Origin-Auswahl atomar bindet und resumefähig persistiert.

Danach:

1. Origin 1 unter der neuen Generation genau einmal über acht Cycles ausführen;
2. die echte Cross-Cycle-Task-15-Auswahl ausführen und Ablehnungsgründe
   auswerten;
3. Tasks 19 bis 27 auf reale Daten und den ausgewählten Kandidaten bzw.
   `NO_TRADE` anwenden;
4. Origins 2 bis 12 ausführen;
5. den create-only Task-33-Preflight und anschließend den UI-gestarteten
   realistischen Monatsprozess erneut prüfen.

Bis dieser Pfad reale, kausale und kostenbereinigte Evidenz liefert, bleibt
Task 33 blockiert und der Bot gesperrt.
