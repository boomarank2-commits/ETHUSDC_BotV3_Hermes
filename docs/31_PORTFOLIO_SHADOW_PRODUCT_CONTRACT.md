# 31 - Verbindlicher Portfolio- und Shadow-Produktvertrag

Stand: 2026-07-13

Dieses Dokument ist die verbindliche fachliche Vorgabe fuer alle neuen
Backtest-, Portfolio-, Dashboard- und Shadow-Funktionen. Bei Widerspruechen zu
aelteren Zielbeschreibungen gilt dieses Dokument. Die Forschungs- und
Leakage-Schutzregeln aus Research Protocol v2 bleiben davon unberuehrt.

## 1. Markt und Handelsrichtung

- Gehandeltes Paar: ausschliesslich `ETHUSDC`.
- Boerse/Markt: Binance Spot.
- Richtung: ausschliesslich LONG.
- Shorts, Margin, Futures und Leverage bleiben verboten.
- `BTCUSDC` und `ETHBTC` duerfen nur Kontext liefern und niemals selbst einen
  Trade oder eine Order ausloesen.

## 2. Kapitalmodell

- Ein logisches Lot hat immer exakt `100 USDC` Entry-Notional.
- Es gibt kein Compounding. Gewinn oder Verlust eines Lots veraendert die
  Groesse des naechsten Lots nicht.
- Das Deployment-Budget wird manuell gewaehlt und begrenzt die Summe der
  gleichzeitig reservierten Entry-Notionals.
- Unterstuetzte Stufen sind zunaechst:

| Deployment-Budget | Maximale offene Lots | Lotgroesse |
|---:|---:|---:|
| 100 USDC | 1 | 100 USDC |
| 200 USDC | 2 | 100 USDC |
| 500 USDC | 5 | 100 USDC |
| 1000 USDC | 10 | 100 USDC |

- Ein groesseres Budget garantiert weder mehr Signale noch linearen Gewinn.
- Das kanonische Research-Profil bleibt vorerst `100 USDC / 1 Lot`. Groessere
  Budgetprofile duerfen einen versiegelten Holdout nicht wiederholt oeffnen.

## 3. Kosten und Risikohinweise

- Baseline-Fee: `0,1 %` beziehungsweise `10 bps` pro Seite.
- Baseline-Slippage: `5 bps` pro Seite.
- Ein spaeterer BNB-Rabatt ist kein Bestandteil der Baseline.
- `15 %` des gewaehlten Deployment-Budgets ist ein weicher
  Drawdown-Richtwert und eine Skalierungswarnung, keine Gewinn- oder
  Freigabegarantie.
- Die unveraenderliche Quality-Gate-v1-Grenze von `15 USDC` fuer das
  kanonische 100-USDC-Profil bleibt separat bestehen. Eine Lockerung benoetigt
  eine neue, vor der Auswertung eingefrorene Gate-Version.
- `200 USDC` Drawdown bei einem 100-USDC-Testprofil ist offensichtlich
  unbrauchbar und darf niemals als akzeptabel dargestellt werden.

## 4. Ertragsrichtwerte

Alle Werte sind Richtwerte nach Fees und Slippage, gemittelt ueber alle
Kalendertage einschliesslich Tage ohne Trade. Sie sind keine Zusage und duerfen
nicht als Suchparameter auf einen Holdout optimiert werden.

| Budget | akzeptabler Richtwert | gewuenschter Richtwert |
|---:|---:|---:|
| 100 USDC | 3 USDC/Tag | 3 USDC/Tag |
| 200 USDC | 5 USDC/Tag | 6 USDC/Tag |
| 500 USDC | 12 USDC/Tag | 15 USDC/Tag |
| 1000 USDC | 25 USDC/Tag | 30 USDC/Tag |

Reports muessen zusaetzlich den Nettoertrag je `100 USDC` Deployment-Budget
ausweisen. Unterschiedliche Tagesergebnisse wie 0, 6, 3, 6, 0 sind zulaessig;
massgeblich ist der ehrliche Durchschnitt ueber den festgelegten Zeitraum.

Ein groesseres Budgetprofil darf nur dann als eigenes gruenes Ergebnis gelten,
wenn genau dieses Profil mit seiner realen Lot-Auslastung und seinen Kosten
separat geprueft wurde. Ein gruener 100-USDC-Nachweis darf nicht lediglich
mathematisch auf 200, 500 oder 1000 USDC hochgerechnet werden.

## 5. Ergebnisampel und Uebernahme

- **Gruen:** alle Robustheits- und Sicherheitspruefungen bestanden und der fuer
  das tatsaechlich bewertete Deployment-Budget geltende gewuenschte Richtwert
  erreicht.
- **Gelb:** alle Robustheits- und Sicherheitspruefungen bestanden, Ergebnis
  netto positiv, Richtwert aber verfehlt.
- **Rot:** fehlende/ungueltige Evidenz, Identitaetsfehler, Safety- oder
  Robustheitsfehler oder kein positiver Nettoertrag.
- Gruen und Gelb duerfen nach menschlicher Aktion in den strikt orderfreien
  Shadow-Modus uebernommen werden. Rot darf nicht uebernommen werden.
- Zielerreichung und Robustheit sind getrennte Tatsachen. Ein verfehlter
  Richtwert darf kein robustes positives Ergebnis verbergen; ein erreichter
  Richtwert darf Robustheitsfehler niemals ueberstimmen.

## 6. Shadow-Modus

`Backtest uebernehmen` bedeutet ausschliesslich:

- Kandidat und Ausfuehrungsprofil kryptografisch an einen kanonischen
  Finalbericht binden.
- Oeffentliche Marktdaten beobachten.
- Hypothetische Ein- und Ausstiege mit derselben deterministischen Engine wie
  im Backtest erzeugen und dauerhaft protokollieren.
- Soll-/Ist-Abweichungen zum Backtest sichtbar machen.

Im Shadow-Modus gelten unverhandelbar:

- keine echten Orders,
- keine Trading-API,
- keine Kontodaten,
- keine API-Keys,
- keine Signaturen oder privaten Endpunkte,
- kein automatischer Uebergang zu Testtrade oder Live.

Laufende Shadow-Daten werden ausserhalb des Git-Repositories gespeichert. Ein
UI-Refresh darf keinen Zustand veraendern. Datenluecken, Manipulationen oder
unklare Reihenfolgen muessen fail-closed pausieren; es duerfen keine Kerzen,
Fills oder Trades erfunden werden.

## 7. Spaetere reale Freigabe

Paper, Testtrade und Live bleiben technisch gesperrt. Nach mehreren Monaten
stabiler Shadow-Beobachtung kann der Nutzer eine separate Entwicklungs- und
Freigabephase beauftragen. Diese beginnt manuell mit 100 USDC. Eine Skalierung
auf 500 oder 1000 USDC ist ebenfalls eine eigene manuelle Entscheidung und
darf nie automatisch erfolgen.

## 8. Aktuelle Evidenzgrenze

Der aktuell lokale ETHUSDC-1m-Bestand umfasst 2023-07-09 bis 2026-07-07. Das
darin enthaltene Fenster 2025-07-08 bis 2026-07-07 wurde bereits als Audit-
beziehungsweise Holdout-Fenster konsumiert. Es darf nicht erneut als frisch,
blind oder versiegelt bezeichnet werden.

Protocol-v3-Vertragsgeneration `3.0.0` erlaubt ausschliesslich, die damals
kausal beobachtbaren Rohmarktwerte dieses Zeitraums in einer spaeteren
Monthly-Origin als normale Historie zu verwenden. PnL, Rankings, Reports,
Gate-Ergebnisse, Auswahlentscheidungen und menschliche Ergebnisinterpretationen
aus frueheren Origins oder dem konsumierten Audit duerfen niemals in einen
spaeteren Fit zurueckgespielt werden.

Damit sind Training, WFV, Infrastrukturtests, der retrospektive
`monthly_process_oos` und kuenftiges Forward-Shadow moeglich. Der historische
Monatsprozess bleibt jedoch `diagnostic_only` und `NOT_FRESH`. Ein neuer ehrlicher
365-Tage-Finalnachweis ist erst moeglich, wenn ein separates, nicht konsumiertes
und vorab versiegeltes Pipeline-Finalfenster verfuegbar ist. Bis dahin darf die
UI keinen gruenen oder gelben echten Finalstatus erfinden.

## 9. Nicht verhandelbare Ehrlichkeit

Das System kann nach einer Strategie mit durchschnittlich etwa 3 USDC pro Tag
suchen und deren Evidenz pruefen. Es kann diesen Ertrag nicht garantieren. Wenn
kein Kandidat die Regeln besteht, ist das korrekte Ergebnis Rot mit konkreten
Blockern und nicht eine nachtraegliche Anpassung des Holdouts oder der Kosten.

## 10. Protocol-v3-Shadow- und Finaltrennung

Protocol-v3-Vertragsgeneration: `3.0.0`  
Maschinenlesbarer Vertrag: `configs/protocol_v3_contract.json`  
Kanonischer Zusatzvertrag: `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`

Die folgenden Evidenz- und Shadow-Klassen sind strikt getrennt:

- `monthly_process_oos`: retrospektiver Pseudo-Live-Nachweis der monatlich refittenden Pipeline; auf der vorhandenen Historie nicht frisch und nicht adoptierbar.
- `consumed_audit`: dauerhaft verbrauchter Zeitraum; Rohmarktbeobachtungen duerfen nur unter der engen kausalen Rolling-Reuse-Regel als Historie dienen.
- `sealed_final_holdout`: einzig moeglicher spaeterer kanonischer Protocol-v3-Finalnachweis; vorab registriert, wirklich neu, 365 Tage versiegelt und erst danach einmal geoeffnet.
- `forward_shadow_month`: nach Einfrieren einer Pipelinegeneration wirklich neu entstandener append-only Monat; frische Beobachtung, aber kein Finalnachweis.
- `research_challenger_shadow`: separat, manuell und strikt orderfrei; weder kanonische Adoption noch Paper-, Testtrade-, Live- oder Orderfreigabe.
- `diagnostic_only`: darf Diagnose erzeugen, aber keinen Finalstatus oder Trading-Pfad freigeben.

Der vorhandene kanonische Single-Candidate-Shadow bleibt an seinen eigenen
Finalbericht gebunden. Ein retrospektiver Protocol-v3-Challenger darf niemals
ueber den bestehenden `adopt_for_shadow`-Pfad angenommen werden. Protocol v2 und
der Single-Candidate-Finalrunner bleiben erhalten, koennen aber keinen
Protocol-v3-Finalstatus erzeugen.
