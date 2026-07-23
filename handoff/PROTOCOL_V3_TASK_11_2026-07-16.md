# Protocol v3 – Handoff Aufgabe 11/33

Stand: 2026-07-16

## Status

`Protocol v3: Aufgabe 11/33 – Protocol-v3-Report-Schemas und Evidenzbedeutung – DONE_100`

Gesamtfortschritt: `11/33 = 33,33 %`.

Exakt nächste Aufgabe: `Aufgabe 12 – Kompakte Artefaktarchitektur`.

## Ausgangsstand und adversariales Review

Verbindlicher Task-11-Ausgangscommit war `a7b7a143a2e303898286ac7266dff45e498a156a`.

Vor Aufgabe 12 wurde Aufgabe 11 erneut am echten Code geprüft. Die Report- und Registrierungssemantik, Root-/Symlink-/Traversal-Sperren, Legacy-Ablehnung, Pipelinebindung und automatische Berücksichtigung persistierter Forward-Monate waren fachlich korrekt. Gefunden wurde jedoch eine Integrationslücke: Die implementierte Reportoberfläche besaß keinen ausdrücklich stabilen öffentlichen Protocol-v3-Fassadenmodulnamen, obwohl das Handoff eine öffentliche Builder-Schnittstelle behauptete.

## Korrektur

Die Korrektur ergänzt:

- `src/ethusdc_bot/protocol_v3/reporting_api.py` als stabile, ausschließlich validierte Task-11-Fassade;
- `tests/unit/test_protocol_v3_reporting_public_api.py` als Export- und Fail-closed-Regressionstest;
- Pipelinebindung von `reporting_api.py` in `configs/protocol_v3_pipeline_contract.json`.

Die Fassade re-exportiert exakt die validierte Oberfläche aus `reporting.py`. Sie bietet keinen Legacy-Final-, Shadow-Adoptions-, Order-, Paper-, Testtrade- oder Live-Pfad.

Ein temporärer GitHub-Contents-Schreibfehler erzeugte den Dokumentationscommit `f950ba87d3145f914aeb68c606b79d863c90ca98`, der die Handoff-Datei kurzzeitig durch einen Platzhalter ersetzte. Dieser reine Dokumentationsfehler wurde im unmittelbar folgenden Korrekturcommit vollständig repariert; Produktionscode und Evidenzsemantik waren davon nicht betroffen.

## Task-11-Vertrag und Evidenzbedeutung

Versioniert bleiben:

- Vertrag: `protocol_v3_evidence_reports_v1`;
- Report-Schema: `protocol_v3_report_v1`;
- Forward-Registrierung: `protocol_v3_evidence_window_registration_v1`;
- Protocol-Version: `3.0.0`.

Reportklassen und feste Roots:

- `protocol_v3_research` → `reports/protocol_v3/research`;
- `monthly_process_oos` → `reports/protocol_v3/monthly_process_oos`;
- `research_challenger_shadow` → `reports/protocol_v3/research_challenger_shadow`;
- `forward_shadow_month` → `reports/protocol_v3/forward_shadow_month`;
- `protocol_v3_pipeline_final` → `reports/protocol_v3/pipeline_final`.

`sealed_final_holdout` bleibt ausschließlich die Evidenzfensterklasse des späteren Task-31-Finalreports. Der Legacy-Typ `final_evaluation` wird nicht verwendet.

Für `monthly_process_oos` gilt weiterhin ausschließlich:

```text
historically_hit = process_oos_net_usdc / 365 >= 3.0
```

Ein historischer Treffer erzeugt weder Freshness noch statistische Unterstützung oder Adoption. Bis Aufgabe 27 und 31 bleiben `fresh_pre_registered_sealed_365`, `sealed_bootstrap_target_supported`, `statistically_supported` und `canonical_adoption_eligible` zwingend falsch.

Forward-Monate werden vor Beginn create-only registriert, beim Reload semantisch revalidiert und bei jeder späteren Finalfensterprüfung direkt aus der festen Registrierungsroot gelesen. Ein Aufrufer kann sichtbare Forward-Monate nicht durch Weglassen verbergen.

## Tests und Safety

Task 11 deckt weiterhin striktes JSON, Duplicate-Key-/NaN-/Infinity-Ablehnung, Root- und Symlink-Sicherheit, Persistenz/Reload, Manipulation, Legacy-Ablehnung und Forward-/Finalfenstertrennung ab. Die neue Fassadenprüfung ergänzt die reale öffentliche Importkette.

Unverändert gesperrt:

- Orders;
- Trading-API und private Endpunkte;
- API-Keys;
- Paper;
- Testtrade;
- Live;
- Shorts, Margin, Futures und Leverage.

## Nicht vorgezogen

Keine kompakte Artefaktarchitektur, kein Cache-/Resume-System, kein Fold-Planer, kein Challenger-Controller, kein Final-Evaluator und keine UI wurden in Task 11 implementiert.

## Exakt nächstes Ticket

`Aufgabe 12 – Kompakte Artefaktarchitektur`
