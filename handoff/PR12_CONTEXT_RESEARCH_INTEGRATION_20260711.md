# PR #12 – Kontextintegration in das Selection-Research

Stand: 2026-07-11

## Branch und Pull Request

- Branch: `review/context-research-integration-v1`
- Base: `review/research-checkpoints-context-v1`
- Pull Request: `#12`
- Status: offen, Draft, nicht gemergt

## Ausgangslage

PR #9 stellte einen strikten Loader und die exakte Ausrichtung für ETHUSDC, BTCUSDC und ETHBTC bereit.

PR #10 implementierte eine trailing-only Kontext-Veto-Engine. Diese konnte ausschließlich ein vorhandenes ETHUSDC-Basissignal bestätigen oder verwerfen.

Bis zu diesem PR war die Engine aber noch nicht im Produktions-Research aktiv:

- der Runner lud nur ETHUSDC;
- der Search Frontier erzeugte bewusst keine echten Kontextkandidaten;
- Walk-Forward, Kostenstress, Parameterstabilität und Rolling-Origin erhielten keinen Kontext.

Dadurch konnte die neue Kontextlogik noch keinen Beitrag zur Suche nach einem robusteren ETHUSDC-Profil leisten.

## Umgesetzte Änderungen

### 1. Selection-only Kontextadapter

Neue Datei:

```text
src/ethusdc_bot/backtest/context_research.py
```

Enthält:

- exakte Kontextfensterschnitte;
- `context_for_candidate(...)`;
- `wrap_candidate_with_context(...)`;
- sieben deterministische Kontextprofile;
- vollständige Kontext-Provenienz.

Der Adapter besitzt keine Netzwerk-, Account-, Key-, Order-, Audit- oder Holdout-Abhängigkeit.

### 2. Parameterkollision behoben

Der äußere Kontext-Wrapper verwendet jetzt:

```text
context_base_family
```

Damit bleiben vorhandene innere Felder wie `base_family=momentum` oder `base_family=breakout` vollständig erhalten.

Der Simulator unterstützt für ältere isolierte Fixtures weiterhin den bisherigen Fallback.

### 3. Search Frontier

Neue optionale Schnittstelle:

```text
context_enabled=False
```

Bei ausgeschaltetem Kontext bleibt das bisherige Verhalten unverändert.

Bei eingeschaltetem Kontext:

- weiterhin maximal 40 erzeugte Kandidaten;
- sechs davon sind Kontextvarianten;
- weiterhin zwölf familienbalanciert getestete Kandidaten;
- zwei davon sind Kontextvarianten;
- weiterhin drei Walk-Forward-Kandidaten;
- weiterhin zwei Finalisten.

### 4. Vollständige Research-Anbindung

Exakt geschnittener Kontext wird weitergegeben an:

- Subtrain-Simulation;
- interne Validation;
- vollständiges Training;
- Walk-Forward-Frontier;
- gemeinsame Kostenstressprofile;
- Slippage-Stress;
- Parameter-Nachbarn;
- historische Rolling-Origin-Replays.

Kein Pfad darf still auf ungeprüfte oder anders geschnittene Kontextdaten zurückfallen.

### 5. Expliziter Schalter und Provenienz

CLI:

```text
--enable-context
```

`LoopConfig.enable_context` bleibt standardmäßig `False`.

Jeder abgeschlossene Zyklus enthält einen eigenen `context_research`-Nachweis. Der Zielwert wird nicht als Parameter verwendet; Audit und finaler Holdout bleiben ausgeschlossen.

### 6. Ressourcenbudget

Das maximale numerische Parameterbudget pro Finalist wurde von 12 auf 18 erhöht, damit die sechs Kontextparameter tatsächlich vollständig perturbiert werden können.

Produktionsobergrenzen pro Zyklus:

```text
Parameter-Evidenz: 10.512 Kandidatentage
Selection gesamt: 28.032 Kandidatentage
```

Diese Werte werden explizit berichtet.

### 7. Windows-Produktionsstarter

Der Starter:

- bindet weiterhin das `src`-Layout selbst;
- nutzt den Research-Supervisor aus PR #11;
- aktiviert Kontext ausdrücklich;
- prüft vor dem langen Lauf alle drei Symbolinventare;
- verlangt je Symbol mindestens 1.095 ZIP- und CHECKSUM-Paare;
- lehnt ungepaarte ZIPs und ungepaarte CHECKSUMs ab;
- speichert das Inventar im Manifest;
- akzeptiert den finalen Report nur, wenn jeder Zyklus `context_research.enabled=true` nachweist.

## Tests und CI

Finale read-only GitHub Actions nach Entfernen aller Patch-Helfer:

- 832 Tests bestanden;
- Python-3.12-Kompilierung bestanden;
- echter PowerShell-Parser bestanden;
- gestapelte Whitespace-Prüfung gegen PR #11 bestanden.

Während der testgetriebenen Integration wurden drei veraltete Testannahmen erkannt:

1. Zwei Tests erwarteten weiterhin den früheren Abschaltgrund `real_context_market_data_not_integrated`.
2. Ein Test erwartete weiterhin das alte 12-Parameter-Ressourcenbudget.

Diese Erwartungen wurden an den neuen expliziten Vertrag angepasst. Keine Safety-Assertion wurde gelockert.

## Repository-Hygiene

Die temporären Patch-Helfer wurden nach dem grünen Produktivcommit gelöscht.

Im finalen PR verbleiben nur:

- Produktivcode;
- Tests;
- normale read-only CI;
- Dokumentation;
- Handoff.

## Sicherheitsstatus

Unverändert gesperrt:

- Live;
- Paper;
- Testtrade;
- echte Orders;
- Kontozugriff;
- API-Keys/private Endpunkte;
- Shorts;
- Margin;
- Futures;
- Leverage.

ETHUSDC bleibt der einzige Handelsmarkt. BTCUSDC und ETHBTC bleiben reine Kontextmärkte.

## Leistungsstatus

Dieser PR liefert noch keinen Nachweis für 3 USDC netto pro Kalendertag.

Der ältere lokale Lauf auf Commit `97167626...` verwendete noch keinen aktiven Kontext-Research-Pfad. Laut letztem Codex-Zwischenstand waren fünf Zyklen abgeschlossen, Zyklus sechs lief und die sichtbaren Performance-Komponenten waren negativ.

Vor einem neuen Lauf muss zuerst festgestellt werden, ob dieser alte Prozess inzwischen abgeschlossen wurde und ob ein finaler Runner-JSON-Report existiert.

## Nächster lokaler Ablauf

1. Alten Python-Prozess und bisherige Reports prüfen.
2. Alten Report vollständig sichern und auswerten, sofern vorhanden.
3. PR #12 lokal auf einen neuen Codex-Prüfbranch holen.
4. 832 lokale Tests, Kompilierung und `git diff --check` ausführen.
5. Inventare für ETHUSDC, BTCUSDC und ETHBTC prüfen.
6. Neuen kontextaktiven Produktionslauf über den Windows-Starter ausführen.
7. Supervisor-Checkpoints regelmäßig kontrollieren.
8. Finalen JSON-Report auswerten.
9. Basis- und Kontextkandidaten getrennt vergleichen.
10. Erst anhand dieser Selection-Evidenz die nächste gezielte Änderung planen.

Kein Merge und keine Holdout-Öffnung vor dieser lokalen Prüfung.
