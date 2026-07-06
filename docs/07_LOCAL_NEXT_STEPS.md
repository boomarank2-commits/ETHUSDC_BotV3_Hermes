# 07 - Local Next Steps

Diese Datei beschreibt den naechsten lokalen Ablauf auf dem Windows-PC.

---

## 1. Lokalen Arbeitsordner verwenden

Hermes-Arbeitsordner:

```powershell
C:\TradingBot\hermes-agent
```

Bot-Repository lokal klonen nach:

```powershell
C:\TradingBot\hermes-agent\ETHUSDC_BotV3_Hermes
```

Befehl:

```powershell
cd C:\TradingBot\hermes-agent
git clone https://github.com/boomarank2-commits/ETHUSDC_BotV3_Hermes.git
cd ETHUSDC_BotV3_Hermes
git status
```

---

## 2. Hermes aus dem richtigen Ordner starten

Hermes darf nicht aus dem Installationsordner gestartet werden.

Richtig:

```powershell
cd C:\TradingBot\hermes-agent
hermes
```

Falsch:

```powershell
C:\Users\booma\AppData\Local\hermes\hermes-agent
```

---

## 3. Wenn Codex wieder frei ist

In Hermes eingeben:

```text
Lies im Repository ETHUSDC_BotV3_Hermes die Datei docs/06_HERMES_BOOTSTRAP_PROMPT.md und fuehre den Prompt aus.
Plane zuerst. Aendere keine Dateien, erstelle keine Ordner und fuehre keinen Code aus, bis ich bestaetige.
```

---

## 4. Erste erwartete Hermes-Antwort

Hermes soll zuerst nur ausgeben:

- lokale Ordnerstruktur
- GitHub-Struktur
- Kanban-Spalten
- Agentenrollen
- erste 10 Tickets
- Abnahmekriterien
- Risiken
- Nutzerfreigaben

Hermes darf in dieser ersten Antwort noch nichts veraendern.

---

## 5. Danach

Der Nutzer kopiert Hermes' Plan zur externen Pruefung in ChatGPT.

Erst nach Freigabe darf Hermes Phase 1 starten.
