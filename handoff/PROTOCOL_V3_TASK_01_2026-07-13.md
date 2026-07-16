# Protocol v3 – Handoff Aufgabe 1/33

Stand: 2026-07-13

## Status

`Protocol v3: Aufgabe 1/33 – Protocol-v3-Vertrag versioniert übernehmen – DONE_100`

Gesamtfortschritt: `1/33 = 3,03 %`

Exakt nächste Aufgabe: `Aufgabe 2 – Monatskalender und Boundary-Vertrag implementieren`.

Codex darf Aufgabe 2 erst beginnen, nachdem der Branch lokal auf den unten genannten finalen PR-Head gezogen und ein sauberer Arbeitsbaum bestätigt wurde.

## Was umgesetzt wurde

Protocol v3 ist als ausdruecklich versionierte Vertragsgeneration `3.0.0` uebernommen. Der fachliche Blueprint bleibt Quelle; der neue ausfuehrbare Vertrag und das maschinenlesbare Manifest definieren fail-closed, was die Begriffe und Evidenzklassen bedeuten.

Die zentrale Vertragsentscheidung lautet:

- Der Zeitraum `2025-07-08..2026-07-07` bleibt dauerhaft `consumed_audit` und `NOT_FRESH`.
- Reine, damals kausal beobachtbare Rohmarktwerte duerfen in spaeteren Monats-Origins als Historie erscheinen.
- Fruehere PnL, Rankings, Reports, Gate-Ergebnisse, Auswahlentscheidungen und menschliche Ergebnisinterpretationen duerfen niemals in einen spaeteren Fit zurueckgespielt werden.
- Der historische `monthly_process_oos` bleibt `diagnostic_only`, nicht adoptierbar und kein Protocol-v3-Finalnachweis.
- Ein `research_challenger_shadow` ist spaeter nur separat, manuell und strikt orderfrei zulaessig.
- Ein kanonischer Protocol-v3-Finalstatus erfordert einen getrennten Pipeline-Final-Evaluator auf einem vorab registrierten, wirklich neuen und 365 Tage versiegelten `sealed_final_holdout`.
- Protocol v2 und der bestehende Single-Candidate-Finalpfad bleiben erhalten, duerfen aber keinen Protocol-v3-Finalstatus erzeugen.

## Geaenderte und neue Dateien

- `AGENTS.md`
  - Protocol-v3-Arbeits- und Evidenzregeln ergaenzt.
  - Strikte Aufgabenreihenfolge und Safety-/Freshness-Sperren festgeschrieben.
- `PROJECT_CONTRACT.md`
  - Monthly-Refit-Pipeline als neue Vertragsgeneration uebernommen.
  - Rolling-Reuse-Grenzen und Finaltrennung dokumentiert.
- `docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md`
  - Evidenz- und Shadow-Klassen getrennt.
  - Research Challenger vom kanonischen Adoption-Shadow getrennt.
- `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
  - Neuer kanonischer Protocol-v3-Zusatzvertrag.
- `configs/protocol_v3_contract.json`
  - Maschinenlesbares Manifest fuer Version, Evidenzklassen, Legacy-Trennung, Zielpolitik und Safety.
- `src/ethusdc_bot/contracts/__init__.py`
  - Export des Validators.
- `src/ethusdc_bot/contracts/protocol_v3.py`
  - Fail-closed-Validator fuer fehlende oder widerspruechliche Vertragsfelder und Dokumentmarker.
  - Plattformunabhaengige Pfadpruefung fuer Windows und CI.
- `tests/unit/test_protocol_v3_contract.py`
  - Positiv-, Negativ-, Missing-Version-, Freshness-, Result-Feedback-, Legacy-Final- und Challenger-Safety-Tests.
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`
  - Aufgabe 1 auf `DONE_100`, Aufgabe 2 auf `NOT_STARTED` gesetzt.

## Tests und Evidenz

### Korrekturstand 2026-07-16

Der Pipelineaufbau ruft den Repository-Vertragsvalidator jetzt selbst fail-closed auf. `AGENTS.md`, `PROJECT_CONTRACT.md`, `docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md`, `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`, `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md` und das Protocol-v3-Manifest sind als exakte Pfade und SHA-256-Quelldigests Teil der Pipelinegeneration. Fehlender Vertrag, falscher Marker oder eine inhaltliche Änderung erzeugt damit einen Fehler beziehungsweise eine neue Generation; die Dokumentverträge sind nicht länger nur außerhalb der Pipeline geprüft.

Die vollstaendige Review-CI auf Implementierungscommit `e373c9ade3ae149bb413b092929d698ffad8e98a` war vollstaendig gruen:

- komplette Pytest-Suite: gruen;
- neue Protocol-v3-Vertragstests: Bestandteil der kompletten Suite und gruen;
- Python-Quellbaum kompilierbar: gruen;
- PowerShell-Syntax: gruen;
- `git diff --check`/Whitespace: gruen.

Rohdaten- oder Backtestlauf war fuer diese reine Vertrags- und Validatoraufgabe nicht fachlich relevant und wurde bewusst nicht vorgezogen.

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 2 oder spaeter wurde vorgezogen. Insbesondere noch nicht implementiert:

- Monats-Boundary-Objekte;
- zwoelf Origins;
- Leap-/Non-Leap-Kalender;
- T+24h-Aktivierungslogik;
- Trial-Ledger;
- Datensnapshot, Simulatoraenderungen, Router oder Shadow;
- neue Orders, Paper, Testtrade, Live oder API-Nutzung.

## Safety

Unveraendert gesperrt:

- Orders;
- Trading-API;
- API-Keys und Kontodaten;
- Paper;
- Testtrade;
- Live;
- finaler Holdout.

## Codex-Startanweisung fuer spaeter

1. Branch `codex/research-resume-and-ui-state-v1` auf den aktuellen PR-Head ziehen.
2. `git status` muss sauber sein und `HEAD` muss dem GitHub-PR-Head entsprechen.
3. Vollstaendige Tests lokal ausfuehren oder mindestens den GitHub-CI-Stand nachvollziehen.
4. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`, `configs/protocol_v3_contract.json` und dieses Handoff lesen.
5. Danach ausschliesslich Aufgabe 2 beginnen.
6. Keine Pipelinegeneration, Trial-Ledger-, Daten-, Simulator-, Router- oder UI-Arbeit vorziehen.

## Exakt naechstes Ticket

`Aufgabe 2 – Monatskalender und Boundary-Vertrag implementieren`

Ziel ist eine reine, deterministische Boundary-Schicht mit exakt zwoelf Origins, 730 Entwicklungstagen je Origin, 365 lueckenlosen Prozess-OOS-Tagen und fester `T+24h`-Entry-Geltung. Abnahme nur mit Leap-/Non-Leap-, Late-Button-, Duplikat-, Luecken- und Training/OOS-Ueberlappungstests.
