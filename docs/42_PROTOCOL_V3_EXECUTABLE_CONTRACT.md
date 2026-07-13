# 42 - Protocol v3: versionierter ausfuehrbarer Vertrag

Stand: 2026-07-13
Protocol-v3-Vertragsgeneration: `3.0.0`
Manifest: `configs/protocol_v3_contract.json`
Blueprint: `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
Umsetzungsfolge: `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`

## 1. Status und Vorrang

Dieses Dokument uebernimmt den Blueprint als ausdruecklich versionierte Protocol-v3-Vertragsgeneration. Es macht noch keine spaetere technische Aufgabe vorzeitig fertig. Ausfuehrbares Produktverhalten entsteht nur in dem Umfang, in dem die nummerierten Aufgaben aus Dokument 41 jeweils `DONE_100` erreicht haben.

Bei Widerspruechen gilt folgende Reihenfolge:

1. `AGENTS.md` fuer Arbeits-, Sicherheits- und Freigaberegeln;
2. `PROJECT_CONTRACT.md` fuer das Gesamtprodukt;
3. `docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md` fuer Kapital, Risiko, Ampel und Shadow;
4. dieses Dokument fuer Protocol-v3-Evidenz, Monatsprozess und Begriffe;
5. Dokument 40 als fachlicher Blueprint und Dokument 41 als Ausfuehrungsreihenfolge.

Das maschinenlesbare Manifest muss mit diesen Dokumenten uebereinstimmen. Eine fehlende oder widerspruechliche Version blockiert Protocol v3 fail-closed.

## 2. Unveraenderliche Produktgrenzen

- Handelsmarkt: ausschliesslich Binance Spot `ETHUSDC`.
- Richtung: ausschliesslich LONG.
- `BTCUSDC` und `ETHBTC` sind nur Kontext und koennen niemals handeln.
- Kanonisches Research-Profil: ein logisches Lot mit angefordertem und reserviertem Entry-Notional von exakt 100 USDC, kein Compounding.
- Shorts, Margin, Futures und Leverage bleiben verboten.
- Paper, Testtrade, Live, Orders, Trading-API und API-Keys bleiben technisch gesperrt.
- Das Ziel von 3 USDC pro Kalendertag ist eine Akzeptanzmetrik nach versiegelter Auswertung, niemals Loss-Funktion, Stopregel oder Anlass zur Gate-Lockerung.

## 3. Champion von Protocol v3

Der Protocol-v3-Champion ist die unveraenderte, versionierte monatliche Auswahlpipeline. Er ist kein einzelner Parametersatz.

Die Pipeline muss an jeder aeusseren Monats-Origin ausschliesslich die unmittelbar vorherigen 730 vollstaendigen UTC-Tage sehen, genau einen Kandidaten oder `NO_TRADE` einfrieren und das folgende Deployment-Intervall erst nach dem festen 24-Stunden-Delay fuer neue Entries oeffnen. Zwoelf solcher Intervalle bilden zusammen exakt 365 Prozess-OOS-Tage.

Protocol v2 und der bestehende Single-Candidate-Finalpfad bleiben erhalten. Weder ein Protocol-v2-Report noch der Single-Candidate-Finalrunner darf einen Protocol-v3-Finalstatus erzeugen.

## 4. Verbindliche Begriffe

### `monthly_process_oos`

Retrospektiver, chronologisch verketteter Pseudo-Live-Nachweis derselben monatlich refittenden Pipeline ueber zwoelf Origins und 365 Tage. Er ist auf dem bereits untersuchten Dreijahresblock `NOT_FRESH`, kein kanonischer Finalnachweis und nicht direkt adoptierbar.

### `consumed_audit`

Der Zeitraum `2025-07-08` bis einschliesslich `2026-07-07` ist dauerhaft verbraucht. Er kann niemals wieder frisch, blind oder versiegelt genannt werden.

Mit dieser Vertragsgeneration ist folgende enge Rolling-Reuse-Regel ausdruecklich beschlossen:

- reine, damals beobachtbare Rohmarktbeobachtungen duerfen in einer spaeteren Origin als normale kausale Historie erscheinen;
- fruehere PnL, Rankings, Reports, Gate-Ergebnisse, Auswahlentscheidungen und menschliche Ergebnisinterpretationen duerfen niemals in einen spaeteren Fit zurueckgespielt werden;
- der historische Protocol-v3-Prozess auf diesen Daten bleibt `diagnostic_only` und `NOT_FRESH`;
- diese Erlaubnis macht den verbrauchten Auditblock weder zu neuem Holdout noch zu kanonischer Final-Evidenz.

### `sealed_final_holdout`

Ein vor Beginn registriertes, wirklich neues und ungesehenes 365-Tage-Fenster. Die vollstaendige eingefrorene Protocol-v3-Pipeline wird darin online mit den jeweiligen Monatsrefits simuliert. Zwischenwerte bleiben bis zum Ende verborgen; danach wird der Report genau einmal geoeffnet. Nur dieser getrennte Pipeline-Finalpfad kann spaeter kanonische Protocol-v3-Final-Evidenz erzeugen.

### `forward_shadow_month`

Ein nach Einfrieren einer Pipelinegeneration wirklich neu entstandener, append-only gespeicherter Monat. Er ist frische Forward-Beobachtung, darf nicht rueckwirkend erzeugt oder veraendert werden und ist fuer sich allein kein Finalnachweis.

### `research_challenger_shadow`

Eine manuell gestartete, strikt orderfreie Beobachtung eines retrospektiven Protocol-v3-Challengers. Sie darf ausschliesslich reproduzierbare Signale, virtuelle Fills und taeglichen MTM-PnL schreiben. Sie ist niemals `canonical_adoption_eligible`, aktiviert weder Paper noch Testtrade oder Live und verwendet keine Trading-API, Kontodaten, privaten Endpunkte oder API-Keys.

### `diagnostic_only`

Evidenz darf Ursachenanalyse und technische Diagnose unterstuetzen, aber keinen kanonischen Finalstatus, keine Adoption und keine Trading-Pfad-Freigabe erzeugen.

## 5. Aktuelle Freigabegrenze

Die versionierte Rolling-Reuse-Entscheidung erlaubt die technische Implementierung des historischen Monatsprozesses und eines spaeteren manuellen `research_challenger_shadow`. Sie erteilt keine Kandidatenfreigabe im heutigen Codezustand.

Vor einer Challenger-Beobachtung muessen mindestens alle dafuer vorgesehenen Aufgaben aus Dokument 41, der vollstaendige historische Monatsprozess, alle Integritaets- und Robustheitsgates sowie die ausdrueckliche Nutzeraktion abgeschlossen sein. Bis dahin bleibt jeder Protocol-v3-Ausgang `diagnostic_only`.

Ein sichtbarer historischer Treffer von 3 USDC/Tag darf nur `historically_hit=true` setzen. `statistically_supported=true` bleibt unmoeglich, solange kein frisches, vorab registriertes und bis Tag 365 versiegeltes Pipeline-Finalfenster bestanden wurde.

## 6. Versionierungsregel

Eine Aenderung an Featuredefinitionen, Kandidatenfamilien, Suchraum, Ranking, Gates, Kostenmodell, Simulator, Boundary-Regeln oder Evidenzbedeutung erzeugt eine neue Pipelinegeneration. Monatliche Re-Fits derselben eingefrorenen Pipeline bleiben Teil derselben Generation.

Der permanente Trial-Zaehler wird niemals durch eine neue Generation zurueckgesetzt. Bereits sichtbare Forward-Monate duerfen niemals nachtraeglich in ein `sealed_final_holdout` aufgenommen werden.

## 7. Fail-closed-Vertrag

Protocol v3 blockiert, wenn:

- Manifest, Dokumentversion oder Vertragsgeneration fehlt oder widerspruechlich ist;
- der verbrauchte Auditblock als frisch oder adoptierbar markiert wird;
- fruehere Ergebnisdaten in spaetere Fits gelangen;
- ein Legacy-Runner einen Protocol-v3-Finalstatus beansprucht;
- ein Research-Challenger Orders, Trading-API, Paper, Testtrade oder Live freigeben soll;
- Sicherheits-, Identitaets- oder Evidenzfelder fehlen.

Das korrekte Ergebnis bei fehlender oder widerspruechlicher Evidenz ist `NO_TRADE`, `TARGET_NOT_REACHED`, `NO_EDGE_FOUND` oder ein expliziter Blocker, niemals eine stillschweigende Lockerung.
