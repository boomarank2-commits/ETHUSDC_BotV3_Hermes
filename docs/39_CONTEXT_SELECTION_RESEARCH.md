# 39 – BTCUSDC-/ETHBTC-Kontext im ETHUSDC-Selection-Research

Stand: 2026-07-11

## Ziel

Die bereits vorhandene trailing-only Kontext-Engine wird jetzt vollständig und reproduzierbar im Selection-Research ausgewertet.

Dabei bleibt unverändert:

- ausschließlich ETHUSDC wird simuliert und später hypothetisch gehandelt;
- BTCUSDC liefert nur Gesamtmarkt-/Risikokontext;
- ETHBTC liefert nur relative Stärke oder Schwäche;
- Kontext darf ein vorhandenes ETHUSDC-Basissignal ausschließlich bestätigen oder verwerfen;
- Kontext darf niemals selbst einen Einstieg erzeugen;
- Live, Paper, Testtrade und echte Orders bleiben gesperrt.

## Explizite Aktivierung

Der normale Python-Runner behält den sicheren Standard:

```text
context_enabled = false
```

Kontextresearch wird nur mit folgendem Schalter aktiviert:

```text
--enable-context
```

Der kanonische Windows-Produktionsstarter setzt diesen Schalter ausdrücklich und prüft vor dem mehrstündigen Lauf alle drei Symbolinventare.

## Datenvertrag

Vor dem Start müssen für jedes Symbol mindestens 1.095 vollständige Tagespaare vorhanden sein:

- ETHUSDC ZIP + CHECKSUM;
- BTCUSDC ZIP + CHECKSUM;
- ETHBTC ZIP + CHECKSUM.

Ungepaarte ZIP- oder CHECKSUM-Dateien führen zum Abbruch vor dem Research.

Anschließend lädt der bestehende read-only Datenlayer alle drei Märkte und verlangt:

- dieselbe Kerzenanzahl;
- exakt identische UTC-Open-Timestamps;
- durchgehende 1-Minuten-Schritte;
- keine Duplikate;
- kein Forward-Fill;
- keine Interpolation;
- keine erfundenen Kerzen.

## Exakte Fensterschnitte

`context_research.py` schneidet Kontextfenster ausschließlich anhand der exakten ETHUSDC-Zeitachse.

Ein Kontextfenster muss:

- innerhalb des geladenen Gesamtfensters liegen;
- zusammenhängende 1-Minuten-Kerzen besitzen;
- in ETHUSDC, BTCUSDC und ETHBTC dieselben Timestamps besitzen.

Dies gilt getrennt für:

- Subtrain;
- interne Validation;
- vollständiges Training;
- jeden Walk-Forward-Fold;
- jedes Kostenstressprofil;
- jeden Parameter-Nachbarn;
- jedes historische Rolling-Origin-Fenster.

## Kollision von `base_family` behoben

Mehrere bestehende Strategien nutzen bereits intern `base_family`, zum Beispiel:

- `cooldown_fee_aware`;
- `session_filter`.

Ein äußerer Kontext-Wrapper darf dieses Feld nicht überschreiben. Deshalb verwendet der Kontextresearch jetzt:

```text
context_base_family
```

Die innere Strategie behält ihre eigene vollständige Parameterstruktur einschließlich ihres eigenen `base_family`.

Die Simulatorlogik liest für neue Kontextkandidaten zuerst `context_base_family` und akzeptiert für ältere isolierte Fixtures weiterhin den bisherigen Fallback.

## Deterministischer Kontext-Suchraum

Es existieren sieben vorab festgelegte Kontextprofile. Sie variieren ausschließlich:

- BTCUSDC-Trendlookback;
- BTCUSDC-Mindesttrend;
- BTCUSDC-Volatilitätslookback;
- BTCUSDC-Maximalvolatilität;
- ETHBTC-Trendlookback;
- ETHBTC-Mindesttrend.

Kein Profil enthält:

- Zielertrag;
- Auditwerte;
- Holdoutwerte;
- spätere Ergebnisdaten.

Bei aktivem Kontext bleiben die Stufenbudgets unverändert:

```text
40 erzeugt
12 getestet
3 Walk-Forward
2 Finalisten
```

Im 40er-Frontier entstehen sechs Kontextkandidaten. Durch die familienbalancierte Auswahl gelangen zwei davon in die zwölf Testplätze. Kontext ersetzt damit keine gesamte Strategiefamilie und sprengt das Ressourcenbudget nicht unkontrolliert.

## Parameterstabilität

Ein Kontextkandidat besitzt bis zu sechs zusätzliche numerische Kontextparameter. Das bisherige Limit von zwölf numerischen Parametern hätte solche Kandidaten unabhängig von ihrer Leistung automatisch als unvollständig markiert.

Das explizite Limit wurde deshalb auf 18 numerische Parameter pro Finalist erweitert. Alle Parameter erhalten weiterhin zwei deterministische Nachbarn.

Die Produktionsobergrenze steigt transparent:

```text
Parameter-Evidenz: 7.008 → 10.512 Kandidatentage pro Zyklus
Selection gesamt: 24.528 → 28.032 Kandidatentage pro Zyklus
```

Diese Erhöhung wird im Report ausgewiesen und ist keine versteckte Simulation.

## Report-Provenienz

Jeder Research-Zyklus enthält `context_research` mit mindestens:

- Integrationsversion;
- Policy-Version;
- aktivem Status;
- ETHUSDC als einzigem Handelsmarkt;
- BTCUSDC und ETHBTC als Kontextmärkte;
- ausgerichteter Kerzenanzahl;
- erstem und letztem Timestamp;
- Anzahl erzeugter Kontextkandidaten;
- `context_direct_trigger_allowed = false`;
- `uses_audit_or_holdout = false`;
- `target_used_as_parameter = false`.

Der Windows-Starter akzeptiert einen Kontextlauf nur, wenn jeder abgeschlossene Zyklus den aktivierten Kontext nachweist.

## Was dieser PR nicht beweist

Die technische Integration beweist nicht, dass Kontext den Ertrag verbessert und nicht, dass 3 USDC pro Kalendertag erreicht werden.

Das kann nur ein neuer lokaler Real-Daten-Lauf auf dem gebundenen Git-Commit zeigen. Dabei sind mindestens getrennt zu vergleichen:

- beste ETHUSDC-Basisstrategie;
- zugehörige Kontextvariante;
- Zahl der zugelassenen und verworfenen Basissignale;
- Nettoertrag nach Gebühren und Slippage;
- Tradezahl;
- Profit Factor;
- Drawdown;
- Walk-Forward- und Rolling-Stabilität;
- Kostenstress;
- Parameterstabilität.

## Prüfung

GitHub Actions, Python 3.12:

- 832 Tests bestanden;
- Python-Kompilierung bestanden;
- PowerShell-Syntaxprüfung bestanden;
- gestapelte Whitespace-Prüfung gegen PR #11 bestanden.

Zusätzliche Tests prüfen insbesondere:

- exakte mittlere Kontextfenster;
- Lücken und außerhalb liegende Zeitfenster;
- erneute Prüfung aller drei Zeitachsen;
- Kontext nur für `context_filter`;
- Erhalt verschachtelter `base_family`-Logik;
- sieben deterministische Kontextprofile;
- 40/12-Grenzen mit sechs erzeugten und zwei getesteten Kontextkandidaten;
- keine Ziel-/Audit-/Holdoutparameter;
- echte Walk-Forward-Auswertung auf vollständigen UTC-Tagen;
- vollständige Inventur aller drei Märkte vor dem Produktionslauf.
