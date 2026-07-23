# Protocol v3 – GPT-Ausführungs- und Prüfanweisung für Aufgaben 11 bis 20

Stand: 2026-07-16

Technisch korrigierter Ausgangsstand: `202e629f6b736e4bd1ff5cd53aeb9096fbf5a167`

Arbeitsbranch: `codex/research-resume-and-ui-state-v1`

Pull Request: `#17`

## 1. Zweck und Geltung

Dieses Dokument ist eine operative Qualitätsanweisung für GPT bei der Umsetzung
der Protocol-v3-Aufgaben 11 bis 20. Es ändert keine Produktanforderung und zieht
keine der Aufgaben technisch vor. Bei Widersprüchen gelten weiterhin in dieser
Reihenfolge:

1. `AGENTS.md`;
2. `PROJECT_CONTRACT.md`;
3. `docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md`;
4. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`;
5. `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`;
6. `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`;
7. dieses Dokument als Ausführungs- und Reviewhilfe.

Der Commit dieses Dokuments ist ein direkter Nachfolger des oben genannten
korrigierten Ausgangsstands. GPT muss vor Aufgabe 11 den **aktuellen Remote-Head
des Arbeitsbranches, der dieses Dokument enthält**, verwenden. Ein älterer
lokaler oder zwischengespeicherter Stand ist unzulässig.

## 2. Vom Nutzer verlangter Ablauf

GPT bearbeitet immer genau eine Aufgabe. Es darf Aufgaben 11 bis 20 nicht in
einem einzigen Arbeitsblock vorwegnehmen.

Der Ablauf lautet verbindlich:

1. Aufgabe 11 implementieren, selbst prüfen, committen, pushen und die CI
   abwarten.
2. Beim Auftrag zu Aufgabe 12 zuerst Aufgabe 11 adversarial kontrollieren.
   Gefundene Fehler werden vor Aufgabe 12 korrigiert, getestet, committed und
   gepusht. Erst danach beginnt Aufgabe 12.
3. Beim Auftrag zu Aufgabe 13 zuerst Aufgabe 12 auf dieselbe Weise kontrollieren.
4. Dieses Muster gilt lückenlos bis Aufgabe 20.
5. Nach Aufgabe 20 Aufgabe 20 selbst vollständig kontrollieren und einen
   kumulativen Bericht über Aufgaben 11 bis 20 erstellen.
6. Danach stoppen. Aufgabe 21 beginnt erst nach der unabhängigen Prüfung durch
   Codex und einer neuen Nutzerfreigabe.

Eine grüne CI der Voraufgabe ersetzt deren adversariales Review nicht. Das
Review prüft, ob die Tests überhaupt die richtige Aussage beweisen.

## 3. Git- und GitHub-Vertrag pro Aufgabe

Vor jeder Aufgabe:

- aktuellen Remote-Branch abrufen;
- lokalen und entfernten Head vergleichen;
- `git status --short` prüfen;
- keine fremden oder ungesicherten Änderungen überschreiben;
- bestehenden Branch und Draft-PR #17 weiterverwenden;
- keinen neuen PR eröffnen;
- nicht mergen;
- kein Force-Push, kein Reset und kein Umschreiben bestehender Historie.

Nach jeder Aufgabe beziehungsweise jeder vorgeschalteten Korrektur:

- nur die beabsichtigten Dateien stagen;
- einen eigenen, klaren Commit erstellen;
- sofort auf denselben Branch pushen;
- Remote-Head gegen den lokalen Commit prüfen;
- Review CI vollständig abwarten;
- erst bei grüner CI und sauberem Arbeitsbaum den Status `DONE_100` setzen.

Eine nachträgliche Korrektur der Voraufgabe erhält einen eigenen Korrekturcommit.
Sie darf nicht still im Commit der nächsten Aufgabe versteckt werden.

## 4. Verbindliches Review der unmittelbar vorherigen Aufgabe

Vor Aufgabe `N` mit `N > 11` muss GPT Aufgabe `N-1` anhand des aktuellen Codes,
nicht anhand ihres Handoffs, kontrollieren. Mindestens folgende Fragen sind zu
beantworten:

1. Ist die Anforderung vollständig im echten öffentlichen Produktionspfad
   angeschlossen oder existiert nur eine isolierte Funktion?
2. Kann ein Aufrufer Freshness, Vollständigkeit, Provenienz, Trialzahl,
   Attestierung, Identität oder Safety durch ein frei gesetztes Feld behaupten?
3. Werden persistierte Daten beim Wiederladen sowohl kryptografisch als auch
   semantisch aus den eigentlichen Quelldaten revalidiert?
4. Wird eine Entscheidung gegen exakt den Ledger-/Snapshot-/Manifeststand
   geprüft, der zum Entscheidungszeitpunkt galt, oder können spätere Ereignisse
   sie rückwirkend verändern?
5. Sind alle Vertrags- und Schemaversionen in Producer, Consumer, Pipeline,
   Fingerprint, Cache-/Resume-Key, Tests und Dokumentation synchron?
6. Prüfen mindestens ein Integrations- und ein Manipulationstest den realen
   Pfad ohne Monkeypatch der zentralen Identitäts- oder Validierungsfunktion?
7. Werden fehlende, zusätzliche, doppelte, veraltete, zukünftige, nichtfinite
   oder widersprüchliche Werte fail-closed behandelt?
8. Bleiben Pfade innerhalb ihrer vorgesehenen Storage-Root und sind
   Traversal-/Symlink-/Alias-Verwechslungen ausgeschlossen?
9. Ist Determinismus über Wiederholung, Prozessneustart, Serialisierung und
   eine veränderte Eingabereihenfolge belegt?
10. Behauptet das Handoff mehr als tatsächlich implementiert ist, etwa einen
    Controller, obwohl nur ein Adaptername existiert?
11. Wurde keine spätere Aufgabe vorgezogen und kein bestehendes strengeres Gate
    gelockert?
12. Bleiben Orders, Trading-API, API-Keys, Paper, Testtrade und Live technisch
    gesperrt?

Wenn eine Antwort nicht beweisbar ist, ist die Voraufgabe nicht `DONE_100`.
GPT korrigiert nur den konkreten Fehler, führt die betroffenen Tests und danach
die vollständige Suite aus, aktualisiert das Handoff und wartet die CI ab.

## 5. Fehlerklassen aus der Korrektur von Aufgaben 1 bis 10

Die folgenden Fehler sind bereits aufgetreten und dürfen sich nicht wiederholen:

### 5.1 Schnittstelle ohne echte Verkabelung

Ein exportierter Name, ein Pfadparameter oder vier Wrapper beweisen nicht, dass
Research, Replay, Cache, Resume oder ein späterer Controller denselben Kern
verwenden. Der Abnahmetest muss vom echten Einstiegspunkt bis zum validierten
Ergebnis beziehungsweise Artefakt laufen.

### 5.2 Vom Aufrufer behauptete Sicherheitswahrheit

Booleans, Hexstrings, Zähler oder Statuswerte des Aufrufers dürfen keine
Evidenz freischalten. Sicherheitsrelevante Werte müssen aus dem validierten
Ledger, versiegelten Artefakten und deren tatsächlichen Inhalten entstehen.

### 5.3 Hashprüfung ohne Inhalts- und Bedeutungsprüfung

Ein äußerer SHA-256 genügt nicht. Nach dem Laden müssen Schema, zulässige
Felder, Referenzen, Zeitgrenzen, Marktdigests, Tagesinhalt und fachliche
Invarianten erneut geprüft werden.

### 5.4 Falscher Bewertungszeitpunkt

Ein später hinzugefügtes Ledger-Ereignis darf einen früheren Gate-Zustand nicht
rückwirkend verändern. Jede Entscheidung bindet den exakten Head und die
Position im append-only Verlauf, die damals galten.

### 5.5 Unvollständige Versionsanhebung

Bei einer inkompatiblen Korrektur müssen Schema, Vertragsversion, Payload,
Pipeline-Komponente, Run-Fingerprint, Cache-/Resume-Key, alle Consumer, Tests
und Handoffs gemeinsam aktualisiert werden. Alte Artefakte dürfen nicht
stillschweigend als kompatibel gelten.

### 5.6 Nur synthetische statt reale Semantik

Tests müssen reale Randfälle des externen Vertrags abbilden. Beispiel aus den
vorherigen Aufgaben: Binance darf einen einzelnen Mengenfilter mit
`stepSize=0` deaktivieren. Eine künstlich strengere Fixture ist kein Beweis für
korrektes Produktionsverhalten.

### 5.7 Fehlende Werte als günstiger Default

Ein fehlendes Resultat ist nicht dasselbe wie ein echter No-Trade-Tag mit
`0 PnL`. Fehlende Evidenz darf weder zu Null aufgefüllt noch als bestanden
interpretiert werden.

### 5.8 Dokumentation als Erfolgssimulation

`DONE_100`, `integriert`, `bitgleich`, `fresh`, `final` und `adoptierbar` dürfen
nur verwendet werden, wenn der konkrete technische Pfad und passende Tests
existieren. Reservierte spätere Pfadnamen sind keine implementierten Controller.

## 6. Allgemeine Definition von DONE_100 für Aufgaben 11 bis 20

Eine Aufgabe ist erst vollständig, wenn:

- ihr eigener versionierter Vertrag beziehungsweise ihr Schema existiert;
- die Pipelinegeneration alle fachlich relevanten neuen Verträge und Quellen
  bindet;
- die öffentliche Protocol-v3-Schnittstelle nur validierte Objekte akzeptiert;
- mindestens Positiv-, Negativ-, Manipulations-, Serialisierungs-/Reload- und
  Determinismustests vorhanden sind;
- ein echter Integrationspfad ohne zentrale Mock-Abkürzung getestet ist;
- fehlende Evidenz einen Blocker oder `NO_TRADE` erzeugt;
- `py -3.12 -m pytest -q` vollständig grün ist;
- `py -3.12 -m compileall -q src` grün ist;
- `git diff --check` grün ist;
- relevante JSON-Dateien tatsächlich parsebar sind;
- Safety-Pfade unverändert gesperrt sind;
- das Handoff Implementiertes und Aufgeschobenes getrennt beschreibt;
- Commit, Push, Remote-Head und Review CI nachweisbar sind.

Tests, die lediglich den gerade geschriebenen Konstantenwert zurücklesen, sind
keine fachliche Abnahme. Golden Fixtures müssen unabhängig berechnete erwartete
Werte besitzen.

Für bewusst reine Kerne wie Foldplanung oder `select_candidate(...)` bleibt
I/O außerhalb der Funktion. Persistenz-/Reload-Tests gelten dort für den
getrennten Adapter beziehungsweise das konsumierte Evidenzobjekt; ein eigener
persistierter Pfad kann im Handoff korrekt `NOT_APPLICABLE_PURE_CORE` heißen.

## 7. Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung

### Muss umgesetzt werden

- getrennte versionierte Reportarten und Storage-Roots mindestens für:
  - `protocol_v3_research` für technische beziehungsweise historische
    Research-Diagnose;
  - `monthly_process_oos`;
  - `research_challenger_shadow`;
  - `forward_shadow_month`;
  - den späteren eindeutig als Protocol v3 benannten Pipeline-Finalreport;
- `sealed_final_holdout` ist die gebundene Evidenzfensterklasse des späteren
  Pipeline-Finalreports, nicht selbst ein austauschbarer Reporttyp;
- der Protocol-v3-Pipeline-Finalreport darf insbesondere nicht den
  Legacy-Typnamen `final_evaluation` übernehmen;
- eindeutige `artifact_kind`-, Schema- und Protocol-v3-Versionsfelder;
- maschinell erzwungene Trennung von:
  - `historically_hit`;
  - `historical_bootstrap_lower_bound`;
  - `freshness`;
  - `sealed_bootstrap_target_supported`;
  - `statistically_supported`;
  - `canonical_adoption_eligible`;
- `monthly_process_oos` auf vorhandener Historie immer `NOT_FRESH`,
  `diagnostic_only` und nicht adoptierbar;
- `research_challenger_shadow` immer orderfrei und nicht kanonisch
  adoptierbar;
- `forward_shadow_month` als neue Forward-Beobachtung, aber niemals als
  alleiniger Finalnachweis;
- Protocol-v3-Finalstatus nur für den späteren, vorregistrierten und wirklich
  neuen Pipeline-Finalpfad aus Aufgabe 31;
- harte Legacy-Trennung: Protocol-v2- und Single-Candidate-Reports dürfen
  keinen Protocol-v3-Finalstatus erhalten;
- sichtbare Forward-Monate dürfen nie nachträglich Bestandteil eines
  `sealed_final_holdout` werden;
- striktes JSON: exakte Schlüssel und Versionen, keine Duplicate Keys,
  unbekannten sicherheitsrelevanten Felder, `NaN` oder Infinity.

Die Evidenzinvarianten sind keine frei setzbaren Booleans:

```text
historically_hit = process_oos_net_usdc / 365 >= 3.0

statistically_supported =
    fresh_pre_registered_sealed_365
    and sealed_bootstrap_target_supported
```

`fresh_pre_registered_sealed_365` benötigt später einen maschinell versiegelten
Beleg aus Aufgabe 31. Bis dahin und auf verbrauchter Historie bleibt es ebenso
wie `statistically_supported` zwingend falsch.

### Besonders zu testen

- verbrauchter Audit wird durch manipulierte Statusfelder nicht frisch;
- historischer Zieltreffer setzt nicht automatisch statistische Unterstützung;
- ein Forward-Monat setzt keinen Finalstatus;
- ein Research-Challenger wird weder adoptierbar noch Paper-/Live-fähig;
- Legacy-Report mit ähnlich benannten Feldern wird abgelehnt;
- jeder Protocol-v3-Report wird vom bestehenden Legacy-Pfad
  `validate_final_evaluation_report`/`adopt_for_shadow` abgelehnt;
- falsche Storage-Root, falsches Schema oder vertauschte Reportklasse blockiert;
- zusätzliche sicherheitsrelevante Felder werden nicht still ignoriert;
- serialize → persist → reload → validate erhält exakt dieselbe Bedeutung.

### Nicht vorziehen

- keine kompakte Artefaktablage aus Aufgabe 12;
- kein transaktionales Resume aus Aufgabe 13;
- kein Research-Challenger-Controller aus Aufgabe 29;
- keine UI aus Aufgabe 30;
- kein Pipeline-Final-Evaluator aus Aufgabe 31.

Ein Schema für einen späteren Report ist erlaubt. Es beweist nicht, dass sein
späterer Producer oder Controller bereits existiert.

## 8. Aufgabe 12 – Kompakte Artefaktarchitektur

### Muss umgesetzt werden

- kleiner kanonischer JSON-Index statt eingebetteter Millionen-Bar-Reihen;
- getrennte, deduplizierte Artefakte für mindestens:
  - Trades;
  - tägliche Netto-MTM-PnL einschließlich echter Nulltage;
  - Equity-/Underwater-Daten;
  - Fold-/Kandidaten-/Diagnostikevidenz;
- jede Referenz bindet mindestens Artefaktart, Schema, SHA-256, Bytegröße,
  logische Zeilenzahl beziehungsweise Kardinalität und Provenienz;
- die Provenienz bindet konkret Elternreport, vollständigen Run-Fingerprint,
  Pipelinegeneration und Work-Unit-Identität;
- content-addressed Dateiname oder Schlüssel muss aus den tatsächlichen
  kanonischen Bytes entstehen;
- Digest, Bytegröße und Kardinalität werden vom Store aus den geschriebenen
  Bytes berechnet und nicht als Behauptung des Aufrufers übernommen;
- Index und Referenzen dürfen keine Rohkerzen oder dieselbe lange Kurve mehrfach
  einbetten;
- referenzierte Pfade müssen relativ zur vorgesehenen Root und gegen
  Traversal/Alias/Symlink-Flucht abgesichert sein;
- Laufartefakte und große Daten bleiben außerhalb von Git;
- Deduplikation darf nur bei identischen Bytes und identischer zulässiger
  Artefaktsemantik greifen.
- ein bereits vorhandenes Objekt unter demselben Digest wird vollständig
  gelesen und semantisch validiert, niemals blind überschrieben oder als
  Cache-Hit akzeptiert;
- alle Objekte werden vor Veröffentlichung ihres Index vollständig geschrieben,
  geflusht, wieder eingelesen und validiert;
- da der Blueprint keine konkrete MB-Grenze vorgibt, muss Task 12 eine
  versionierte Größenpolitik begründen und mit repräsentativer synthetischer
  12-Origin-Last prüfen, statt willkürlich eine Zahl zu erfinden.

### Besonders zu testen

- fehlende, verkürzte, manipulierte oder vertauschte Referenz blockiert;
- korrekter Digest mit falschem Schema oder falscher Provenienz blockiert;
- ein echter Nulltag bleibt von einer fehlenden Tageszeile unterscheidbar;
- zwei identische Artefakte werden einmal gespeichert und zweimal referenziert;
- unterschiedliche Inhalte können nicht wegen Dateiname oder Metadaten
  kollidieren;
- Indexgröße wächst nicht proportional zu 1m-Candles oder mehrfachen
  Equity-Kopien;
- Roundtrip rekonstruiert dieselben fachlichen Reihen und Summen.

### Nicht vorziehen

- Task 12 darf create-only/deduplicated Speicherung definieren, aber noch keine
  vollständige Crash-/Resume-Transaktion aus Aufgabe 13 behaupten;
- keine Fold-, Auswahl-, PBO-, DSR- oder Feature-Logik bauen;
- keine 12-Origin-Orchestrierung aus Aufgabe 23.

## 9. Aufgabe 13 – Content-addressed Cache und transaktionales Resume

### Muss umgesetzt werden

- Cache und Checkpoint verwenden den vollständigen Run-Fingerprint v2 und die
  konkrete validierte `ContextParityBinding`;
- jede folgende Identitätsklasse ist vorhanden oder besitzt einen typisierten,
  vertraglich validierten Genesis-/`NOT_APPLICABLE`-Zustand; Weglassen, `None`
  oder ein Aufruferdefault darf keinen Cache-Hit ermöglichen:
  - Drei-Markt-Daten- und Tagesdigests;
  - Code und Pipelinegeneration;
  - Feature-/Kandidaten-/Foldidentität;
  - Boundary-, Horizon-, Execution-, Simulator- und Kostenvertrag;
  - Quality Gates;
  - Exchange-Info-Snapshot;
  - Trial-Ledger-Head am Entscheidungszeitpunkt;
  - Rotation-State und bereits versiegelte Store-Heads;
- Checkpoints binden außerdem Pre-Run-Manifest, Seed-Namespace und Seedzustand,
  Budgetreservierungen sowie Stop-/Stagnationszustand;
- atomische Dateiablage mit Temp-Datei im Zielverzeichnis, Flush/Fsync und
  Replace beziehungsweise äquivalenter nachgewiesener Plattformsemantik;
- exklusive Sperre; eine unklare oder veraltete Sperre darf nicht blind
  überschrieben werden;
- ein Checkpoint wird erst nach vollständiger Artefakt- und Digestprüfung als
  committed sichtbar;
- Resume verwendet nur den letzten vollständig committed Zustand;
- Cache-Hit validiert alle transitiven Referenzen erneut;
- Cache-Wiederverwendung wird im permanenten Ledger sichtbar, zählt aber nicht
  als neuer unabhängiger Trial;
- Trial-, Work-Unit- und Cache-Reuse-IDs sind deterministisch und idempotent;
  ein Crash zwischen Ledger-Append und Checkpoint-Commit wird durch denselben
  Ereignisschlüssel geheilt statt durch einen zweiten Append;
- Neustart darf weder Trial, Cycle, Origin, Ergebnis noch Ledgerappend doppeln;
- gleicher Input muss nach Abbruch/Resume oder Cache-Hit dieselbe Entscheidung
  und dieselben fachlichen Digests liefern wie ein ununterbrochener Lauf.

### Besonders zu testen

- Fehler-Injektion vor und nach jeder Commit-/Replace-Phase;
- abgeschnittene Temp-/Index-/Artefaktdatei;
- Digest- oder Referenzmanipulation bei formal gültigem JSON;
- anderer Code-, Pipeline-, Kontext-, Daten-, Exchange- oder Ledgerstand;
- konkurrierender Writer und stale/unklare Lock-Situation;
- Wiederholung nach Crash ohne doppelte Ledgerereignisse;
- Cache-Hit mit identischen Daten und Cache-Miss nach jeder einzelnen
  Identitätsänderung;
- persistierter Checkpoint wird in einem neuen Prozess vollständig neu geladen,
  nicht aus einem In-Memory-Objekt bestätigt.

### Ehrliche Grenze

Die vollständige 12-Origin-End-to-End-Parität kann erst nach den späteren
Auswahl- und Orchestrierungsaufgaben in Aufgabe 32 abschließend bewiesen werden.
Aufgabe 13 muss die reale Transaktionsschicht mit repräsentativen vorhandenen
Protocol-v3-Objekten testen, darf aber keine noch nicht existierenden Fold- oder
Outer-Controller vortäuschen.

### Nicht vorziehen

- keinen Task-14-Fold-Planer;
- keine Auswahlfunktion aus Aufgabe 15;
- keinen Router oder `FrozenCandidateBundle` aus Aufgabe 22;
- keine Outer-Origin-Orchestrierung aus Aufgabe 23.
- keine persistente monatliche Rotation-/`valid_from`-/`flat_time`-Semantik aus
  Aufgabe 24; Task 13 darf nur vorhandenen Task-9-State beziehungsweise einen
  typisierten Identitätsslot binden;
- keinen Pipeline-Final-Store oder Evaluator aus Aufgabe 31.

## 10. Aufgabe 14 – Exakter innerer 6×60-Tage-Fold-Planer

### Muss umgesetzt werden

- reiner neuer Protocol-v3-Planer; die alte variable Foldlogik darf nicht
  unverändert umbenannt werden;
- Eingabe ist ein exakt definiertes 730-Tage-Trainingsintervall
  `[training_start, training_end)` in UTC;
- sechs chronologische, lückenlose und nicht überlappende Validation-Folds auf
  exakt den letzten 360 Tagen;
- je Fold exakt 60 vollständige UTC-Tage;
- für `k=0..5` exakt:

  ```text
  validation_start_k = training_end - (6-k) * 60 Tage
  validation_end_k   = training_end - (5-k) * 60 Tage
  fit_start_k        = training_start
  fit_end_k          = validation_start_k - purge_duration
  ```

- erster Fit besitzt vor Purging 370 Tage, danach wächst er je Fold um 60 Tage;
- Purge verwendet dieselbe eingefrorene `HorizonPolicy` wie Pending-Entry- und
  Holdinglogik aus Aufgaben 8/9;
- Warmup liegt außerhalb des Fits und bleibt ausschließlich feature-only;
- Boundary-Objekte sind immutable, kanonisch serialisierbar und gehasht.

### Besonders zu testen

- Leap-/Non-Leap- und Monatsgrenzen in UTC;
- exakt 360 unterschiedliche Validation-Tage;
- kein Tag der **aktuellen** Fold-Validation im zugehörigen aktuellen Fit;
- Rohmarkttage einer früheren Validation dürfen in einem späteren expanding Fit
  kausale Historie sein; frühere PnL, Rankings und Entscheidungen niemals;
- Label/Trade, dessen Informationshorizont die Grenze berührt, wird gepurgt;
- Timestamp-Spies blockieren jeden Read bei oder nach `validation_start` im Fit;
- fehlender Tag, doppelte Minute, falsches Intervall oder zu großer Purge
  blockiert;
- Eingabereihenfolge ändert den Plan nicht;
- alte Protocol-v2-Folds bleiben erhalten und werden nicht als v3 ausgegeben.

### Nicht vorziehen

- keine Kandidatenauswahl, Matrix, PBO oder DSR;
- keine Outer-Origins.

## 11. Aufgabe 15 – Reine innere Auswahlfunktion

### Muss umgesetzt werden

Öffentliche Form sinngemäß:

```text
select_candidate(training_window, frozen_pipeline_config)
    -> candidate | NO_TRADE, evidence, fingerprints
```

Die Funktion:

- besitzt nur explizite Eingaben und unveränderliche Abhängigkeiten;
- liest weder UI-Zustand noch Outer-Ergebnisse;
- verwendet keine versteckte globale Konfiguration, aktuelle Uhrzeit,
  Umgebungsvariable, Netzwerkabfrage oder implizite Arbeitsverzeichnisdatei;
- kann nichts bei oder nach `training_end` lesen;
- verwendet den Task-14-Planer und validiert die eingefrorenen
  40/12/3/2-Budgetobergrenzen;
- bindet Seed, Pipelinegeneration, Daten, Kontext, Kosten, Gates und Ledgerstand;
- liefert bei fehlender oder widersprüchlicher Evidenz `NO_TRADE` mit
  maschinenlesbarem Blocker;
- rankt niemals nach Abstand zum 3-USDC-Ziel;
- erzeugt für denselben Input denselben Kandidaten, dieselbe Evidenz und
  dieselben Digests.

Nach bestandenen Development-Gates gilt exakt diese lexikographische
Reihenfolge:

```text
worst_fold_net_usdc_per_day          absteigend
median_fold_net_usdc_per_day         absteigend
aggregate_wfv_net_usdc_per_day       absteigend
joint_stress_net_usdc_per_day        absteigend
max_drawdown_usdc                    aufsteigend
friction_share                       aufsteigend
free_parameter_count                 aufsteigend
canonical_candidate_id               aufsteigend
```

Die alte Protocol-v2-Rangfolge darf nicht stillschweigend als vertragsgleich
übernommen werden.

### Wichtige Übergangsregel

Aufgaben 16 bis 18 liefern Matrix, PBO und DSR erst später. Aufgabe 15 darf
diese Gates nicht mit permissiven Platzhaltern umgehen. Solange erforderliche
Development-Evidenz fehlt, muss die Auswahl fail-closed `NO_TRADE` liefern.
Nach den späteren Aufgaben wird dieselbe reine Funktion erweitert und erneut
abgenommen.

Aufgabe 15 baut deshalb den reinen Control-/Ranking-Kern und konsumiert
typisierte Evidenz. Sie führt oder persistiert noch nicht selbst den kompletten
Task-16-Prozess für Tagesmatrix und Promotion.

Der aktuelle reale Trial-History-Stand ist unvollständig. Synthetische
vollständige Fixtures dürfen den Trading-Pfad testen; der reale Zustand darf
deshalb nicht künstlich freigeschaltet werden.

### Besonders zu testen

- Future-/Outer-Timestamp-Spies;
- gleiche Eingaben in neuer Prozessinstanz;
- permutierte Eingabereihenfolge;
- fehlende Gate-/Ledger-/Kontextidentität;
- technischer Fehler wird nicht als günstiger Kandidat oder stilles Cash
  verschluckt;
- `NO_TRADE` ist eine echte typisierte Auswahl, kein Dummy-Kandidat;
- bestehende Researchfunktionen werden extrahiert/wiederverwendet statt als
  zweite Engine kopiert.

### Nicht vorziehen

- keine vollständige Matrix aus Aufgabe 16;
- kein PBO/DSR;
- keine äußere Orchestrierung.

## 12. Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion

### Muss umgesetzt werden

- jedes tatsächlich als getestet deklarierte Profil jedes Cycles, höchstens
  zwölf, erhält dieselbe 360-Tage-Basis aus den sechs Validation-Folds;
- die Origin-Matrix bewahrt alle datengetesteten Profile aller Cycles, nicht
  nur die drei Promovierten oder zwei Finalisten;
- jede Kandidatenspalte besitzt dieselben geordneten UTC-Tage;
- Werte sind tägliche Netto-MTM-PnL nach Kosten einschließlich echter
  No-Trade-Nulltage;
- eine fehlende Auswertung bleibt fehlende Evidenz und wird niemals zu Null
  umgedeutet;
- Profile, Tagesraster, Foldprovenienz und Inhalt werden gehasht;
- Promotion bleibt pro Cycle innerhalb der verschachtelten Obergrenzen:

  ```text
  tested <= 12
  promoted <= min(3, tested)
  finalists <= min(2, promoted)
  ```
- jedes datenbewertete Profil ist im permanenten Trial-Ledger sichtbar;
- Cache-Reuse ist sichtbar, aber kein neuer unabhängiger Trial;
- globale und per-Origin-/Cycle-Budgets bleiben unverändert.

### Besonders zu testen

- exakt 360 gemeinsame Tage pro vollständiger Kandidatenspalte;
- Nulltag versus fehlende Zeile;
- Kandidat mit nur 359 oder 361 Tagen blockiert;
- Duplikatdatum, nichtfiniter Wert oder abweichende Tagesreihenfolge blockiert;
- Summe der Tageswerte stimmt mit der zugehörigen Netto-MTM-Evidenz überein;
- ein nicht promovierter Kandidat bleibt dennoch in der PBO-Basismatrix;
- ein Profil kann nicht ohne vollständige Basisreihe Finalist werden;
- Cycle-/Origin-übergreifende ID-Kollisionen blockieren.
- Fold-Equity wird als Tagesdelta verkettet; bei jedem Fold auf null gesetzte
  absolute Equity-Werte dürfen nicht naiv addiert werden;
- fehlen Reihen für **deklarierte** getestete IDs, ist die Evidenz unvollständig;
  eine legitim kleinere deklarierte Testmenge wird jedoch nicht aufgefüllt und
  nicht allein deshalb als technischer Fehler bezeichnet.

### Nicht vorziehen

- PBO wird erst in Aufgabe 17 berechnet;
- DSR erst in Aufgabe 18;
- keine Outer-Ergebnisse verwenden.

## 13. Aufgabe 17 – PBO/CSCV exakt

### Muss umgesetzt werden

- Eingabe ist ausschließlich die vollständige kausale 360-Tage-Matrix aller
  datengetesteten Tradingprofile einer Origin;
- Vollständigkeit wird aus dem gebundenen Task-16-Origin-Inventar und dem
  zugehörigen Task-4-Ledger-Head abgeleitet, niemals aus einer vom Aufrufer
  gelieferten Spaltenzahl; das Weglassen eines getesteten Profils blockiert;
- keine Full-fit-In-Sample-, Shortlist-, Finalisten- oder Outer-PnL verwenden;
- `S=12` zusammenhängende Blöcke zu exakt 30 Tagen;
- alle `C(12,6)=924` IS-Blockkombinationen genau einmal auswerten;
- OOS ist jeweils das exakte Komplement der sechs IS-Blöcke;
- IS-Metrik ist mittlere tägliche Netto-MTM-PnL;
- genau eine immutable Cash-/`NO_TRADE`-Nullspalte nimmt sowohl an der
  IS-Auswahl als auch am OOS-Rang teil;
- IS-Gleichstand entscheidet über eine fest definierte kanonische ID
  aufsteigend, einschließlich der kanonischen Cash-ID;
- OOS-Rang verwendet bei gleichem OOS-Mittel den Durchschnittsrang,
  `1=schlechtester`, `M=bester`;
- exakt:

  ```text
  omega = (r - 0.5) / M
  lambda = ln(omega / (1 - omega))
  development_pbo = count(lambda <= 0) / 924
  ```

- Cash/`NO_TRADE` zählt weder als Trial noch als eines der mindestens zwei
  erforderlichen Tradingprofile. Es gilt
  `M = Anzahl Tradingprofile + 1`; gewinnt Cash einen IS-Split, wird dieser
  Split normal ausgewertet. Cash selbst benötigt kein DSR-/PBO-Release-Gate;
- weniger als zwei Tradingprofile, ungleiche Tage, fehlende oder nichtfinite
  Werte ergeben `INSUFFICIENT_EVIDENCE`.

### Vor Implementierung explizit einfrieren

Task 17 muss die Average-Rank-Regel des Blueprints, die kanonische Cash-ID und
deren Teilnahme an IS und OOS im versionierten Vertrag eindeutig festlegen und
mit Golden Fixtures prüfen. Keine zufällige Dict-, Sortier- oder
Bibliotheksreihenfolge verwenden.

### Besonders zu testen

- exakt 924 eindeutige Splits;
- jeder Split besitzt 180 IS- und 180 OOS-Tage;
- Komplement- und Blockgrenzen stimmen;
- unabhängig handberechnete Golden-Matrix;
- konstante Reihen `A=+1`, `B=+0,5`, Cash `0` ergeben `PBO=0`;
- zwei spiegelbildlich auf die Blockhälften überangepasste Profile ergeben
  `PBO=1`;
- bei ausschließlich identischen Nullreihen gilt wegen `lambda<=0` exakt
  `PBO=1`;
- deterministische IS- und OOS-Ties;
- Kandidatenspalten-Permutation ändert das fachliche Ergebnis nicht;
- eine beliebige Tagespermutation wird abgelehnt; die zwölf Blöcke entstehen
  ausschließlich aus dem kanonischen chronologischen Tagesindex;
- zusätzlich zum PBO-Wert wird separat geprüft, ob ein Tradingkandidat die im
  Ranguniversum enthaltene Cash-Baseline über die gemeinsame 360-Tage-Reihe
  mit einem strikt positiven aggregierten Mittel schlägt; Gleichstand reicht
  nicht;
- fehlende Evidenz liefert keinen numerischen Ersatzwert;
- keine Rundung vor Winner-, Tie-, Rank- oder Gate-Entscheidung; die
  Summationsreihenfolge muss deterministisch sein.

### Nicht vorziehen

- keine DSR-Berechnung;
- kein Outer-Bootstrap oder Monthly Gate.

## 14. Aufgabe 18 – DSR und Multiple-Testing-Diagnostik

### Muss umgesetzt werden

Die Implementierung folgt exakt Abschnitt 7.3 des Blueprints:

- `n=360` tägliche Netto-MTM-Werte einschließlich Nulltage;
- die ausgewählte Reihe ist digest-identisch mit der Task-16-/Ledger-Reihe auf
  exakt denselben geordneten 360 UTC-Tagen; Schnittmengenbildung, Forward-Fill,
  Entfernen von Nulltagen sowie Droppen oder Auffüllen fehlender Tage sind
  verboten;
- Sample-Standardabweichung mit `ddof=1`, ohne Annualisierung;
- `K=floor(4*(n/100)^(2/9))`;
- damit gilt bei `n=360` exakt `K=5`;
- Stichprobenautokorrelationen und gewichteter VIF;
- `n_eff=n/VIF` mit `VIF>=1`;
- Schiefe und Pearson-Kurtosis gemäß eingefrorenem Vertrag;
- Task 18 friert vor der Implementierung die exakten Momentenschätzer fest:
  biased/unbiased-Konvention, Sample-Korrektur und Mindeststichprobe dürfen
  nicht von wechselnden Bibliotheksdefaults abhängen;
- `N_raw` ist der vollständige permanente Trial-Count am gebundenen
  Ledger-Head;
- diagnostisches `N_eff_trials` darf `N_raw` im Gate niemals ersetzen;
- `sigma_SR` ist die Sample-Standardabweichung des exakt gebundenen Satzes
  kausaler Trial-Sharpe-Werte; Trial-IDs, Reihen- und Set-Digest werden
  reportet;
- `SR0`, Nenner und `Phi(z)` werden mit allen Zwischenwerten reproduzierbar
  reportet;
- die Korrelationsmatrix verwendet nur vollständig gemeinsame kausale
  Kandidatenreihen;
- fehlende gemeinsame Reihen, Nullvarianz, ungültiger Nenner, `N_raw<2`,
  nichtfinite Werte oder unvollständige Trial-Historie liefern
  `INSUFFICIENT_EVIDENCE` beziehungsweise
  `INSUFFICIENT_TRIAL_HISTORY`;
- ein Tradingkandidat darf dann nicht freigegeben werden; `NO_TRADE` bleibt die
  einzige valide Entscheidung.
- `NO_TRADE` erhält `NOT_APPLICABLE_NO_TRADE`, niemals einen künstlichen DSR
  von 1;
- vor dem Einfrieren einer Auswahl wird der Ledger-Head erneut geprüft; ein
  zwischenzeitlicher Append macht die alte DSR-Evidenz veraltet.
- ein Tradingkandidat besteht nur bei `development_dsr >= 0.95`; ein kleinerer
  Wert führt fail-closed `NO_TRADE`.

### Unverhandelbarer realer Ausgangszustand

Der aktuell belegbare historische Altbestand ist weiterhin nur eine Untergrenze
und besitzt keine vollständig aufgelösten unabhängigen Alt-Trials. GPT darf den
Status nicht durch Zeilenzahlen, Cache-/Duplikatbehauptungen oder synthetische
Attestierungen auf vollständig setzen. Numerische Positivtests verwenden eine
separate vollständig belegte Testfixture; der reale Gate-Test bleibt gesperrt.

### Besonders zu testen

- unabhängig berechnete numerische Golden Fixtures;
- Autokorrelation mit bekannten Reihen;
- Schiefe/Kurtosis und Nennergrenzen;
- Trial-Count stammt aus dem revalidierten Ledger-Snapshot, nicht aus einem
  Funktionsparameter;
- ein späteres Ledgerereignis mutiert den alten, an seinen Head gebundenen
  DSR-Nachweis nicht, macht ihn aber für eine Entscheidung am neuen Head stale
  und damit unzulässig;
- `N_eff_trials` kann den Gatewert nicht verbessern;
- unvollständige Historie blockiert die Task-15-Auswahl end-to-end;
- PBO- und DSR-Evidenz bleiben getrennt, werden aber beide für einen
  Tradingkandidaten verlangt.

### Nicht vorziehen

- kein Outer-Block-Bootstrap aus Aufgabe 27;
- keine Monthly Gates aus Aufgabe 26;
- keine Trial-History-Lockerung.

## 15. Aufgabe 19 – Kausaler Multi-Timeframe-Feature-Store

### Muss umgesetzt werden

- gemeinsame exakte 1m-Basis für ETHUSDC, BTCUSDC und ETHBTC;
- Eingang ist die validierte Task-10-Drei-Markt-/Snapshotbindung, nicht eine
  beliebige Candle-Liste mit frei behauptetem Digest;
- deterministische UTC-Aggregation für 5m, 15m, 30m, 1h, 4h und 1d;
- Wochen- und Monatskontext nur aus vollständig abgeschlossenen Perioden;
- ein höherer Balken wird erst nach Eingang und Prüfung aller benötigten 1m-Bars
  sichtbar;
- keine Teilbar, kein Forward-Fill, keine Interpolation und kein
  Nearest-Neighbor;
- OHLCV-Aggregation, Zeitgrenzen und Availability-Timestamp sind versioniert;
- Wochenanfang und Kalendermonatsgrenze werden vor Implementierung als
  ausdrückliche versionierte Task-19-Vertragsentscheidung festgelegt. ISO-Woche
  Montag-zu-Montag und echter UTC-Kalendermonat sind der naheliegende Vorschlag,
  aber kein stillschweigend bereits beschlossener höherer Produktvertrag; bei
  fehlender Freigabe oder Widerspruch nicht raten, sondern blockieren;
- Featuredefinition, Fit-State, Scaler, Quantile, Trainingsgrenze und
  Quelldigests sind immutable, serialisierbar und gehasht;
- Fit und Transform sind getrennt: Scaler, Quantile, Schwellen und Auswahl
  werden ausschließlich auf dem jeweiligen Fold-Training gelernt;
- Warmup darf Rolling-State aller drei Märkte seeden, aber nie Scaler,
  Quantile, Labels, Ranking, PnL oder Signale beeinflussen;
- vergangene MFE/MAE darf nur als trailing Verteilung dienen, wenn jeder
  Ergebnishorizont vor `available_at` vollständig beendet und durch Purge
  zulässig ist; Warmup, Validation und zukünftige MFE/MAE dürfen sie nicht in
  den Fit einschleusen;
- Replay mit demselben Store und Fit-State ist bitgleich;
- Feature-/Fit-State-Identität fließt in Pipeline, Cache und Resume ein.
- kein Scaler-, Modell- oder Feature-Fit-State wird zwischen Folds oder Outer-
  Origins getragen; Wiederverwendung ist nur bei exakt identischer
  Task-13-Cache-Identität zulässig;
- Persistenz verwendet die kompakte Task-12-Referenzarchitektur und den
  transaktionalen Task-13-Store, nicht eine zweite Feature-Speicherwahrheit.

### Besonders zu testen

- Future-Mutation nach dem Entscheidungstimestamp verändert frühere Features
  nicht;
- unvollständige 5m-/4h-/Tages-/Wochen-/Monatsbar ist unsichtbar;
- fehlende einzelne 1m-Bar blockiert die davon abhängige höhere Bar;
- UTC-Tages-, Wochen-, Monats- und Leap-Grenzen;
- Training-only-Scaler/Quantile mit extremen späteren Validationwerten;
- Warmup erzeugt keine Fit-Statistik und kein Signal;
- Drei-Markt-Watermark und Task-5-Tagesinhalte bleiben exakt gebunden;
- persistierter Fit-State wird beim Reload vollständig revalidiert;
- Feature-Reihen sind unabhängig von Chunking und Eingabereihenfolge.
- das heutige `backtest/features.py` stellt Werte teilweise am Candle-
  `open_time` dar und darf deshalb nicht ungeprüft als Store geschlossener
  höherer Bars ausgegeben werden; `available_at` muss das tatsächliche Ende
  aller Quellbars beweisen.

### Nicht vorziehen

- keine Opportunity-/Regimeentscheidung aus Aufgabe 20;
- keine Spezialisten aus Aufgabe 21;
- kein Router oder `FrozenCandidateBundle` aus Aufgabe 22.

## 16. Aufgabe 20 – Opportunity- und Regime-Schicht

### Muss umgesetzt werden

- kausale, typisierte Bewertungen für:
  - Bewegungskapazität;
  - Trend und Effizienz;
  - Range/Stabilität;
  - Kompression/Expansion;
  - Stress beziehungsweise widersprüchlichen Kontext;
- Mindestinhalt der zugrunde liegenden Dimensionen:
  - realisierte Volatilitätsquantile, ATR und erwartete Range;
  - Range-Kompression/-Expansion und vollständig gereifte trailing MFE/MAE;
  - 1h-/4h-/1d-Returns und Trend-Effizienz;
  - Steigung/Distanz zu robusten Trendankern;
  - BTCUSDC-Stress/Volatilität und ETHBTC-relative Stärke;
- ausschließlich Task-19-Features und den zum Timestamp gültigen Fit-State
  verwenden;
- alle Quantile, Schwellen und Normalisierungen nur auf Fold-Training fitten;
- Opportunity-Kapazität strikt von Long-Richtung trennen: erwartete Bewegung
  ist kein Entry-Signal;
- BTCUSDC und ETHBTC dürfen bestätigen oder blockieren, niemals Richtung,
  Signal oder Trade erzeugen;
- unbekannte, fehlende, stale oder widersprüchliche Lage liefert nicht nur
  einen Grund, sondern die tatsächliche Entscheidung `NO_TRADE`;
- die Entscheidungspräzedenz ist deterministisch:

  ```text
  invalid/missing/stale
  -> stress oder context veto
  -> conflict
  -> nach Kosten unzureichende Opportunity
  -> erst sonst routable regime
  ```

- Stress führt fail-closed zu `NO_TRADE`;
- vergangene MFE/MAE darf nur verwendet werden, wenn ihr gesamter
  Ergebnishorizont vor dem Entscheidungstimestamp abgeschlossen war;
- das eingefrorene Kostenprofil darf die Opportunity als wirtschaftlich
  unzureichend blockieren;
- Ergebnis enthält nachvollziehbare Reason Codes, Feature-State-Hash,
  Threshold-State-Hash und Entscheidungstimestamp;
- gleiche Eingaben erzeugen identische Regime-/Opportunityausgabe.
- der operative Router-Regimebegriff bleibt getrennt vom vorhandenen
  Quality-Gate-Regime `trend_sign_x_training_median_volatility`; Task 20 darf
  dieses Gate weder ersetzen noch lockern.
- jede geänderte Feature-, Schwellen- oder Regimedefinition erzeugt eine neue
  Pipelinegeneration und einen dateninformierten Trial;
- Hindsight-/Capture-Solver-Ausgaben dürfen niemals in diese Schicht gelangen.

### Wichtige Leakage-Sperre

Die im Blueprint genannten historischen Tertile von ungefähr 4,43 % und
5,81 % sind exploratorische Diagnosewerte und keine universellen
Produktionsschwellen. Sie dürfen nicht hart in die Engine kopiert werden.
Schwellen werden je Fold ausschließlich aus dessen Training gelernt. Die
dateninformierte Hypothese bleibt im permanenten Trial-Ledger sichtbar.

### Besonders zu testen

- Future-Mutation und unvollständige höhere Bars;
- veränderte Validationdaten beeinflussen Trainingsthresholds nicht;
- hohe Volatilität ohne Richtungsbeleg erzeugt kein Long-Signal;
- Trend/Range-Konflikt, Stress und fehlender Kontext liefern `NO_TRADE`-Grund;
- ETHBTC/BTCUSDC können die Trade-Engine nicht aufrufen;
- Entscheidung und Reason Codes bleiben nach Persistenz/Reload gleich;
- task-15-Auswahl behandelt unbekannte oder unvollständige Regimeevidenz
  fail-closed.

### Nicht vorziehen

- keine lokalen Spezialisten aus Aufgabe 21;
- kein Router, keine Strategieauswahl und kein `FrozenCandidateBundle` aus
  Aufgabe 22;
- keine Outer-Origins, Monthly Gates oder UI;
- die Regime-Schicht erzeugt selbst weder Signal noch Trade.

## 17. Bestehenden Code wiederverwenden, aber nicht falsch umdeuten

Vor einer neuen Implementierung sind mindestens folgende vorhandene Bereiche
zu inventarisieren:

| Aufgaben | Vorhandene Bereiche |
|---|---|
| 11 | `src/ethusdc_bot/reports/schema.py`, `backtest/reporting.py`, `shadow/schema.py`, bestehende Report-Schemas |
| 12 | bestehende Reportwriter, `backtest/research_loop_runner.py`, `shadow/store.py` |
| 13 | `protocol_v3/run_identity.py`, `context_parity.py`, `trial_ledger.py`, bestehende Resume-/Supervisor- und Atomic-Store-Funktionen |
| 14 | `protocol_v3/boundaries.py`, `runtime_state.py`, bestehende `backtest/walk_forward.py` nur als Inventar, nicht als unveränderten v3-Planer |
| 15 | `research_loop_runner.py`, `research_runner.py`, `pipeline.py`, `global_budget.py`, `trial_history_gate.py` |
| 16 | Walk-forward-Evidenz, Equity-/MTM-Helfer und kanonische Protocol-v3-Simulatorpfade |
| 17–18 | Task-16-Matrix, `trial_ledger.py`, `trial_history_gate.py` |
| 19 | `backtest/features.py`, `context_features.py`, `data_loader.py`, `protocol_v3/data_snapshot.py`, `context_parity.py` |
| 20 | Task-19-Feature-Store und vorhandene reine Feature-/Kontextfunktionen |

Wiederverwendung bedeutet nicht, eine alte Protocol-v2-Semantik umzubenennen.
Wenn ein alter Pfad einen anderen Vertrag besitzt, bleibt er erhalten und der
Protocol-v3-Pfad wird eindeutig getrennt versioniert.

## 18. Handoff pro Aufgabe

Jedes Handoff 11 bis 20 enthält mindestens:

- Status und exakte Aufgabenbezeichnung;
- geprüfter Ausgangs-Head;
- Ergebnis des adversarialen Reviews der Voraufgabe;
- gegebenenfalls eigener Korrekturcommit der Voraufgabe;
- geänderte Verträge, Schemas und öffentliche Produktionspfade;
- konkrete End-to-End-Aufrufkette;
- Persistenz-/Reload- und Manipulationsnachweise;
- neue und vollständige Testzahl;
- Compile-, Whitespace- und JSON-Status;
- Commit, Remote-Head und GitHub-CI-Link;
- reale aktuelle Blocker;
- ausdrücklich noch nicht implementierte spätere Controller;
- unveränderte Safety-Sperren;
- exakt nächste Aufgabe.

Ein Handoff darf keine reale Backtest-, Performance- oder 3-USDC-Aussage
erfinden, wenn in der Aufgabe kein entsprechender vollständiger Lauf stattfand.

## 19. Kumulativer Bericht nach Aufgabe 20

Nach dem eigenen Abschlussreview von Aufgabe 20 erstellt GPT einen Bericht für
Codex mit einer Tabelle für jede Aufgabe 11 bis 20:

- Aufgabenstatus;
- Implementierungscommit(s);
- eventuelle Korrekturcommits;
- Vertrags-/Schemaversionen;
- zentrale Quelldateien;
- tatsächlicher öffentlicher Einstiegspunkt;
- tatsächlicher persistierter Artefaktpfad oder begründetes
  `NOT_APPLICABLE_PURE_CORE`;
- neue Tests und vollständige Testzahl;
- Review-CI-Run;
- belegte Invarianten;
- bekannte Einschränkungen und auf spätere Aufgaben verschobene Integration.

Zusätzlich sind anzugeben:

- korrigierter Startcommit `202e629f6b736e4bd1ff5cd53aeb9096fbf5a167`;
- finaler Branch- und Remote-Head;
- ob der Arbeitsbaum sauber ist;
- alle Pipeline-/Schema-Versionssprünge;
- ob alte Artefakte regeneriert werden müssen;
- aktueller realer Trial-History-, Daten-/Warmup- und `NO_TRADE`-Status;
- Nachweis, dass Aufgabe 21 nicht begonnen wurde;
- Nachweis, dass keine Orders, API-Keys, Trading-API, Paper-, Testtrade- oder
  Live-Aktivierung entstanden ist.

Danach nimmt GPT keine weitere Änderung vor. Codex zieht den GitHub-Stand,
prüft Aufgaben 11 bis 20 unabhängig und entscheidet gemeinsam mit dem Nutzer
über die Fortsetzung ab Aufgabe 21.

## 20. Kurze Arbeitsanweisung für jeden neuen GPT-Auftrag

Für Aufgabe 11:

```text
Lies docs/43_PROTOCOL_V3_TASK_11_20_GPT_EXECUTION_GUARDRAILS.md vollständig.
Synchronisiere den aktuellen PR-#17-Branch. Implementiere ausschließlich
Aufgabe 11 nach diesem Dokument. Teste vollständig, committe, pushe, warte die
Review CI ab, aktualisiere das Handoff und stoppe.
```

Für Aufgabe `N` von 12 bis 20:

```text
Lies docs/43_PROTOCOL_V3_TASK_11_20_GPT_EXECUTION_GUARDRAILS.md vollständig.
Synchronisiere den aktuellen PR-#17-Branch. Kontrolliere zuerst Aufgabe N-1
adversarial anhand des echten Codes. Korrigiere gefundene Fehler in einem
eigenen Commit und warte die grüne CI ab. Implementiere danach ausschließlich
Aufgabe N. Teste vollständig, committe, pushe, warte die Review CI ab,
aktualisiere das Handoff und stoppe. Keine Aufgabe N+1 vorziehen.
```

Für Aufgabe 20 gilt zusätzlich: nach dem Abschlussreview den kumulativen
Bericht aus Abschnitt 19 erstellen und anschließend ohne Aufgabe 21 stoppen.
