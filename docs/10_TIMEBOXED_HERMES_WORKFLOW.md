# 10 - Timeboxed Hermes Workflow

Diese Datei ist verbindlich fuer Hermes-Arbeitssitzungen.

Der Nutzer will, dass Hermes kontrolliert arbeitet und jederzeit nach Neustart fortsetzen kann.

---

## 1. Grundsatz

Hermes arbeitet niemals endlos und niemals unkontrolliert.

Jede Arbeitssitzung hat eine vom Nutzer genannte Laufzeit, zum Beispiel:

```text
Arbeite 45 Minuten an Ticket X.
Danach stoppen, alles sichern und Handoff aktualisieren.
```

Wenn keine Laufzeit genannt wird, muss Hermes nachfragen oder maximal nur planen.

---

## 2. Was Hermes vor jeder Sitzung tun muss

Vor Beginn einer Arbeitssitzung:

1. Repository-Status pruefen.
2. AGENTS.md lesen.
3. PROJECT_CONTRACT.md lesen.
4. Aktuelles Ticket lesen.
5. Aktuelles Handoff lesen, falls vorhanden.
6. Arbeitszeitlimit bestaetigen.
7. Geplante Schritte kurz ausgeben.
8. Erst danach beginnen.

---

## 3. Arbeitszeitlimit

Hermes muss die Nutzerzeit respektieren.

Beispiele:

- `Arbeite 15 Minuten` = kurze Diagnose oder kleiner Fix
- `Arbeite 45 Minuten` = normale Umsetzung eines kleinen Tickets
- `Arbeite 90 Minuten` = groessere Umsetzung mit Tests, nur wenn Nutzer es ausdruecklich erlaubt

Nach Ablauf der Zeit muss Hermes stoppen und sichern.

Wenn die Aufgabe nicht fertig ist, ist das kein Fehler. Dann wird ein Fortsetzungs-Handoff geschrieben.

---

## 4. Was Hermes am Ende jeder Sitzung tun muss

Am Ende jeder Sitzung, egal ob erfolgreich oder abgebrochen:

1. Alle Aenderungen zusammenfassen.
2. Git-Status dokumentieren.
3. Geaenderte Dateien nennen.
4. Tests nennen, die ausgefuehrt wurden.
5. Tests nennen, die nicht ausgefuehrt wurden.
6. Offene Blocker nennen.
7. Naechsten kleinsten Schritt nennen.
8. Handoff aktualisieren.
9. GitHub aktualisieren, falls erlaubt.
10. Dem Nutzer sagen, ob Neustart/Weiterarbeit sicher moeglich ist.

---

## 5. Handoff-Pflichtdateien

Hermes soll spaeter im Projekt eine maschinenlesbare und eine menschenlesbare Fortschrittsstruktur fuehren.

Geplante lokale/Repository-Struktur:

```text
handoff/
  CURRENT_STATUS.md
  SESSION_LOG.md
  NEXT_ACTION.md
  BLOCKERS.md
  LAST_KNOWN_GOOD.md
runtime/
  runtime_state.json
  progress_state.json
  locks.json
reports/
  summary/
  backtests/
  paper/
```

Grosse Reports und Rohdaten bleiben lokal und werden nicht ungeprueft in GitHub geladen.

---

## 6. Fortsetzen nach Neustart

Hermes muss nach einem Neustart immer zuerst lesen:

1. `AGENTS.md`
2. `PROJECT_CONTRACT.md`
3. `docs/09_BOOTSTRAP_HANDOFF.md`
4. spaeter `handoff/CURRENT_STATUS.md`
5. spaeter `handoff/NEXT_ACTION.md`
6. offenes GitHub-Issue/Ticket
7. Git-Status

Danach muss Hermes sagen:

- Wo wurde aufgehört?
- Was war der letzte sichere Zustand?
- Welche Datei/Phase war aktiv?
- Was ist der naechste kleinste Schritt?
- Braucht es Nutzerfreigabe?

---

## 7. Keine halbfertigen stillen Zustaende

Hermes darf nicht mitten in einer Aenderung aufhoeren, ohne den Zustand zu dokumentieren.

Wenn eine Aenderung unvollstaendig ist:

- klar markieren,
- nicht als fertig ausgeben,
- Tests nicht als bestanden behaupten,
- naechsten Schritt dokumentieren,
- Nutzer informieren.

---

## 8. GitHub-Arbeitsweise

Hermes darf GitHub nutzen fuer:

- Issues
- Kommentare
- Handoffs
- kleine Dokumentationsupdates
- Branches/PRs, wenn Code geaendert wird

Fuer Code gilt:

- nicht wild direkt auf main,
- groessere Aenderungen per Branch/PR,
- Sicherheitscheck im PR-Template,
- Nutzerfreigabe bei groesseren Schritten.

---

## 9. Codex-Limit oder Modell-Limit

Wenn Codex oder ein Modell wegen Limit blockiert:

Hermes darf trotzdem:

- GitHub lesen,
- Issues erstellen,
- Plan aktualisieren,
- Handoff aktualisieren,
- naechste Tickets vorbereiten,
- Nutzer informieren.

Hermes darf dann nicht behaupten, Code sei implementiert worden.

---

## 10. Stop-Regel

Wenn der Nutzer sagt:

```text
Stopp
Pause
Beende nach Handoff
```

muss Hermes:

1. keine neue Aufgabe beginnen,
2. laufende Aenderung sicher abschliessen oder als unfertig markieren,
3. Handoff schreiben,
4. GitHub/Git-Status melden,
5. auf weitere Freigabe warten.

---

## 11. Erfolg einer Sitzung

Eine Sitzung ist erfolgreich, wenn am Ende klar ist:

- was gemacht wurde,
- was nicht gemacht wurde,
- welcher Stand sicher ist,
- welche Tests liefen,
- wo weitergemacht wird,
- ob Nutzerfreigabe gebraucht wird.

Nicht erforderlich ist, dass ein grosses Ziel in einer Sitzung komplett fertig wird.
