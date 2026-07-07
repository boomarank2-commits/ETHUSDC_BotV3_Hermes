# 13 - AI Worksplit and Codex Budget

Diese Datei legt fest, wie Hermes, ChatGPT, GitHub, Copilot und Codex zusammenarbeiten sollen, ohne das Codex-Limit unnoetig zu verbrauchen.

---

## 1. Grundsatz

Codex ist wertvoll und soll nicht fuer jede kleine Planungs- oder Kommunikationsaufgabe verbraucht werden.

Ziel:

```text
Hermes = Orchestrator und Kommunikationszentrum
GitHub = Projektgedaechtnis, Aufgaben, Handoff, Historie
ChatGPT = externe Projektleitung, Review, Prompt-/Ticket-Schaerfung
Codex = gezielter Umsetzer fuer schwere Codearbeit
Copilot/anderer Fallback = optional fuer leichte Assistenz, wenn stabil verfuegbar
```

---

## 2. Codex nur gezielt verwenden

Codex soll nur genutzt werden fuer:

- echte Code-Implementierung
- komplexe Bugfixes
- Refactoring ueber mehrere Dateien
- Tests schreiben oder reparieren
- Backtest-/Engine-Fehler lokalisieren
- schwierige Architekturdetails, wenn einfache Planung nicht reicht

Codex soll nicht verbraucht werden fuer:

- lange Projektzusammenfassungen
- einfache Issue-Kommentare
- reine Handoff-Texte
- reine Dokumentationspflege
- wiederholtes Lesen derselben Projektregeln
- unkontrollierte Endlosschleifen
- grosse freie Diskussionen ohne klares Ticket

---

## 3. Kommunikationsweg

Der bevorzugte Weg ist:

1. ChatGPT schreibt oder schaerft Regeln/Tickets in GitHub.
2. Hermes liest GitHub und plant.
3. Hermes erzeugt ein kleines, klares Ticket.
4. Der Nutzer gibt die naechste Timebox frei.
5. Hermes nutzt Codex nur, wenn das Ticket Codearbeit wirklich braucht.
6. Nach der Timebox schreibt Hermes Handoff/Status.
7. ChatGPT kann den Handoff pruefen und bei Bedarf GitHub-Tickets schaerfen.

---

## 4. Timebox mit Budget

Jede Hermes-Sitzung braucht eine Zeitbox und ein Codex-Budget.

Beispiele:

```text
Arbeite 30 Minuten. Nur lesen und planen. Kein Codex-Codeauftrag.
```

```text
Arbeite 45 Minuten an Ticket X. Codex nur verwenden, wenn eine konkrete Datei geaendert werden muss. Maximal ein Codex-Implementierungsblock.
```

```text
Arbeite 90 Minuten an Backtest-Fehler Y. Codex erlaubt fuer Diagnose und Fix. Nach jedem fehlgeschlagenen Test stoppen und Handoff schreiben.
```

---

## 5. Startmodus nach Reset

Nach einem Codex-Reset soll Hermes nicht sofort bauen.

Erster Start:

- Issues #1, #2 und #3 lesen
- genannte Dokumente lesen
- 30 Minuten nur Planungsmodus
- keine Codeaenderung
- kein grosser Codex-Implementierungsauftrag
- Handoff als GitHub-Kommentar speichern
- auf Nutzerfreigabe warten

---

## 6. Wann Hermes den Nutzer fragen muss

Hermes muss fragen, bevor:

- Codex fuer groessere Umsetzung gestartet wird
- mehrere Dateien geaendert werden
- ein Backtest lange laufen soll
- Daten massiv heruntergeladen werden
- eine neue Abhaengigkeit eingefuehrt wird
- UI/Engine/Backtest-Struktur groesser geaendert wird
- Live/Testtrade/Paper freigegeben wird

---

## 7. Sparsame Kontextstrategie

Hermes soll nicht bei jedem Ticket alle Dokumente vollstaendig in den Kontext laden, wenn ein Handoff und die relevanten Regeln reichen.

Empfohlene Reihenfolge:

1. AGENTS.md und PROJECT_CONTRACT.md fuer harte Regeln
2. aktuelles Issue
3. letztes Handoff
4. nur relevante Detaildokumente
5. keine unnoetigen alten Logs laden

---

## 8. Fallback-Regel

Wenn ein leichter Provider wie Copilot oder LM Studio stabil funktioniert, darf Hermes ihn fuer leichte Aufgaben verwenden:

- Issue lesen
- Handoff schreiben
- kleine Planung
- Dokumentationszusammenfassung

Codex bleibt fuer schwere Umsetzung reserviert.

Wenn kein Fallback stabil funktioniert, arbeitet Hermes mit Codex nur in kurzen, klaren Timeboxen.

---

## 9. Fertig ist nur, was belegt ist

Auch bei Codex-Sparmodus gilt:

- keine Fake-Trades
- keine Fake-Reports
- keine Blindtest-Leakage
- keine Gate-Lockerung
- keine ungetestete Fertigmeldung
- keine zweite Wahrheit

---

## 10. Kurzregel fuer Hermes

```text
Denke sparsam. Lies gezielt. Nutze GitHub als Gedaechtnis. Nutze Codex nur fuer konkrete Codearbeit. Stoppe nach der Timebox. Schreibe Handoff. Warte auf Freigabe.
```
