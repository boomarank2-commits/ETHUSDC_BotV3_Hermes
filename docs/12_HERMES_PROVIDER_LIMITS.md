# 12 - Hermes Provider Limits

Diese Datei klaert ein wichtiges Missverstaendnis:

Hermes kann GitHub-Tools nutzen, aber Hermes braucht trotzdem ein aktives Sprachmodell, um Nutzeraufgaben zu verstehen und Tool-Aufrufe zu planen.

---

## 1. GitHub-Zugriff vs. Denkmodell

GitHub-Zugriff und Denkmodell sind zwei verschiedene Dinge.

```text
GitHub Token / Skills = Dateien, Issues, PRs lesen und schreiben
Inference Provider = Denken, Planen, Entscheiden, Tool-Aufrufe auswaehlen
```

Wenn der aktive Inference Provider `OpenAI Codex` ist und dessen Quota erschoepft ist, kann Hermes keine Aufgabe bearbeiten, auch wenn der GitHub-Token gueltig ist.

---

## 2. Aktueller Zustand

Aktuell ist Hermes so konfiguriert:

```text
Provider: OpenAI Codex
Model: gpt-5.5
GitHub Token: vorhanden
Credentials: gueltig
Blocker: Codex provider quota exhausted HTTP 429
```

Das bedeutet:

- GitHub ist nicht der Blocker.
- Credentials sind nicht der Blocker.
- Der aktive Denk-/Inference-Provider ist der Blocker.

---

## 3. Was ohne Codex geht

Ohne freie Codex-Quota kann Hermes nicht sinnvoll auf Nutzeranweisungen reagieren, solange OpenAI Codex der aktive Provider ist.

Moeglich sind dann nur externe Wege:

- Nutzer wartet auf Quota-Reset.
- Nutzer stellt Hermes auf einen anderen verfuegbaren Provider um.
- ChatGPT arbeitet direkt ueber GitHub an kleinen Aufgaben.
- Nutzer erstellt manuell Issues/Dateien.

---

## 4. Provider-Optionen

Moegliche Wege:

### Option A - Warten

Auf Codex-Reset warten und danach Hermes normal mit OpenAI Codex / gpt-5.5 starten.

Vorteil:

- beste geplante Qualitaet fuer das Projekt
- keine neuen Kosten
- keine neue Provider-Komplexitaet

Nachteil:

- Wartezeit

### Option B - OpenAI API

Hermes von `OpenAI Codex` auf `OpenAI API` umstellen.

Voraussetzung:

- eigener OpenAI API Key
- API-Abrechnung aktiv

Vorteil:

- unabhaengiger vom ChatGPT/Codex-Quota

Nachteil:

- kann Zusatzkosten erzeugen
- API Key muss sicher lokal gespeichert werden

### Option C - GitHub Copilot Provider

Hermes auf GitHub Copilot als Provider umstellen, falls Hermes diesen Provider unterstuetzt und Copilot beim Nutzer aktiv/authentifiziert ist.

Vorteil:

- kann als Ausweichmodell dienen

Nachteil:

- Qualitaet/Verfuegbarkeit muss getestet werden
- nicht als Hauptwahrheit fuer grosse Bot-Architektur geplant

### Option D - Nous Portal oder anderer Provider

Hermes auf einen anderen vorhandenen Provider stellen, falls Konto/Key vorhanden ist.

Vorteil:

- Ausweichweg

Nachteil:

- zusaetzliche Einrichtung
- Qualitaet/Limit/Kosten unklar

---

## 5. Empfohlene Projektregel

Standard:

```text
Hauptprovider fuer wichtige Bot-Arbeit: OpenAI Codex / gpt-5.5
Fallback fuer kleine GitHub-/Planungsaufgaben: nur wenn stabil getestet
```

Wenn Codex leer ist, soll Hermes nicht versuchen, endlos erneut zu starten.

Hermes soll dann:

1. Blocker melden,
2. keine Aufgabe starten,
3. Handoff/Issue durch externen GitHub-Weg aktualisieren lassen,
4. nach Reset fortsetzen.

---

## 6. Was der Nutzer Hermes sagen kann

Nach Reset:

```text
Nutze OpenAI Codex / gpt-5.5 fuer die Planung.
Arbeite 30 Minuten an Issues #1 und #2.
Danach Handoff in GitHub speichern.
```

Wenn ein anderer Provider getestet werden soll:

```text
Oeffne hermes setup model und stelle einen verfuegbaren Fallback-Provider ein.
Teste nur Repository-Lesen und Issue-Lesen.
Keine Codearbeit.
```

---

## 7. Wichtige Klarstellung

Hermes kann nicht komplett ohne Denkmodell arbeiten.

GitHub-Schreiben selbst braucht kein Codex, aber Hermes braucht ein Modell, um zu entscheiden, was es schreiben soll.

Wenn der aktive Denkprovider blockiert ist, ist Hermes als Agent blockiert.
