# Protocol v3 – Aufgabe 33 Start-Handoff

Stand: 2026-07-22

## Status

Aufgabe 33 – `Erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht` – ist `IN_PROGRESS`.

## Erlaubter Umfang

- ausschließlich der historische `monthly_process_oos` mit zwölf Origins und exakt 365 OOS-Tagen;
- reale lokale Binance-Public-Data und vollständig auditierte Digests;
- Wiederverwendung der bestehenden Protocol-v3-Kette, Task-13-Resume und Cache;
- ehrlicher Status `TARGET_REACHED`, `TARGET_NOT_REACHED`, `NO_EDGE_FOUND` oder ein reproduzierbarer `BLOCKED_*`-Status.

## Startnachweise

- Task 31 erneut auditiert: 41 zielgerichtete Tests und 1.305/1.305 Baseline-Tests grün;
- Task 32 abgeschlossen: 1.321/1.321 Tests lokal grün;
- Task-32-Technik-CI `29924203612` grün;
- Task-32-Dokumentations-CI `29925381805` grün;
- GitHub-Issue `#19` angelegt;
- Branch und Remote auf Commit `3bb23905ecbac38233e18c074ecc55acf0d45ad4` synchron und vor Task-33-Start sauber.

## Vorläufiger Datenbefund

Der lokale Bestand besitzt für ETHUSDC und BTCUSDC je 1.095 Tagesarchive von `2023-07-09` bis `2026-07-07`; ETHBTC besitzt zusätzlich `2026-07-08`. Der verbindliche Warmup von 20 Tagen plus einer 1m-Quellbar beginnt für den festgelegten Prozess bei `2023-06-18T23:59:00Z`. Die dafür erforderlichen vollständigen UTC-Tagesarchive ab `2023-06-18` fehlen derzeit bei allen drei Märkten und müssen ausschließlich über das vorhandene öffentliche Downloadwerkzeug ergänzt und danach vollständig auditiert werden.

## Sicherheitsgrenze

Kein `sealed_final_holdout`, keine Adoption, kein `active_config.json`, kein Paper, Testtrade, Live, Orderpfad, privater Endpunkt oder API-Key. Task-32-Fixtures sind keine Task-33-Evidenz.
