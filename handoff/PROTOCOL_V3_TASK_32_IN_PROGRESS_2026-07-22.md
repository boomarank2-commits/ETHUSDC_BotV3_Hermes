# Protocol v3 – Aufgabe 32 Arbeitsnachweis

Stand: 2026-07-22

Status: `IN_PROGRESS`

GitHub-Ticket: `#18 – Protocol v3 Task 32: E2E parity and fault-injection acceptance`

## Eintrittsnachweis

Aufgabe 31 wurde vor der ersten Task-32-Codeänderung erneut unabhängig geprüft:

- 41/41 gezielte Task-31-Tests erfolgreich;
- vollständige Repository-Suite mit 1.305/1.305 Tests erfolgreich;
- dedizierte Vorregistrierungs-, Claim-, Progress-, Task-13-Checkpoint-, Attestation- und genau-einmalige Reportkette geprüft;
- generischer Task-11-Finalpfad bleibt absichtlich gesperrt;
- kein echtes Finalfenster wurde registriert, geclaimt, gelesen, ausgeführt oder geöffnet.

## Aktiver Umfang

Aufgabe 32 setzt ausschließlich `handoff/NEXT_ACTION.md` um. Der vollständige Dry-Run bleibt synthetisch und muss außerhalb der kanonischen Reportroots isoliert sein. Erstlauf, Resume, Cache und Replay müssen dieselben semantischen Identitäten liefern. Alle vorgeschriebenen Fehlerklassen müssen fail-closed geprüft werden.

## Sicherheitsgrenze

- keine echte neue 365-Tage-Evidenz;
- kein Start von Aufgabe 33;
- keine Orders, Trading-API, API-Keys, Paper-, Testtrade- oder Live-Freigabe;
- keine Adoption und keine Änderung von `active_config.json`;
- Fixture- oder Dry-Run-Artefakte dürfen keinen echten Protocol-v3-Finalstatus beanspruchen.
