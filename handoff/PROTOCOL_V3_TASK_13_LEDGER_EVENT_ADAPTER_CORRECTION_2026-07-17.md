# Protocol v3 – Korrekturbericht Aufgabe 13

Stand: 2026-07-17

## Status

`Aufgabe 13 – Content-addressed Cache und transaktionales Resume – KORRIGIERT UND CI-GRÜN`

Diese Korrektur wurde vor Beginn von Aufgabe 14 durchgeführt.

## Adversarialer Befund

Der verbindliche Ausgangs-Head war:

`a4a48c226da4992575f9dd01bfc8d993859ec629`

PR #17 war offen, Draft und ungemerged.

Das permanente Task-4-Trial-Ledger speichert den Hash eines Events im Feld `event_sha256`. Der Task-13-Adapter griff im produktiven Code jedoch weiterhin an drei Stellen auf das nicht existierende Feld `event_hash` des Ledger-Events zu:

- beim Aufbau des Checkpoint-Ledger-Receipts;
- bei der Cache-Hit-Prüfung gegen den Ledger-HEAD;
- bei der Revalidierung eines bereits persistierten Receipts.

Die Task-13-Receipt-Struktur darf intern weiterhin das neutrale Feld `event_hash` verwenden. Der Adapter muss dafür aber den semantisch validierten Wert aus `event_sha256` des echten Task-4-Events übernehmen.

Zusätzlich war die Receipt-Revalidierung zu schwach: Sie prüfte zwar Event-Key, Sequenz und Hash, blockierte aber nicht sicher, wenn nach dem idempotenten Cache-Reuse-Ereignis ein fremdes weiteres Ledger-Ereignis angehängt wurde.

## Korrektur

Produktionscommit:

`1acdeeabf65b46944785160e67c35bded5dd1121`

Regressionstest-Commit:

`7c3d3b9d3d0d62adc2ae4f369526a803ba47e710`

Geändert wurde:

- `src/ethusdc_bot/protocol_v3/transactional_cache_store.py`;
- `tests/unit/test_protocol_v3_task13_ledger_event_adapter.py`.

Der Adapter verwendet jetzt ausschließlich das echte Ledgerfeld `event_sha256` und schreibt dessen validierten Wert in `ledger_receipt.event_hash`.

Für ein vorhandenes oder neu angehängtes Cache-Reuse-Ereignis müssen gleichzeitig gelten:

- exakt ein passender Event-Key;
- Sequenz exakt `decision_event_count + 1`;
- Ledger-Eventzahl exakt gleich dieser Sequenz;
- Ledger-HEAD exakt gleich `event_sha256` dieses Events.

Ein späterer fremder Ledgerfortschritt blockiert Cache-Hit, Resume und weitere Checkpoint-Fortsetzung fail-closed.

## Regressionstest

Der neue Test verwendet das echte Task-4-Ledger und bestätigt:

- das Ledger-Event enthält `event_sha256`;
- das Ledger-Event enthält kein `event_hash`;
- `ledger_receipt.event_hash` entspricht exakt dem echten `event_sha256`;
- der Ledger-HEAD entspricht dem gebundenen Event;
- ein danach angehängtes fremdes Cache-Reuse-Ereignis blockiert die Fortsetzung.

## CI

Review CI Run 443 war vollständig grün:

`https://github.com/boomarank2-commits/ETHUSDC_BotV3_Hermes/actions/runs/29567264398`

Grün waren:

- vollständige Pytest-Suite;
- Python-Kompilierung;
- PowerShell-Syntax;
- Whitespace-Prüfung;
- abschließendes Pytest-Gate.

## Grenzen

Keine Aufgabe 14 oder später wurde durch diese Korrektur vorgezogen.

Unverändert gesperrt bleiben:

- Paper;
- Testtrade;
- Live;
- Orders;
- private Endpunkte;
- API-Keys.

Exakt nächster zulässiger Schritt ist Aufgabe 14 – exakter innerer 6×60-Tage-Fold-Planer.
