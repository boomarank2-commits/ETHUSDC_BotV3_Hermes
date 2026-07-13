# Monatlicher ETHUSDC-Research-Blueprint

Stand: 2026-07-13

Status: verbindliche Forschungs- und Umsetzungsgrundlage, noch keine Implementierung

Zielmarkt: Binance Spot `ETHUSDC`, LONG-only

Bei einem Widerspruch bleiben `AGENTS.md`, `PROJECT_CONTRACT.md` und
insbesondere `docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md` vorrangig. Dieses
Dokument ergaenzt sie ausschliesslich als Protocol-v3-Blueprint. Protocol v3
wird erst nach einer ausdruecklich versionierten Vertragsuebernahme daraus zu
ausfuehrbarem Produktverhalten.

## 1. Entscheidung in einem Satz

Der Bot darf nicht versuchen, eine einmal gefundene feste Strategie jahrelang
auszufuehren. Er muss die **vorab festgelegte monatliche Auswahlpipeline**
historisch so testen, wie sie spaeter wirklich betrieben wird: jeweils nur die
vorherigen 730 vollstaendigen UTC-Tage sehen, darin Kandidaten und Parameter
waehlen, im exakt folgenden Deployment-Intervall erst nach dem festen
24-Stunden-Delay neue Entries zulassen und zwoelf solche Intervalle zu einem
365-Tage-Prozess-OOS verbinden.

Der Champion ist damit die versionierte Auswahlpipeline, nicht ein dauerhaft
fixer Parametersatz.

## 2. Was diese Untersuchung ehrlich festgestellt hat

Die letzten drei Jahre enthalten im Rueckblick genug Intraday-Bewegung, um das
Ziel mit perfektem Zukunftswissen und mindestens einer idealen
Tagesentscheidung rechnerisch zu konstruieren. Die gleichen Daten zeigen aber
keinen einfachen kausalen Zeit-, Momentum-, Tagesrichtungs- oder Kontext-Edge,
der nach Kosten auch nur in die Naehe von 3 USDC pro Kalendertag kommt. Die
breiten Tagesregeln falsifizieren dabei **nicht** jede sauber bestaetigte
Pullback-/Reclaim- oder mehrtaegige Strategie; genau diese engeren Hypothesen
muessen erst durch das unten definierte Protokoll geprueft werden.

Das bedeutet:

- Das Ziel ist als historisches Akzeptanzziel mathematisch nicht ausgeschlossen.
- Das Ziel ist extrem anspruchsvoll: Bei hoechstens einem Roundtrip pro Tag
  verlangt es rund 87 Prozent des nicht handelbaren perfekten
  Ein-Trade-Close-Benchmarks. Das ist keine Systemobergrenze fuer Kandidaten
  mit mehreren sequentiellen Trades.
- Ein Backtest darf deshalb niemals so lange Varianten erzeugen, bis zufaellig
  eine Zahl ueber 3 erscheint.
- `NO_TRADE` beziehungsweise Cash ist ein vollwertiges und haeufig korrektes
  Ergebnis.
- Ein historischer Kandidat darf hoechstens als strikt orderfreier
  Research-Challenger beobachtet werden, wenn die Auswahlmethode selbst im
  monatlichen Pseudo-Live-Prozess besteht. Das ist keine kanonische Uebernahme.

Es gibt keine Garantie, dass ein ehrlicher Backtest jemals einen Kandidaten mit
3 USDC pro Tag findet. Wenn kein solcher Edge in den Daten nachweisbar ist, muss
der korrekte Report `TARGET_NOT_REACHED` beziehungsweise `NO_EDGE_FOUND`
melden.

## 3. Verbindlicher Produktvertrag

| Feld | Verbindlicher Wert |
|---|---:|
| Handelsmarkt | ETHUSDC Spot |
| Richtung | LONG-only |
| reserviertes/angefordertes Lot | exakt 100 USDC Entry-Notional; Fees zusaetzlich |
| ausgefuehrtes Entry-Notional | wegen Step Size <= 100 USDC, beide Werte reporten |
| Gleichzeitig offene Positionen | maximal 1 Lot |
| Sequentielle Trades | erlaubt; harte Tages-/Haltedauergrenze je Kandidatenfamilie vorab fixiert |
| Compounding | aus |
| Basisgebuehr | 10 bps je Seite |
| Basisslippage | 5 bps adverse je Seite |
| Basiskosten Roundtrip | ungefaehr 0,30 USDC je 100-USDC-Trade |
| Kalenderbasis | No-Trade-Tage zaehlen mit 0 PnL |
| Kontextmaerkte | BTCUSDC und ETHBTC, niemals handelbar |
| Shorts/Margin/Futures/Leverage | verboten |
| Automatische Orders/Live-Aktivierung | verboten |
| Entwicklung je Monats-Origin | vorherige 730 vollstaendige UTC-Tage |
| Prozess-OOS | folgende 365 Tage, in 12 Monats-Origins |
| neue Entry-Geltung einer Konfiguration | ab Anker +24h bis zum naechsten Anker; Altposition exit-only |

`100 USDC` bezeichnet gemaess dem vorrangigen
`docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md` das angeforderte und reservierte
Entry-Notional eines logischen Lots. Die technisch ausgefuehrte Menge wird
abgerundet und kann deshalb ein geringeres Notional besitzen. Reports muessen
`requested_entry_notional_usdc=100`, `reserved_entry_notional_usdc=100` und
`executed_entry_notional_usdc<=100` getrennt ausweisen. Entry- und Exit-
Gebuehren werden zusaetzlich als Kosten verbucht. Gewinn oder Verlust veraendert
die angeforderte Groesse des naechsten Lots nicht.

Die `3 USDC/Tag` sind ein **nach dem versiegelten Prozess ausgewertetes
Akzeptanzziel**, niemals die Loss-Funktion der Suche. Kandidaten werden nur nach
den vorab eingefrorenen Robustheitskriterien gerankt. Eine Suche, die direkt
den Abstand zu 3 minimiert oder bis zum ersten Treffer weiterlaeuft, ist
unbrauchbar.

## 4. Datenbasis der Diagnose

Ausgewertet wurden die lokalen Binance-Spot-Rohdaten unter
`C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot`:

| Markt | Gemeinsamer Zeitraum | Vollstaendige Tage | 1m-Kerzen |
|---|---|---:|---:|
| ETHUSDC | 2023-07-09 bis 2026-07-07 | 1.095 | 1.576.800 |
| BTCUSDC | 2023-07-09 bis 2026-07-07 | 1.095 | 1.576.800 |
| ETHBTC | gemeinsamer Schnitt | 1.095 | 1.576.800 |

Jeder angenommene Tag besitzt exakt 1.440 fortlaufende Minutenkerzen. Im
gemeinsamen Zeitraum wurden keine Zeitluecken, doppelten Intervalle oder
ungueltigen OHLC-Zeilen festgestellt. 43.152 ETHUSDC-Kerzen beziehungsweise
2,74 Prozent besitzen Volumen null. Theoretische Extrempreis-Fills sind deshalb
besonders vorsichtig zu behandeln.

### 4.1 Marktstruktur

| Kennzahl | Ergebnis |
|---|---:|
| ETHUSDC Start -> Ende | 1.865,48 -> 1.770,57 USDC |
| Endpunkt-Rendite | -5,09 % |
| UTC-Open-to-Close positiv / negativ, vor Kosten | 552 / 543 |
| Median Tagesrange | 4,36 % |
| 75-%-Quantil Tagesrange | 6,46 % |
| 90-%-Quantil Tagesrange | 9,20 % |
| Median realisierte Tagesvolatilitaet | 2,83 % |
| Median Trend-Effizienz | 0,023 |
| Autokorrelation 1m / 15m / 60m / Tag | -0,025 / -0,004 / 0,003 / -0,014 |

Trend-Effizienz ist hier `absoluter Tages-Netto-Logreturn / Summe aller
absoluten 1m-Logreturns`. Der niedrige Median zeigt: Es gibt viel Bewegung,
aber nur einen kleinen gerichteten Anteil. Das ist ein schlechtes Umfeld fuer
kostenintensives Minutenscalping.

Die groesste durchschnittliche Stundenvolatilitaet lag um 14 bis 16 UTC. Die
durchschnittliche Richtung dieser Stunden war jedoch nahezu null. Uhrzeit ist
damit ein Opportunity-Merkmal, kein eigenstaendiges Long-Signal.

### 4.2 Perfekte Ein-Trade-Hindsight-Benchmarks

Fuer den ersten, bewusst optimistischen **All-Candle-Diagnosebenchmark** wurde
die Kostennaeherung

```text
K = (1 - 0,0015) / (1 + 0,0015) = 0,9970044933
net_return = sell / buy * K - 1
```

verwendet. Sie repraesentiert 10 bps Gebuehr plus 5 bps adverse Slippage je
Seite. Einsatz: 100 USDC, maximal ein Long-Trade pro UTC-Tag, kein Compounding.
Negative Tagesgelegenheiten werden als No-Trade mit 0 gewertet.

| Nicht handelbarer Benchmark | Mittel USDC/Kalendertag | Median | Tage >= 3 USDC | Summe 3 Jahre |
|---|---:|---:|---:|---:|
| perfekter spaeterer 1m-Close nach perfektem frueheren Close | 3,450 | 2,771 | 497/1.095 = 45,4 % | 3.777,77 |
| perfektes Low -> spaeteres High, Extremfill | 3,737 | 3,018 | 552/1.095 = 50,4 % | 4.092,30 |
| ungeordnete Tagesrange, nicht handelbar | 4,943 | 4,045 | 69,9 % | 5.412,35 |

Der Close-Benchmark kauft immer am im Nachhinein besten Minuten-Close und
verkauft am im Nachhinein besten spaeteren Minuten-Close. Er ist nicht
handelbar. Er ist eine Kapazitaetsreferenz fuer Systeme mit **hoechstens einem
Roundtrip pro Tag**, aber keine Obergrenze fuer den gesamten Bot: Ein kausales
System koennte mehrere nicht ueberlappende Roundtrips an einem Tag ausfuehren.
Fuer solche Kandidaten muss zusaetzlich ein kandidatengleicher Hindsight-
Benchmark mit derselben maximalen Tradezahl, Haltedauer und Zustandslogik
berechnet werden.

Die Zahlen in der Tabelle schliessen Nullvolumenkerzen noch nicht aus und sind
deshalb nur ein optimistischer Diagnosewert. Der formale Capture-Nenner muss
Entry und Exit auf Kerzen mit `volume>0` begrenzen und exakt denselben
Simulator mit Step-Size-Rundung, requested/executed Notional, Fees, Slippage,
Haltedauer und Handoff-State wie der Kandidat verwenden. Bis dieser handelbare
Benchmark vorliegt, darf die 80-/87-Prozent-Zahl keine Freigabe ausloesen.

Der kandidatengleiche Solver darf ausschliesslich diagnostisch nach Abschluss
laufen. Er verwendet dynamische Programmierung auf demselben Zeitraster und
dieselbe Long-only-/Ein-Lot-Zustandsmaschine, Kosten, maximale Tradezahl und
Haltedauer wie der Kandidat. Seine Entscheidungen oder Pfade duerfen niemals
Features, Labels, Kandidatenerzeugung oder Ranking speisen.

Konsequenzen:

- 3 USDC pro Tag entsprechen rund **87,0 Prozent des perfekten
  Ein-Trade-Close-Benchmarks**.
- Gegenueber dem optimistischen Ein-Trade-Low/High-Benchmark sind es immer noch
  80,3 Prozent.
- Selbst der perfekte Ein-Trade-Close-Benchmark bleibt an 54,6 Prozent der Tage
  unter 3 USDC.
- Nur 24 von 35 vollstaendigen Monatsabschnitten erreichten mit perfekter
  Close-Benchmark mindestens 3 USDC pro Tag.
- Im letzten 365-Tage-Block lag der perfekte Close-Benchmark bei 3,534 USDC/Tag,
  aber nur 169 von 365 Tagen erreichten einzeln mindestens 3 USDC.

Fuer einen Kandidaten mit hoechstens einem Trade pro Tag ist ein Ergebnis nahe
3 USDC/Tag daher automatisch ein Overfit-Warnsignal: Er behauptet dann, einen
sehr grossen Anteil perfekter Tageskenntnis kausal zu erfassen. Bei mehreren
Trades gilt nur der kandidatengleiche Benchmark als sinnvoller Nenner.

### 4.3 Erforderliche Bruttobewegung

Bei fest 100 USDC Entry-Notional pro Trade und ungefaehr 0,30 Prozent
Roundtrip-Kosten gilt naeherungsweise:

```text
erforderlicher Bruttoreturn je Trade = 0,30 % + 3,00 % / Trades_pro_Tag
```

| Trades pro Kalendertag | Erforderlicher durchschnittlicher Bruttoreturn je Trade, noch ohne Verlusttrades |
|---:|---:|
| 1 | 3,30 % |
| 2 | 1,80 % |
| 4 | 1,05 % |
| 6 | 0,80 % |
| 10 | 0,60 % |

Mit genau einem Roundtrip verlangt die verwendete multiplikative
Kostenkonvention exakt rund `3,3095 %` Bruttobewegung, um netto 3,00 USDC zu
erzielen.

Das Jahresziel entspricht `1.095 USDC` Netto-PnL auf wiederverwendetem
100-USDC-Lot-Notional. Das ist **keine** Behauptung von taeglichem Compounding,
aber wirtschaftlich trotzdem ein ausserordentlich aggressiver Richtwert.

Jeder Verlusttrade erhoeht diese Anforderung. Hohe Frequenz loest das Problem
nicht automatisch, weil zehn Roundtrips bereits rund 3 USDC Basiskosten pro Tag
verursachen.

### 4.4 Breite kausale Falsifikationstests

Die folgenden Regeln wurden bewusst breit und ohne nachtraegliche
Parameterkosmetik auf 730 Entwicklungstage und 365 spaetere Tage angewendet:

```text
Development: 2023-07-09 bis 2025-07-07 (730 UTC-Tage)
spaeterer Diagnoseblock: 2025-07-08 bis 2026-07-07 (365 UTC-Tage)
```

| Regel | Entwicklung USDC/Tag | spaetere 365 Tage USDC/Tag |
|---|---:|---:|
| taeglich 00-24 UTC Long | -0,202 | -0,337 |
| 00-08 UTC Long | -0,262 | -0,314 |
| 08-16 UTC Long | -0,334 | -0,392 |
| 16-24 UTC Long | -0,212 | -0,240 |
| erste 4h positiv -> Resttag Long | -0,117 | -0,159 |
| erste 4h negativ -> Resttag Long (grober Reversal-Proxy) | -0,074 | -0,241 |
| ETH, BTC und ETHBTC erste 4h positiv | -0,088 | -0,142 |
| vorherige 7 Tage ETH und BTC positiv | -0,090 | +0,019 |
| vorherige 7 Tage alle drei positiv | -0,060 | +0,015 |

Die letzten beiden kleinen positiven Spaetwerte replizieren nicht aus der
Entwicklung und besitzen nur ungefaehr PF 1,04. Sie sind kein nachgewiesener
Edge.

Weitere Befunde:

- Kein vorab geprueftes festes 1h-, 4h- oder 8h-Zeitfenster war in der
  Entwicklung nach Kosten positiv.
- Ein vorab bestimmter TP +3 % / SL -1,5 % ab 00 UTC verlor in Entwicklung und
  spaeterem Jahr.
- Vorherige hohe Volatilitaet prognostiziert die **Menge moeglicher Bewegung**.
  Das kausale Merkmal war die um einen Tag verschobene mittlere rohe
  Tagesrange der vorherigen 20 vollstaendigen UTC-Tage. Die nur auf den ersten
  730 Tagen gelernten Tertile waren `<= 4,430581 %`, `> 4,430581 % bis
  <= 5,814767 %` und `> 5,814767 %`; im spaeteren 365-Tage-Block blieb der
  Ein-Trade-Close-Benchmark mit 2,510 / 3,574 / 4,219 USDC pro Tag geordnet.
- Im hohen Volatilitaetsregime erreichten 56,7 Prozent der spaeteren Tage im
  perfekten Ein-Trade-Benchmark mindestens 3 USDC. Dieselbe Volatilitaet
  prognostizierte jedoch keine profitable Long-Richtung; rohe Open-to-Close-
  Longs blieben in allen drei Regimen nach Kosten negativ.

| kausales 20-Tage-Range-Regime | Ein-Trade-Close-Benchmark Development | spaetere 365 Tage |
|---|---:|---:|
| niedrig | 2,459 USDC/Tag | 2,510 USDC/Tag |
| mittel | 3,603 USDC/Tag | 3,574 USDC/Tag |
| hoch | 4,324 USDC/Tag | 4,219 USDC/Tag |

Diese geordnete Replikation ist der staerkste exploratorische Befund der
Diagnose. Sie zeigt interne Opportunity-Kapazitaet, beweist aber weder
Vorzeichen, Entry-Timing, Netto-Edge noch kuenftige Stabilitaet.

Volatilitaet ist damit ein **exploratorisch intern repliziertes
Kapazitaetssignal**, aber weder ein vorab bestaetigtes Opportunity-Gate noch ein
Entry. Die Hypothese ist bereits dateninformiert, wird ins Trial-Ledger
aufgenommen und muss nested sowie in neuer Forward-Evidenz bestehen.

### 4.5 Zusaetzlicher kausaler Modell-Challenger

Als Falsifikation wurde ein kleiner linearer Ridge-Challenger mit ausschliesslich
vergangenen ETHUSDC-, BTCUSDC- und ETHBTC-Informationen untersucht:

- 1h/4h/12h/24h/72h/168h Returns;
- realisierte Volatilitaet;
- Range und Volumen;
- UTC-Zeit;
- sechs expanding Walk-forward-Folds innerhalb der ersten 730 Tage;
- Auswahl von Horizont, Regularisierung und Signalquantil nur aus diesen Folds;
- danach genau eine Auswertung auf den letzten 365 Tagen.

Der beste innere Kandidat hatte vier von sechs positiven Folds, aber einen
schlechtesten Fold von -0,625 USDC/Tag und bereits negative Gesamt-PnL. Im
spaeteren 365-Tage-Block erzielte er:

| Kennzahl | Ergebnis |
|---|---:|
| Netto USDC/Tag | -0,1687 |
| Trades | 105 |
| Profit Factor | 0,5305 |
| Maximaler sequenzieller Drawdown | 64,53 USDC |

Das ist kein Kandidat fuer den Bot. Es zeigt, dass mehr Merkmale oder ein Modell
allein keinen Edge erzeugen und dass Median-Fold-Ranking ohne strenge Worst-Fold-
und Gesamtgates gefaehrlich ist.

### 4.6 Vergleich mit dem vorhandenen Research

Der juengste abgeschlossene Protocol-v2-Lauf
`research_loop_supervisor_20260713T172938Z` stoppte regulaer nach 7 von maximal
8 Zyklen wegen `selection_stagnation_3_cycles`. Er erzeugte 280 Profile,
testete 84, fuehrte 21 in Walk-forward und bewertete 14 Finalisten. Kontext war
aktiv; Audit und finaler Holdout blieben geschlossen. Sein bester
Validation-Kandidat `cooldown_fee_aware_06_011` meldete +0,028867 USDC/Tag,
PF 1,316 und nur 16 Trades. Das liegt rund Faktor 104 unter dem Ziel und reicht
wegen der kleinen Stichprobe nicht als Beweis. Der Lauf erzeugte keine Orders
und liess Live, Paper und Testtrade gesperrt.

## 5. Welche Handelsarchitektur als Naechstes falsifiziert werden sollte

Die Daten rechtfertigen keine einzelne feste Regel. Sie motivieren als naechste
zu falsifizierende, begrenzte Challenger-Hypothese eine regimeabhaengige Auswahl mit
lokalen Spezialisten und einem dominanten `NO_TRADE`-Zustand. Das ist die aus
der Diagnose am besten begruendete **zu pruefende Architektur**, noch keine
bewiesene Handelsmethode.

### 5.1 Zielstruktur des Routers

```text
abgeschlossene Marktdaten
        |
        v
Opportunity/Regime-Erkennung
        |
        +--> kein belegter Edge --------------------------> NO_TRADE
        |
        +--> Trend + kontrollierter Ruecksetzer ----------> Pullback/Reclaim
        |
        +--> Kompression + bestaetigter Ausbruch/Retest --> Breakout-Spezialist
        |
        +--> stabile Range + niedrige Effizienz ----------> Mean-Reversion
        |
        +--> Stress/Crash/uneinheitlicher Kontext --------> NO_TRADE
```

Der Router darf nur eine Strategie freigeben, deren lokaler Edge in genau
diesem Regime innerhalb der Entwicklung nachgewiesen wurde. Er darf keine
Position aus BTCUSDC oder ETHBTC erzeugen. Die nachgewiesene Volatilitaets-
Kapazitaet darf dabei nur entscheiden, **ob genug Bewegung plausibel ist**;
Richtung und Entry brauchen separat bestaetigte, kausale Evidenz.

### 5.2 Verbindliche abgeschlossene Zeitebenen

- 1m: konservative Ausfuehrung, Stop-/TP-Reihenfolge, Slippage;
- 5m/15m/30m: Entry-Struktur und Reclaim/Retest;
- 1h/4h: Opportunity, Volatilitaet, Kompression, lokaler Trend;
- 1d: uebergeordneter Trend und Risikoregime;
- 1 Woche/Monat: nur Kontext aus vollstaendig abgeschlossenen Perioden.

Ein Signal auf Bar-Schluss darf fruehestens auf dem naechsten handelbaren Preis
ausgefuehrt werden. Unfertige 4h-, Tages-, Wochen- oder Monatsbalken sind fuer
das Signal verboten.

### 5.3 Feature-Gruppen

Alle Schwellen, Quantile und Normalisierungen werden je Fold nur auf dessen
Trainingsdaten gelernt.

1. **Opportunity-Kapazitaet**
   - realisierte Volatilitaetsquantile;
   - ATR und erwartete Range;
   - Range-Kompression/Expansion;
   - vergangene MFE/MAE-Verteilung, niemals zukuenftige MFE als Feature.

2. **Trend und Effizienz**
   - 1h/4h/1d Returns;
   - Kaufman-aehnliche Trend-Effizienz;
   - Steigung und Distanz zu robusten Trendankern;
   - Pullback-Tiefe in ATR-Einheiten.

3. **Entry-Bestaetigung**
   - 15m-Reclaim eines abgeschlossenen Levels;
   - Breakout mit Retest statt Kauf des ersten Impulses;
   - Volumen relativ zum ausschliesslich vergangenen Sessionprofil;
   - Abstand bis Stop und erwartetes Netto-Potenzial nach Kosten.

4. **Kontext-Veto**
   - BTCUSDC Trend, Stress und Volatilitaet;
   - ETHBTC relative Staerke/Schwaeche;
   - gemeinsame Zeitstempel und nur abgeschlossene Kontextbalken;
   - Kontext bestaetigt oder blockiert, handelt aber nie selbst.

5. **Kosten und Handelbarkeit**
   - erwartete Bewegung deutlich groesser als Basiskosten;
   - Tick Size, Step Size, Mindestnotional und Mengenrundung;
   - Spread-/Slippage-Basis und Stress;
   - Liquiditaets- und Nullvolumen-Veto.

### 5.4 Zu pruefende lokale Spezialisten

Die Reihenfolge ist bewusst. Jeder Spezialist wird als kleine, vorab begrenzte
Kandidatenfamilie eingefuehrt und muss den kompletten Monatsprozess verbessern.

1. `trend_pullback_reclaim`
   - positiver 4h-/Tagestrend;
   - kontrollierter Pullback statt Impulsjagd;
   - 15m-Reclaim;
   - BTC-/ETHBTC-Veto;
   - ATR-Stop, Zeitstop und konservativer Trail.

2. `compression_breakout_retest`
   - vorherige Volatilitaetskompression;
   - abgeschlossener Ausbruch;
   - Einstieg erst nach gehaltenem Retest;
   - erwartete Restbewegung muss Kosten und Stopdistanz tragen.

3. `range_reversion_confirmed`
   - niedrige Trend-Effizienz und stabiles Range-Regime;
   - Kauf erst nach Rueckkehr in die Range, nicht waehrend des fallenden Impulses;
   - enges Zeitlimit und kein Einsatz im Hochvolatilitaets-Abverkauf.

4. `multiday_swing_trend`
   - mehrtaegiger Trend, um die Kostenlast gegenueber Intraday-Frequenz zu senken;
   - Monatsgrenzen und Modellwechsel muessen offene Positionen explizit behandeln.

5. `no_trade`
   - Standard, wenn kein Spezialist seine lokale Untergrenze besteht.

Die heutigen Familien Momentum, Breakout, Pullback und Mean-Reversion sollen
zuerst als Spezialisten hinter dem Router wiederverwendet werden. Es wird keine
zweite Simulationsengine gebaut.

## 6. Der korrekte monatliche 730/365-Prozess

### 6.1 Warum ein jeden Monat betrachtetes Jahr nicht erneut blind ist

Nach dem ersten Oeffnen des letzten Jahres sind beim naechsten Monatslauf elf
von zwoelf Monaten bereits bekannt. Wiederholtes Anpassen an diesen Block
ueberfitten den Holdout selbst. Adaptive Holdout-Wiederverwendung ist ein
bekanntes methodisches Problem ([Dwork et al., 2015](https://papers.nips.cc/paper_files/paper/2015/hash/bad5f33780c42f2588878a9d07405083-Abstract.html)).

Deshalb gelten drei getrennte Begriffe:

- `monthly_process_oos`: historischer, rollierender Pseudo-Live-Nachweis;
- `sealed_final_holdout`: einmalige, unangetastete Pruefung einer neuen
  Protokollgeneration;
- `forward_shadow_month`: der nach der Entscheidung wirklich neu entstandene
  Monat.

Die vorhandenen drei Jahre wurden bereits analysiert. Sie koennen eine
retrospektive Pseudo-Live-Simulation liefern, sind aber nicht mehr ehrlich
unangetastet. Wirklich neue Evidenz entsteht ab jetzt Monat fuer Monat im
Shadow-Ledger.

Zusaetzlich verbieten der aktuelle `PROJECT_CONTRACT.md` und die heutige
`split.py`-Policy jede Selektion/Re-Optimierung auf dem verbrauchten Auditblock
`2025-07-08..2026-07-07`. Protocol v3 darf diesen Block deshalb **vor einer
versionierten Vertragsaenderung nur diagnostisch** in spaeteren Rolling-Trains
verwenden und weder einen Folgemonatskandidaten noch Research Shadow daraus
freigeben. Eine spaetere Vertragsaenderung darf Rohmarktbeobachtungen aus einem
frueheren Pseudo-OOS als kausale Historie zulassen, niemals aber dessen PnL,
Ranking, Report oder menschlich daraus abgeleitete Pipelineaenderung in einen
spaeteren Fit zurueckspielen. Der kanonische Final-Holdout bleibt davon
unberuehrt.

### 6.2 Aeussere Monats-Origins

Der Protocol-v3-Kalender wird vor dem Lauf vollstaendig eingefroren:

```text
timezone                       = UTC
deployment_anchor_day_utc      = 8
research_activation_delay      = 24 Stunden keine neuen Entries
target_anchor                  = T
as_of_day                      = UTC-Kalendertag T-1
valid_from                     = T + 24 Stunden
valid_until                    = naechster Monatsanker nach T
manual_decision_deadline       = valid_from
entry_enabled_at               = max(valid_from, flat_time)
process_end_exclusive          = letzter Anker, dessen Vortag fuer alle
                                 drei Maerkte vollstaendig vorliegt
process_start_inclusive        = process_end_exclusive - 365 Tage
outer_test_boundaries          = process_start, jeder nachfolgende
                                 Monatsanker innerhalb des Fensters,
                                 process_end
train_j                        = [test_start_j - 730 Tage, test_start_j)
test_j                         = [test_start_j, test_end_j)
```

Formal seien die sortierten Grenzen `b0=process_start < b1 < ... <
b12=process_end`. Fuer Origin `j=1..12` gilt ohne Ausnahme:

```text
T_j = test_start_j = b_(j-1)
test_end_j = b_j
as_of_day_j = UTC-Kalendertag unmittelbar vor T_j
valid_from_j = T_j + 24 Stunden
valid_until_j = b_j
```

Insbesondere gilt `T_1=test_start_1=b0=process_start` und
`valid_from_1=b0+24h`.

Damit ist bei einem Leap-Fenster auch das synthetische `b0` der eindeutige
erste Entscheidungszeitpunkt; genau dessen erste 24 Stunden sind entry-
gesperrt. `b1..b12` bleiben echte Monatsanker. Die Boundary-Fixtures pruefen
`T_1`, `valid_from_1`, alle zwoelf Intervalle und die 365-Tage-Vereinigung.

Der Tag `8` passt zum aktuellen Datenschnitt bis einschliesslich `2026-07-07`.
Er wird nicht nach Ergebnissen verschoben. In kuerzeren Monaten wuerde ein
hoeherer konfigurierter Ankertag auf den letzten gueltigen Kalendertag geklemmt.
`process_start` ist eine bewusst synthetische erste Grenze: In einem
Schaltjahr kann sie vom Tag 8 abweichen; nur die danach liegenden inneren
Grenzen sind Monatsanker. Das erste Deployment-Intervall ist dann entsprechend
kuerzer oder laenger. Die Vereinigungsmenge bleibt verbindlich **exakt 365
vollstaendige UTC-Tage**, ohne Luecke oder Doppelung, und muss trotzdem genau
zwoelf Deployment-Intervalle liefern. Boundary-Fixtures muessen mindestens
Enden am `2024-03-08`, `2025-03-08` und `2026-07-08` abdecken.

Der 24-Stunden-Delay bildet die reale Rechenzeit fail-closed ab: Am Anker wird
der Snapshot eingefroren und die neue Konfiguration darf am ersten Tag des
Testintervalls keinen Entry erzeugen. Ohne uebertragene Altposition ist das ein
No-Trade-Tag; eine Altposition bleibt ausschliesslich exit-only. Ist der Lauf
bis dahin nicht erfolgreich und reproduzierbar abgeschlossen, bleibt die neue
Konfiguration fuer dieses Intervall `NO_TRADE`. `valid_from` bleibt auch bei
frueherem Abschluss **exakt** `T+24h`; der Kandidat wartet. Ein Buttondruck
nach `T+24h` darf nicht zurueckdatieren und zielt ausschliesslich auf den
naechsten Monatsanker. Eine andere Latenzregel waere eine neue
Pipelinegeneration.

Bezeichne die 1.095 Fit-/Prozess-Tage chronologisch mit `D1 ... D1095`.
`D731 ... D1095` bilden das obige Prozessfenster. Es entstehen genau zwoelf
aufeinanderfolgende Testintervalle. Jeder der 365 Tage darf genau einmal
Prozess-OOS sein. Wenn die Boundary-Funktion nicht genau zwoelf Intervalle
erzeugt, blockiert der Lauf statt eine Grenze still zu veraendern.

Die Rohdatenpflicht ist groesser als 1.095 Tage:

```text
warmup_duration = max(alle ETH-/BTC-/ETHBTC-Feature- und Kontextlookbacks)
                  + 1 kleinste Quellbar
required_raw_interval = [D1 - warmup_duration, process_end_exclusive)
```

Fehlt dieser Vorlauf in nur einem Markt, blockiert Protocol v3. Die heute exakt
1.095 Tage reichen daher fuer den neuen Multi-Timeframe-Router noch nicht aus.

Fuer jede Origin `j`:

1. `test_start_j` bestimmen;
2. exakt die 730 Tage unmittelbar davor als Entwicklung laden; Rohdaten aus
   einem frueheren Outer-Test duerfen spaeter als normale historische
   Trainingsdaten erscheinen, aber **nie** dessen PnL, Ranking oder menschliche
   Ergebnisinterpretation;
3. alle Daten-, Feature-, Regime- und Labelgrenzen an dieser Origin neu fitten;
4. die komplette innere Auswahlpipeline ausfuehren;
5. genau einen Kandidaten oder `NO_TRADE` einfrieren;
6. neue Entries ausschliesslich innerhalb `test_j` und erst ab
   `entry_enabled_at` zulassen. Eine Altposition darf exit-only in `test_j`
   hineinreichen; PnL wird dem realen UTC-Tag und der Ursprungskonfiguration
   eindeutig zugeordnet;
7. Ergebnis versiegelt speichern und der Kandidatensuche nicht zurueckgeben;
8. zur naechsten Origin um einen Monat weiterschieben.

Vereinfacht in Monatsnotation entspricht das:

```text
Origin 01: Monate 01-24 entwickeln -> Monat 25 handeln
Origin 02: Monate 02-25 entwickeln -> Monat 26 handeln
...
Origin 12: Monate 12-35 entwickeln -> Monat 36 handeln
Danach:   neueste 730 Tage -> Kandidat fuer das naechste Ankerintervall
```

Die Monatsnotation ist nur anschaulich. Verbindlich sind die obigen exakten
UTC-Tagesintervalle, nicht die ungenaue Gleichsetzung `24 Monate = 730 Tage`.

Es wird damit nicht nur ein Kandidat getestet. Es wird geprueft, welche
Entscheidung dieselbe festgelegte Research-Pipeline an jedem historischen
Monatsende tatsaechlich getroffen haette. Rolling-Origin-Evaluation ist fuer
nichtstationaere Zeitreihen geeigneter als zufaellige Splits ([Tashman, 2000](https://doi.org/10.1016/S0169-2070(00)00065-0)).

### 6.3 Innere Auswahl je Origin

Innerhalb der jeweiligen 730 Tage:

1. Kandidatenfamilien und Parameterraum aus der eingefrorenen Pipeline laden.
2. Einen **neuen deterministischen Inner-Fold-Planer** verwenden; die heutige
   Fold-Funktion wird nicht unveraendert wiederverwendet.
3. Sechs streng chronologische, nicht ueberlappende 60-Tage-Validation-Folds
   auf den letzten 360 Entwicklungstagen bilden. Fuer Fold `k = 0..5` gilt:

   ```text
   validation_start_k = training_end - (6-k) * 60 Tage
   validation_end_k   = training_end - (5-k) * 60 Tage
   fit_start_k        = training_start
   fit_end_k          = validation_start_k - purge_duration
   ```

   Der erste Fit besitzt damit vor Purging 370 Tage; jeder folgende waechst um
   60 Tage. Diese Festlegung erfuellt weiterhin `required_wfv_folds=6` und
   `min_wfv_fold_days=60` der bestehenden Quality Gates.
4. Vor jeder Foldgrenze ueberlappende Labels/Trades purgen.
5. Scaler, Quantile, Regimegrenzen und Feature-Auswahl nur auf dem jeweiligen
   Fold-Training fitten.
6. Zuerst alle Development-Gates anwenden. Bestehen mehrere Kandidaten, gilt
   exakt die folgende lexikographische Reihenfolge, jeweils absteigend ausser
   dem abschliessenden kanonischen ID-Tiebreaker:

   ```text
   (worst_fold_net_usdc_per_day,
    median_fold_net_usdc_per_day,
    aggregate_wfv_net_usdc_per_day,
    joint_stress_net_usdc_per_day,
    -max_drawdown_usdc,
    -friction_share,
    -free_parameter_count,
    canonical_candidate_id aufsteigend)
   ```

   Das 3-USDC-Ziel ist kein Bestandteil dieses Schluessels.
7. Parameter-Nachbarschaft und Kostenstress pruefen.
8. Besteht kein Kandidat alle Development-Gates, `NO_TRADE` waehlen; andernfalls
   genau den deterministischen Gewinner auf allen innerhalb der 730 Tage
   boundary-zulaessigen Events refitten. Labels, deren Ergebnis
   `training_end` erreicht oder ueberschreitet, bleiben ausgeschlossen.
9. Parameter, Router und Exitlogik fuer den naechsten aeusseren Monat einfrieren.

Nested Validation trennt Parameterwahl von Performance-Schaetzung und reduziert
Selektionsbias ([Varma und Simon, 2006](https://brb.nci.nih.gov/techreport/Varma-Simon-CrossValid.pdf)).

### 6.4 Purging und zeitliche Paritaet

Jedes Signal besitzt ein Informationsintervall vom Signalzeitpunkt bis zum
spaetestmoeglichen Label-, Stop-, TP- oder Time-stop-Ende. Es gilt vorab:

```text
purge_duration = max(max_label_horizon,
                     max_holding_period + pending_entry_latency)
                 + 1 Ausfuehrungsbar
```

Trainingsevents, deren Informationsintervall eine Validation-/Testgrenze
beruehrt, werden entfernt. `max_holding_period` gehoert zum eingefrorenen
Suchvertrag; eine nachtraegliche Verlaengerung ist eine neue Pipelinegeneration.

Feature-Warmup darf Daten **vor** `training_start` lesen, aber ausschliesslich
zur kausalen Berechnung bereits festgelegter Lookbacks. Warmup-Daten duerfen
nicht in Scaler, Quantile, Regimefit, Labels oder PnL eingehen. Fehlender Warmup
blockiert den Kandidaten.

Pflichten:

- Signalbar abgeschlossen;
- Ausfuehrung fruehestens naechster handelbarer Preis;
- Kontext zum gleichen oder frueheren Informationsstand;
- keine Normalisierung mit zukuenftigen Daten;
- kein guenstiger kuenstlicher Monatsend-Fill;
- jeder innere Fold startet `flat`, ohne Pending-Order, Cooldown oder
  uebernommenen Modellzustand, und schliesst eine Restposition am Fold-Ende zum
  konservativen handelbaren Preis inklusive Kosten;
- nur die erste aeussere Origin startet `flat`. Zwischen aeusseren Origins
  wird ausschliesslich eine noch offene Position samt ihrer alten Exitlogik
  weitergetragen; Pending Entries, Cooldowns, Scaler oder Modellzustand werden
  nicht uebernommen;
- ab der Monatsgrenze darf die alte Konfiguration keinen neuen Entry erzeugen.
  Sie verwaltet nur ihre offene Position bis zum regulaeren Exit; die neue
  Konfiguration wartet bis `flat`. Taeglicher MTM-PnL bleibt dem realen
  Kalendertag zugeordnet;
- nur am Ende des gesamten 365-Tage-Prozesses wird eine Restposition fuer den
  endlichen Report konservativ liquidiert und separat als
  `terminal_liquidation=true` ausgewiesen.

Der versionierte Rotation-State muss mindestens enthalten:

```text
retiring_candidate_bundle_hash
open_quantity, entry_price, accrued_fees
stop_price, target_price, trailing_state, high_watermark, time_stop_state
new_candidate_bundle_hash
anchor, valid_from, valid_until, flat_time, entry_enabled_at
```

Der kandidatengleiche Hindsight-Solver muss exakt dieselbe Exit-only-Handoff-
und terminale Liquidationslogik verwenden. Bewertungsobjekt ist die verkettete
monatliche Policy, nicht ein isolierter Kandidat mit kuenstlichem Flat-Start an
jeder Outer-Grenze.

### 6.5 Ergebnisse bleiben bis zum Ende versiegelt

Die UI darf waehrend der zwoelf Origins zeigen:

- Fortschritt und technische Phase;
- Origin/Fold/Kandidatencount;
- Daten- und Safety-Status;
- keine einzelnen Outer-PnL-Werte, Rankings oder Strategiewechsel.

Erst nach Abschluss aller zwoelf Origins wird der verkettete Prozess-OOS
geoeffnet. Sonst wuerde der Mensch die spaeteren Origins indirekt an fruehere
Ergebnisse anpassen.

## 7. Multiple-Testing-Schutz

### 7.1 Permanentes Trial-Ledger vor der naechsten Suche

Jeder Kandidat, der irgendeinen datenabhaengigen Wert, Filter, Score oder Rang
erhaelt, wird permanent gezaehlt:

- Kandidaten und Parameterkombinationen;
- Strategie-/Featurevarianten;
- Seeds;
- Ranking-/Gate-Aenderungen;
- manuelle Patches nach Ergebnisbetrachtung.

Nur rein theoretische, vor jedem Datenzugriff ausgefuehrte Syntax-, Typ- und
Parameterbereichsfilter duerfen einen Kandidaten ohne Trial-Eintrag verwerfen.
Der Zaehler wird weder pro Zyklus, Outer-Origin, Monat noch
Pipelinegeneration zurueckgesetzt. Fuer bereits ausgefuehrte historische
Versuche wird der rekonstruierbare Stand importiert und verpflichtend mit
`historical_trial_count_is_lower_bound=true` gekennzeichnet. White zeigt,
warum wiederholte Modellsuche auf derselben Historie zufaellige Gewinner
erzeugen kann ([White, 2000](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00152)).

Eine Trial-Untergrenze ist **keine** konservative Eingabe fuer DSR: unbekannte
ausgelassene Versuche koennen den DSR nur zu gut erscheinen lassen. Solange
`historical_trial_count_is_lower_bound=true` oder zu einem Trial seine kausale
Tagesreihe fehlt, gilt `development_dsr=INSUFFICIENT_TRIAL_HISTORY`. Dann darf
keine Origin einen Trading-Kandidaten freigeben; `NO_TRADE` bleibt die einzige
valide Entscheidung. Erst eine vollstaendig inventarisierte Trial-Historie kann
das harte DSR-Gate aktivieren.

Eine Pipelinegeneration umfasst Featuredefinitionen, Familien, Suchraum,
Ranking, Gates, Kostenmodell und Boundary-Regeln. Monatliche Re-Fits derselben
eingefrorenen Pipeline gehoeren zur selben Generation. Jede inhaltliche
Aenderung erzeugt eine neue Generation; der permanente Trial-Zaehler bleibt
trotzdem erhalten und die Forward-Evidenz der neuen Generation beginnt bei
null.

### 7.2 Vorab begrenztes Rechen- und Suchbudget

Protocol v3 darf nicht unbegrenzt weiterprobieren:

| Ebene | harte Obergrenze |
|---|---:|
| Outer-Origins | 12 |
| Inner-Cycles je Origin | 8 |
| je Cycle erzeugt / getestet / Full-WFV-Promotion / Finalisten | 40 / 12 / 3 / 2 |
| zusaetzlicher aktueller 730-Tage-Refit | 1 gleicher Inner-Lauf |
| maximal erzeugte Profile gesamt | 4.160 |
| maximal datengetestete Profile gesamt | 1.248 |
| kausale 360-Tage-PBO/WFV-Basisreihen | 1.248 |
| maximal in volle WFV-Robustheit promovierte Profile | 312 |
| maximal Finalisten-Auswertungen gesamt | 208 |

`selection_stagnation_3_cycles` darf einen Inner-Lauf frueher beenden. Ein
Cache darf eine bitidentische Kombination aus Daten-, Kontext-, Feature-,
Kandidaten-, Fold-, Boundary-, Execution-, Simulator- und Kostenhash
wiederverwenden; der Ledger protokolliert dann
die Cache-Wiederverwendung und darf sie nicht als neuen unabhaengigen Test
ausgeben. Budget oder Stopregel werden nie aus einem sichtbaren Outer-Ergebnis
heraus erweitert.

Damit aendert sich die interne Bedeutung der Stufen, nicht die sichtbare
40/12/3/2-Promotion: Alle 12 getesteten Profile eines Cycles erhalten eine
kompakte, vergleichbare 6-x-60-Tage-OOS-Basisreihe fuer die vollstaendige
PBO-Matrix. Nur drei werden danach in die teureren Stress-, Regime-,
Nachbarschafts- und Finalistenpruefungen promoviert. Ohne Budget fuer alle 12
Basisreihen ist PBO nur shortlist-bedingt und darf **kein** Full-Pipeline-Gate
sein.

### 7.3 Entwicklungsdiagnostik, nicht Outer-Tuning

Neue Pflichtdiagnostik innerhalb der Entwicklung:

| Gate | Vorabwert |
|---|---:|
| `development_dsr` | mindestens 0,95 |
| `development_pbo` | hoechstens 0,10 |
| CSCV-Partitionen fuer PBO | `S=12` zusammenhaengende Tagesbloecke |
| Kandidatenmatrix | taeglicher Netto-MTM-PnL jedes der 12 getesteten Profile je Cycle |
| Challenger-Vergleich | White Reality Check oder Hansen SPA, retrospektiv |

Der Deflated Sharpe korrigiert Selektionsbias, Anzahl der Versuche und
nichtnormale Renditen ([Bailey und Lopez de Prado](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)). PBO misst die Wahrscheinlichkeit, dass der In-Sample-
Gewinner ausserhalb der Auswahl schlechter rangiert ([Bailey et al.](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)). Fuer mehrere Challenger ist Hansen SPA eine robustere Ergaenzung zum einfachen Gewinnervergleich ([Hansen, 2005](https://doi.org/10.1198/073500105000000063)).

PBO wird je 730-Tage-Origin ausschliesslich aus der kausal erzeugten inneren
WFV-Development-Matrix **aller getesteten Profile dieser Origin** berechnet.
Jede Spalte besitzt dieselben 360 verketteten Validation-Tage einschliesslich
Nulltagen; Full-fit-In-Sample-PnL ist verboten. Die exakte CSCV-Regel lautet:

```text
S = 12 zusammenhaengende Bloecke zu exakt 30 Tagen
Splits = C(12, 6) = 924
IS-Metrik = mittlerer taeglicher Netto-MTM-PnL der sechs IS-Bloecke
IS-Tie = canonical_candidate_id aufsteigend
OOS-Rang r = Durchschnittsrang nach OOS-Mittel, 1=schlechtester, M=bester
omega = (r - 0.5) / M
lambda = ln(omega / (1 - omega))
development_pbo = Anzahl(lambda <= 0) / 924
```

Cash/`NO_TRADE` mit Nullreihe ist die feste Baseline. Weniger als zwei
Tradingprofile, nichtfinite Werte oder nicht exakt gemeinsame 360 Tage ergeben
`PBO=INSUFFICIENT_EVIDENCE`. Ein Trading-Kandidat muss Cash schlagen; Cash
selbst braucht kein DSR/PBO-Gate.

DSR wird fuer den ausgewaehlten Trading-Kandidaten aus derselben 360-Tage-OOS-
Reihe berechnet. Der Implementierungsvertrag ist:

```text
n = 360; r = taeglicher Netto-MTM-PnL einschliesslich Nulltagen
SR = mean(r) / sample_std(r)
K = floor(4 * (n / 100)^(2/9))
VIF = max(1, 1 + 2 * sum[k=1..K]((1-k/(K+1))*rho_k))
n_eff = n / VIF
N_raw = vollstaendiger permanenter Trial-Count
C = Korrelationsmatrix der gemeinsamen kausalen Kandidatenreihen
N_eff_trials = (trace(C)^2) / trace(C @ C)     # nur Diagnose
sigma_SR = sample_std aller kausalen Trial-SRs
SR0 = sigma_SR * ((1-gamma)*Phi^-1(1-1/N_raw)
                  + gamma*Phi^-1(1-1/(N_raw*e)))
z = (SR-SR0)*sqrt(n_eff-1)
    / sqrt(1-skew(r)*SR+((kurtosis(r)-1)/4)*SR^2)
development_dsr = Phi(z)
```

`gamma` ist die Euler-Mascheroni-Konstante, `kurtosis` die Pearson-Kurtosis und
`rho_k` die Stichprobenautokorrelation. Das Gate nutzt absichtlich `N_raw`,
nicht den kleineren diagnostischen `N_eff_trials`. Nullvarianz, Nenner <= 0,
`N_raw<2`, unvollstaendige Trial-Historie oder fehlende gemeinsame Reihen
ergeben `DSR=INSUFFICIENT_EVIDENCE`.

Jeder Kandidat in der PBO-Matrix braucht dieselbe vollstaendige taegliche
Development-Reihe. Ein nur per billiger Vorstufe gescortes Profil bleibt zwar
im permanenten Trial-Zaehler, darf aber weder in PBO fehlen und anschliessend
gewinnen noch ohne vollstaendige Matrix zum Finalisten werden.

Das Outer-Ledger enthaelt dagegen nur die taegliche Netto-MTM-Reihe der damals
eingefrorenen Auswahl. PBO/DSR werden niemals aus den zwoelf Outer-Ergebnissen
nachoptimiert oder als neue Auswahlvariable zurueckgespielt. Reality Check/SPA
auf bereits mehrfach verwendeter Historie ist nur eine retrospektive
Warnleuchte, kein Ersatz fuer neue Forward-Daten.

## 8. Execution- und Kostenmodell

Der Backtest muss dieselbe Entscheidung spaeter im Shadow reproduzieren.

### 8.1 Basisfill

- Entry auf dem naechsten handelbaren Preis nach Signal;
- Entry-Slippage `+5 bps`, Exit-Slippage `-5 bps`;
- 10 bps Gebuehr auf den tatsaechlich ausgefuehrten Notional je Seite;
- Kaufmenge auf die zulaessige Step Size abrunden, sodass das ausgefuehrte
  Entry-Notional 100 USDC nicht ueberschreitet; Fees werden zusaetzlich
  verbucht;
- angeforderte/reservierte 100 USDC und tatsaechlich ausgefuehrtes Notional
  getrennt im Trade- und Aggregatreport speichern;
- Verkauf auf dieselbe gerundete Menge;
- PRICE_FILTER, LOT_SIZE/MARKET_LOT_SIZE und MIN_NOTIONAL/NOTIONAL aus einem
  versionierten Exchange-Info-Snapshot.

Binance definiert Preis-, Mengen- und Notionalfilter in der offiziellen
[Spot-Filter-Dokumentation](https://developers.binance.com/en/docs/products/spot/filters).
Tatsaechliche Provisionen koennen nach Maker/Taker, Konto, VIP-Stufe und Rabatt
abweichen ([offizielle Commission-FAQ](https://developers.binance.com/en/docs/products/spot/faqs/commission_faq)); der Basis-Research bleibt trotzdem
konservativ und reproduzierbar auf 10 bps je Seite fixiert.

### 8.2 Intrabar-Regeln

- Stops/TPs aus hoeheren Signalzeitebenen werden immer mit den vorhandenen
  1m-Kerzen aufgeloest.
- Werden Stop und TP innerhalb derselben 1m-Kerze beruehrt, gilt fuer den Long
  ausnahmslos die pessimistische Reihenfolge: Stop vor TP.
- Gaps fuellen zum schlechteren naechsten handelbaren Preis.
- Keine perfekten High-/Low-Fills.
- Der orderfreie Shadow erzeugt keine echten oder partiellen Fills. Spread-,
  BookTicker- oder Orderbuchdaten duerfen nur versionierte **virtuelle** Fill-
  und Slippage-Proxys liefern; tatsaechliche Fill-Evidenz waere erst in einer
  separat beauftragten spaeteren Testtrade-/Live-Phase moeglich.

### 8.3 Stresslaeufe

Jeder Finalist erhaelt mindestens:

1. Basis: 10 bps Fee + 5 bps Slippage je Seite;
2. Slippagestress: 10 + 15 bps je Seite;
3. Joint Stress: 15 + 10 bps je Seite;
4. spaeter orderfrei: Median und p90 versionierter virtueller Slippage-Proxys
   aus oeffentlichen Marktdaten; niemals als echte Fills bezeichnen.

## 9. Bewertung des 365-Tage-Monatsprozesses

Alle zwoelf Deployment-Intervall-Ledger werden chronologisch verkettet.
No-Trade-Tage tragen exakt null bei. Deployment-Intervalle sind nicht mit
UTC-Kalendermonaten identisch: Das aktuelle Fenster
`2025-07-08..2026-07-08(exklusiv)` besitzt zwoelf Deployment-Intervalle, aber
beruehrt 13 benannte Kalendermonate und fuenf Kalenderquartale. Beide
Periodensysteme werden getrennt reportet und gegatet.

Zielertrag, Drawdown, Underwater und Deployment-PnL entstehen aus dem
taeglichen MTM-Ledger. Geschlossene Trade-PnL, PF, Winrate und Tradezaehlung
werden eindeutig dem UTC-Exit-Zeitpunkt zugeordnet; Fees und Slippage dem
tatsaechlichen Ausfuehrungstag. Eine grenzueberschreitende Position darf dadurch
nicht doppelt in MTM- und Closed-Trade-Gesamt-PnL eingehen.

### 9.1 Pflichtmetriken

- Gesamt-Netto-USDC und Netto-USDC pro Kalendertag;
- Profit Factor, Winrate und Tradezahl;
- Fees, Slippage und Friction Share;
- Mark-to-Market-Drawdown und Underwater-Dauer;
- positive/aktive Deployment-Intervalle, UTC-Kalendermonate und Quartale;
- schlechtestes Deployment-Intervall, schlechtester Kalendermonat und Fold;
- laengste No-Trade-Luecke;
- Top-1-/Top-5-Trade- und Top-Monat-Konzentration;
- Ergebnis je Marktregime und je Spezialist;
- Kandidaten-/Familienwechsel je Origin;
- Flat- und ETH-Buy-and-hold-Benchmark;
- Ein-Trade-Close- und kandidatengleicher Hindsight-Benchmark;
- Development-DSR/PBO getrennt vom Outer-Block-Bootstrap;
- Abstand zum Ziel von 3 USDC/Tag.

### 9.2 Fail-closed Prozess-Gates

Die vorhandenen `quality_gate_v1`-Grenzen werden nicht rueckwirkend veraendert
oder durch weichere Monatsgrenzen ersetzt. Normativ bleibt der unveraenderte
Evaluator in `src/ethusdc_bot/backtest/quality_gates.py`; die folgende Tabelle
ist nur eine lesbare Kurzfassung und niemals eine Ersatzimplementierung.

`monthly_quality_gate_v1` ist eine **neue, vorab eingefrorene Gate-Version**.
Sie uebertraegt oder verschaerft die anwendbaren bestehenden Schwellen fuer den
historischen Outer-Prozess und ergaenzt Multiple-Testing-/Boundary-Pruefungen.
Sie kann niemals `final.single_sealed_evaluation` erfuellen oder dem
Prozess-OOS einen kanonischen Finalstatus geben:

| Bereich | unveraenderliche Mindestanforderung |
|---|---|
| innere Validation | >= 50 Trades, PF >= 1,10, MTM-Drawdown <= 15 USDC |
| innere WFV | 6 Folds zu >= 60 Tagen, >= 30 Trades/Fold, >= 180 gesamt, PF >= 1,20 |
| WFV-Stabilitaet | >= 5 positive Folds, >= 5 Folds mit PF >= 1,05, Worst PF >= 0,90 und Worst Netto/Tag >= -0,10 |
| WFV-Retention | Fold-Netto-CV <= 1,00, WFV/Training-Retention >= 60 %, MTM-Drawdown <= 15 USDC |
| Outer-Prozess | >= 120 Trades, PF >= 1,25, Average Trade > 0, MTM-Drawdown <= 15 USDC, Underwater <= 60 Tage, Gesamt-Netto positiv |
| Deployment-Intervalle | exakt 12, >= 9 positiv, >= 10 aktiv, schlechtestes >= -5 USDC, Top-Intervall <= 25 % |
| UTC-Kalendermonate | alle beruehrten Monate reporten; >= 75 % positiv, >= 83,33 % aktiv, Worst Month >= -5 USDC, No-Trade-Gap <= 30 Tage |
| UTC-Kalenderquartale | mindestens 4 und alle beobachteten positiv; mindestens 20 Exit-Trades in jedem beobachteten Quartal |
| Konzentration | Top-1-Trade <= 10 %, Top-5-Trades <= 35 %, Netto ohne Top 5 positiv und PF ohne Top 5 >= 1,05 |
| Joint Stress | netto positiv, PF >= 1,10, >= 50 % Netto-Retention, MTM-Drawdown <= 20 USDC |
| Slippage-Stress | netto positiv und PF >= 1,05; Friction Share <= 40 % |
| Parameter-Nachbarn | >= 80 % bestehen, Median-Netto-Retention >= 75 %, schlechtester Nachbar >= -0,10 USDC/Tag |
| Regime | 4 vorab definierte Regime, >= 20 Trades/Regime, >= 3 positiv und >= 3 mit PF >= 1,05, Worst PF >= 0,90, Worst Netto >= -5 USDC, max. PnL-Anteil 60 % |
| neue Development-Gates | Nur fuer freigegebenen Trading-Kandidaten DSR >= 0,95 und PBO <= 0,10; unzureichende Evidenz waehlt `NO_TRADE` |
| Integritaet | kein Safety-, Leakage-, Daten-, Fingerprint-, Boundary- oder Paritaetsfehler |

Zusaetzlich bleiben alle im normativen Evaluator enthaltenen Details wirksam:

- Gate-Version eingefroren, `selection_uses_audit=false` und exakt eine
  versiegelte Auswertung nur im separaten kanonischen Finalpfad;
- positive Full-Training-, Validation- und WFV-Nettoergebnisse sowie ueberall
  `drawdown_method=mark_to_market`;
- `max_underwater_days<=60`, Netto ohne Top 5 positiv und positiver
  durchschnittlicher Finaltrade;
- alle numerischen Parameter mit `+/-10 %`, mindestens zwei Nachbarn je
  Parameter, Session-Stunden-Schritt exakt 1 und alle bestehenden
  Nachbarschaftsgates;
- exakte Basis-/Stresskostenprofile, positives Baseline-Netto und saemtliche
  Stress-Retention-/Friction-Gates;
- Regimedefinition exakt `trend_sign_x_training_median_volatility`, Schwellen
  nur aus Training und Zuweisung ausschliesslich trailing.

Die Outer-Zeile mit 120 Trades, PF 1,25 und 15-USDC-Drawdown ist eine bewusst
konservative neue `monthly_quality_gate_v1`-Uebertragung der vorhandenen
Finalschwellen. Sie ist kein Final-Holdout-Nachweis und erzeugt keine
Adoption-Eignung.

Fehlende Evidenz besteht kein Trading-Gate. Eine korrekt fail-closed
`NO_TRADE`-Origin besteht die Origin-Integritaet ohne DSR/PBO vorzutaeuschen,
aber ein kompletter Prozess mit zu wenig Aktivitaet kann deshalb nicht Gruen
oder Gelb werden. Gruen verlangt zusaetzlich das Ziel; Gelb darf nur
als `robustness_passed_ex_target=true` bezeichnet werden, wenn alle
Robustheitsgates ausser dem expliziten Ziel-Gate bestanden sind.

### 9.3 Zwei getrennte Aussagen zum 3-USDC-Ziel

```text
historically_hit:
    beobachtetes Outer-Netto / 365 >= 3,00 USDC

statistically_supported:
    fresh_pre_registered_sealed_365 = true
    and sealed_bootstrap_target_supported = true
```

`historically_hit=true` bedeutet nur: Die Pipeline haette in dieser Historie
das Ziel erreicht. Auf dem bereits adaptiv analysierten Dreijahresblock muss
`statistically_supported=false` und `freshness=NOT_FRESH` bleiben, selbst wenn
ein Bootstrap-Intervall oberhalb 3 liegt. Bootstrap repariert weder
Holdout-Wiederverwendung noch Pipelineauswahl.

Der retrospektive Wert heisst deshalb `historical_bootstrap_lower_bound`. Erst
ein vor Beginn registriertes, bis zum Ende versiegeltes neues 365-Tage-Fenster
darf `sealed_bootstrap_target_supported` und damit den statistischen Status
setzen. Auch dann ist es eine Konfidenzaussage zum historischen Mittelwert,
keine Garantie der Pipeline-Generalisation.

Der Algorithmus verwendet die 365 taeglichen Netto-MTM-Werte einschliesslich
aller Nulltage und exakt 10.000 Replikationen. Der Seed entsteht als unsigned
64-bit Integer aus den ersten 16 Hexzeichen von `sha256(canonical_json(
pre_bootstrap_input_manifest))`. Das Manifest enthaelt PnL-Digest, Daten-,
Code-, Pipeline-, Gate- und Bootstrapkonfiguration, aber weder Bootstrapoutput
noch finalen Reporthash.

Fuer jede erwartete Blocklaenge `L in {5,10,20}` gilt der circular Stationary
Bootstrap: neuer Startindex gleichverteilt auf `0..364`; danach mit
Wahrscheinlichkeit `p=1/L` einen neuen gleichverteilten Start ziehen, sonst den
vorherigen Index modulo 365 um eins fortsetzen, bis 365 Werte vorliegen. Aus
jeder Replikation wird der Mittelwert berechnet; die einseitige 95-%-
Untergrenze ist ohne Interpolation der 500. Wert der aufsteigend sortierten
10.000 Mittelwerte (`ceil(0,05*10000)`). Das strenge Flag ist nur wahr, wenn
**alle drei** Untergrenzen mindestens 3 USDC/Tag sind.

Die Benchmark-Ratios werden verpflichtend, aber passend zur Kandidatenlogik
ausgewiesen:

```text
all_candle_one_trade_capture_ratio_diagnostic = process_oos_net_usdc_per_day
    / all_candle_one_trade_close_hindsight_usdc_per_day
candidate_matched_tradeable_capture_ratio = process_oos_net_usdc_per_day
    / candidate_matched_volume_filtered_hindsight_usdc_per_day
```

Die erste Ratio ist nur eine optimistische Diagnose und nur interpretierbar,
wenn der Kandidat maximal einen
Roundtrip pro Tag erlaubt; sonst kann sie legitim groesser als 1 werden. Die
zweite formale Ratio begrenzt den Hindsight-Solver auf positive-
Volumenzeitpunkte sowie dieselbe maximale Tradezahl, Haltedauer,
Long-only-/Ein-Lot-/Handoff-Zustandsmaschine, Rundung und Kosten. Ein
Ein-Trade-Kandidat in Richtung 0,80 bis 0,87 oder ein kandidatengleicher Wert
nahe 1 erfordert eine besondere Leakage-/Overfit-Sperre und manuelle Pruefung.

## 10. Auswahl fuer den kommenden Monat und frische Evidenz

Nach bestandenem historischen Monatsprozess und erst nach der in Abschnitt 6.1
verlangten Vertragsaenderung:

1. Fuer Zielanker `T` dieselbe unveraenderte Auswahlpipeline exakt auf
   `[T-730 Tage,T)` ausfuehren; ein spaeter Buttondruck darf keine nach `T`
   bekannten Daten hineinnehmen.
2. Aktuellen Kandidaten oder `NO_TRADE` einfrieren.
3. Reportfelder schreiben:
   - `as_of_day`;
   - `valid_from`;
   - `valid_until`;
   - `entry_enabled_at`;
   - Pipeline-/Daten-/Feature-/Kosten-/Gate-Hashes;
   - Kandidat, Parameter, Router und lokale Spezialisten;
   - Vorgaenger und Wechselgrund;
   - Prozess-OOS- und Stressstatus;
   - `manual_research_shadow_start_required=true`;
   - `canonical_adoption_eligible=false`.
4. Champion, Challenger und Cash paarweise vergleichen.
5. Nutzer entscheidet bewusst, ob der Kandidat als rein orderfreier
   `research_challenger_shadow` beobachtet wird.
6. Einen Anker-Monat ohne Code-, Parameter- oder Gate-Aenderung ausfuehren.
7. Diesen Monat genau einmal an das append-only Forward-OOS-Ledger dieser
   Pipelinegeneration anhaengen.

Der wiederholte Bedienablauf ist damit eindeutig:

```text
Anker 00:00 UTC
  -> Downloads/Data Gate aller drei Maerkte abschliessen
  -> Snapshot, Code, Pipeline, Kosten, Trialstand und Seed einfrieren
  -> Research rechtzeitig vor T+24 h abschliessen; keine neuen Entries, Altposition exit-only
  -> Report oeffnen und vor T+24 h manuell annehmen oder ablehnen
  -> frueher Abschluss/Annahme wartet; fehlende Entscheidung oder Fehler bedeutet NO_TRADE
T+24 h
  -> bei vorliegender Annahme entry_enabled_at=max(T+24 h, flat_time)
  -> eingefrorenen Kandidaten bis zum naechsten Anker nur orderfrei beobachten
naechster Anker
  -> keine neuen Entries des abgelaufenen Kandidaten
  -> Deployment-Intervall-Ledger genau einmal versiegeln
  -> offene Altposition nach alter Exitlogik beenden, neue wartet bis flat
  -> denselben Ablauf mit den dann neuesten Daten wiederholen
```

Ein Buttondruck nach `T+24h` plant den **naechsten** Anker und aktiviert nichts
rueckwirkend. Bis dessen Snapshot verfuegbar ist, darf die UI nur den geplanten
Status oder einen klar als nicht uebernehmbar markierten Diagnose-Preview
zeigen.

Scheitern Download, Audit, Research, Reproduzierbarkeit, Gates oder die
24-Stunden-Frist, ist die neue Monatsentscheidung `NO_TRADE`; die UI darf weder
einen alten Kandidaten still verlaengern noch auf einen Orderpfad ausweichen.
Dieses Research-`NO_TRADE` stoppt, ersetzt oder veraendert keinen bereits ueber
einen kanonischen Finalreport adoptierten Shadow-Kandidaten; beide Zustaende
bleiben getrennt benannt und gespeichert.

Der historische Prozess darf mit den heute bereits analysierten drei Jahren
keine frische `sealed_final_holdout`-Freigabe vortaeuschen. Der bestehende
`shadow/adoption.py`-Pfad verlangt zu Recht einen frischen, strikten
`final_evaluation`-Nachweis und ist deshalb fuer den aktuellen
Retrospektivkandidaten nicht erreichbar. Protocol v3 benoetigt fuer die sofort
gewuenschte Beobachtung einen **separaten, strikt orderfreien**
`research_challenger_shadow`-Pfad. Er darf weder Adoption-Eignung noch
Live-/Paper-/Testtrade-Freigabe melden und schreibt nur reproduzierbare Signale,
virtuelle Fills und taeglichen MTM-PnL.

Ein neues Feature, eine neue Strategie-Familie, ein neues Ranking, ein neues
Kosten-/Boundary-Modell oder ein geaendertes Gate ist eine neue
Challenger-Pipeline. Sie benoetigt eigene historische Prozess-Evidenz; ihr
Forward-Ledger startet bei null. Drei wirklich neu entstandene, vorab
eingefrorene Monate sind die Mindestwartezeit fuer eine erste
Champion/Challenger-Entscheidung, aber **kein** Ersatz fuer die bestehenden
12-Monats-/120-Trade-Gates und keine Freigabe. Eine vollwertige Promotion
erfordert einen kanonischen `final_evaluation`-Report mit genau einer
versiegelten Holdout-Auswertung. Der heutige `sealed_holdout_runner.py` prueft
jedoch einen einzelnen fixen Kandidaten und kann den Protocol-v3-Champion - die
monatlich refittende Pipeline - nicht korrekt evaluieren.

Vor einer Promotion ist deshalb eine versionierte Vertrags-, Schema- und
Gate-Aenderung fuer einen neuen **Pipeline-Final-Evaluator** erforderlich. Er
registriert ein frisches 365-Tage-Fenster vor dessen Beginn, simuliert die
gesamte eingefrorene Pipeline online mit zwoelf kausalen Refits nur aus den am
jeweiligen `T_j` bekannten Rohdaten und verbirgt alle Zwischenresultate bis Tag
365. Danach oeffnet er genau einmal und erzeugt den kanonischen
`final_evaluation`-Report. Bereits sichtbare Research-Challenger-/Forward-
Monate duerfen niemals nachtraeglich Teil dieses Fensters werden. Drei
Forward-Monate ersetzen den Pipeline-Finalnachweis nicht. Der permanente
Trial-Zaehler wird bei keiner Generation zurueckgesetzt.

Alle Challenger-Laufdaten liegen ausserhalb von Git. Der Pfad darf keine
API-Keys, Kontodaten, privaten Endpunkte oder Trading-API verwenden. UI-Refresh
ist rein lesend und zustandsneutral; Datenluecke, Stale-Feed, Hashabweichung oder
fehlende Kontextparitaet blockiert neue virtuelle Entries fail-closed.

## 11. Aktuelle technische Luecken

### P0: vor jeder Monatsautomatik

1. **Dynamischer Datenstichtag**
   - UI und Produktionsstarter sind derzeit auf `2026-07-07` fest verdrahtet.
   - Der neueste gemeinsame vollstaendige UTC-Tag aller drei Maerkte muss
     dynamisch bestimmt und danach fuer den ganzen Run eingefroren werden.

2. **Consumed Audit**
   - `2025-07-08` bis `2026-07-07` ist bereits verbraucht.
   - Heutige Protocol-v2-Laeufe koennen Diagnosen liefern, aber keinen neuen
     versiegelten 3-USDC-Nachweis. Im vorhandenen Dreijahresblock existiert
     kein unangetasteter finaler Holdout mehr.
   - Der aktuelle Vertrag verbietet auch spaetere Auswahl auf diesem Block.
     Ohne versionierte Protocol-v3-Vertragsaenderung bleiben alle Rolling-
     Ergebnisse diagnostisch und duerfen keinen Kandidaten starten.

3. **Rolling-Origin ist heute kein Monats-Refit**
   - `evaluate_rolling_origins` spielt einen bereits ausgewaehlten Kandidaten
     ueber Origins ab.
   - Die Reports kennzeichnen korrekt `pipeline_refit_per_origin=false` und
     `eligible_as_quality_gate_evidence=false`.
   - Protocol v3 braucht deshalb eine neue aeussere Orchestrierung, nicht nur
     eine Umbenennung des vorhandenen Rolling-Reports.

4. **Kontext-Paritaet bis Final und Shadow**
   - Research kann `context_filter` auswaehlen.
   - Sealed Holdout und Shadow laden/verwenden den Kontextpfad noch nicht
     durchgehend identisch.
   - Bis zur Reparatur darf ein Kontextgewinner nicht als uebernehmbar gelten.
   - Der orderfreie Challenger braucht einen Drei-Markt-Watermark: Zeitpunkt
     `t` wird erst verarbeitet, wenn geschlossene, exakt ausgerichtete
     ETHUSDC-, BTCUSDC- und ETHBTC-Bars fuer `t` vorliegen. Fehlend/stale
     pausiert fail-closed.

5. **Sealed-Report-Schema und Evidenzbedeutung**
   - Der aktuelle Research-Report besitzt mindestens `data_end_day`,
     `resume_supported` und `resume_state_path`, die der strikte
     Sealed-Holdout-Reader noch nicht akzeptiert.
   - Ein technisch reparierter Reader macht einen bereits angesehenen Zeitraum
     nicht wieder statistisch frisch.

6. **Vollstaendige Fingerprints und Trial-Ledger**
   - Rohdaten-ZIP/Checksum-Inhalte;
   - gemeinsamer Stichtag;
   - Feature-, Search-, Simulator-, Kosten-, Gate- und Kontextversion;
   - Pipelinegeneration, Boundary-/State-Vertrag und Trial-Ledger-Identitaet;
   - executable Code, Exchange Info, Pre-Bootstrap-Manifest und versiegelter
     Result-Store-Head;
   - der permanente Trial-Stand muss vor jeder neuen dateninformierten
     Router-/Featurearbeit existieren.

7. **Kompakte Artefakte**
   - heutige Cycle-Dateien liegen grob bei 390-425 MB;
   - abgeschlossene Reports erreichen mehrere GB;
   - zwoelf volle Pipeline-Refits sind damit nicht praktikabel.

8. **Simulator-/State-Paritaet**
   - 100 USDC angefordertes/reserviertes Entry-Notional, gerundetes
     ausgefuehrtes Notional <= 100 USDC, Fees separat;
   - Tick/Step/Notional;
   - eindeutige Intrabar-Prioritaet;
   - Warmup, Purging, Inner-Fold-End, Outer-Carry, terminale Liquidation und
     monatlicher Modellwechsel;
   - identische Research-/Final-/Challenger-Shadow-Entscheidung.

9. **Innerer Fold-Planer**
   - Die heutige WFV-Grenzlogik bildet nicht die in Abschnitt 6.3 fixierten
     sechs 60-Tage-Folds ab.
   - Der neue Planer muss Boundary-Objekte erzeugen und per Timestamp-Spies
     beweisen, dass kein Fit Daten aus Validation oder Outer-Test sieht.

10. **Zusaetzliche Rohdaten fuer Warmup**
   - Die heutigen 1.095 Tage beginnen genau bei `D1` und reichen fuer Features
     mit Vorlauf vor der ersten Origin nicht.
   - Alle drei Maerkte muessen mindestens `warmup_duration` frueher geladen,
     geprueft und im Snapshot gebunden werden.

11. **Rotation-State und FrozenCandidateBundle**
   - Der heutige Shadow haelt nur eine Strategie; Protocol v3 muss alte
     Exitlogik und neue wartende Entrylogik gleichzeitig versioniert halten.
   - Router, Spezialisten, skalare Parameter, Quantile, Scaler, Feature-State,
     Kontextpolicy, Kosten und Gueltigkeit brauchen ein gehashtes
     `FrozenCandidateBundle`, nicht nur flache `StrategyCandidate.params`.

12. **Resume-/Cache-Transaktionalitaet**
   - Checkpoints binden Boundary-Plan, Code, Drei-Markt-Snapshot, Exchange Info,
     Pipelinegeneration, Trial-Ledger-Head, abgeschlossene Origin-Digests,
     Outer-Rotation-State und Sealed-Store-Head.
   - Atomic Write/Replace, Dateisperre, Artefakt-Digests und deterministische
     Trial-IDs sind Pflicht; Cache-Keys enthalten Kontext-, Boundary- und
     Execution-Identitaet.

13. **Zwei Zeitaggregationen**
   - Die aktuelle Temporal-Aggregation ist nicht fuer 12 Ankerintervalle plus
     13/5 beruehrte Kalenderperioden ausgelegt.
   - `build_temporal_evidence` ordnet heutigen Trade-PnL nach Entry-Periode;
     Protocol v3 verlangt fuer Closed-Trade-Gates die eindeutige Exit-Periode.
   - Protocol v3 braucht getrennte Deployment-MTM- und Calendar-/Exit-Trade-
     Evidenz ohne Doppelzaehlung.

14. **Pipeline statt Einzelkandidat im Finalfenster**
   - Der aktuelle Sealed Runner friert einen Kandidaten/Parametersatz fuer das
     ganze Jahr ein; Champion v3 ist dagegen die monatlich refittende Pipeline.
   - Ein neuer, vertraglich versionierter Pipeline-Final-Evaluator muss alle
     zwoelf kausalen Refits innerhalb eines vorab registrierten frischen Jahres
     ausfuehren und Ergebnisse bis zum einmaligen Ende verborgen halten.

### P1: monatliche Auswahlmaschine

- innere Auswahl aus `research_loop_runner.py` als reine, wiederverwendbare
  Funktion fuer ein beliebiges 730-Tage-Fenster extrahieren;
- zwoelf aeussere Monats-Origins mit vollstaendigem Refitting implementieren;
- Outer-Ergebnisse bis Abschluss versiegeln;
- Trial-Ledger, DSR, PBO und Block-Bootstrap erzeugen;
- aktuelles 730-Tage-Refit fuer den Folgemonat erzeugen;
- Resume auf Origin- und Inner-Cycle-Ebene;
- versionierten Outer-Rotation-State und transaktionale Checkpoints;
- separaten orderfreien `research_challenger_shadow` statt einer falschen
  Sealed-Adoption bereitstellen.

### P2: fachlicher Router

- echte abgeschlossene 5m/15m/30m/1h/4h/1d-Features;
- Opportunity-Kapazitaet und Regime;
- lokale vorhandene Familien als Spezialisten;
- `NO_TRADE`-Router;
- Volumen/Kompression/Pullback-Reclaim;
- Kandidatenstabilitaet ueber Monats-Origins;
- gehashtes `FrozenCandidateBundle` mit Router, Spezialisten, Fit-State,
  Kontextpolicy und Gueltigkeitsgrenzen;
- kausales Seeding aller drei Marktlookbacks ohne Trade vor `valid_from`.

## 12. Schritt-fuer-Schritt-Umsetzungsagenda

Jeder Schritt ist ein eigener kleiner Commit/Ticket mit Tests. Kein spaeterer
Schritt beginnt, bevor der vorherige fail-closed abgeschlossen ist.

### Schritt 1 - Protocol v3, Kalender, State und Trial-Ledger einfrieren

Ergebnis:

- versionierter Vertrag fuer 12 Monthly Origins;
- exakte UTC-Boundaries, Warmup-, Purge-, Flat- und Modellwechselregeln;
- klare Begriffe Prozess-OOS, verbrauchter Sealed Holdout, Research Challenger
  Shadow und wirklich neuer Forward Shadow;
- aktuelle 730-Tage-Auswahl und Folgemonatsgueltigkeit;
- explizite Vertragsaenderung fuer Rolling-Training auf verbrauchter
  Rohhistorie oder bis dahin `diagnostic_only=true` ohne Kandidatenstart;
- append-only Trial-/Pipelinegenerations-Ledger;
- vorab fixierte Gates, Suchbudgets, Seeds und Stopregeln.

Abnahme:

- reine Boundary-Tests beweisen lueckenlose 365 OOS-Tage;
- Leap-/Non-Leap- und Late-Button-Fixtures beweisen exakt 12 Intervalle,
  `valid_from=T+24h` und niemals rueckdatierte Daten;
- jeder OOS-Tag erscheint genau einmal;
- kein OOS-Tag liegt in seinem eigenen Training;
- ein bereits datenbewerteter Versuch kann nicht unprotokolliert verschwinden;
- der historische Trial-Import ist als Untergrenze gekennzeichnet und erzwingt
  `DSR=INSUFFICIENT_TRIAL_HISTORY`, solange er nicht vollstaendig ist.

### Schritt 2 - Dynamischen Datensnapshot und Fingerprints bauen

Ergebnis:

- letzter gemeinsamer vollstaendiger UTC-Tag;
- verifizierte ZIP-Checksummen und versionierter Exchange-Info-Snapshot;
- ein unveraenderlicher Snapshot-Hash fuer alle drei Maerkte;
- Rohhistorie ab `D1-warmup_duration` fuer alle drei Maerkte;
- kein Produktions-Hardcode fuer `2026-07-07`.

Abnahme:

- veraenderte Datei, Exchange-Info, Feature-, Gate- oder Kosten-Version
  verhindert Resume;
- unvollstaendiger Tag wird ausgeschlossen, interne Luecke oder fehlender
  Warmup blockiert.

### Schritt 3 - Simulator- und Execution-Paritaet herstellen

Ergebnis:

- angeforderte/reservierte 100 USDC und ausgefuehrtes Notional getrennt, Fees
  separat verbucht;
- Tick-/Step-/Notional-Rundung aus dem Snapshot aus Schritt 2;
- next-tradable-price, pessimistische Intrabar-Prioritaet und Kostenstress;
- identische Warmup-, Purge-, Inner-Fold-End-, Outer-Carry- und
  Modellwechsel-Zustandsmaschine im Simulationskern.

Abnahme:

- Golden-Trade-Fixtures liefern im Researchkern und Replay bitgleiche Menge,
  virtuellen Fill, Fee, Slippage und PnL;
- kein Kernpfad kann einen perfekten High-/Low-Fill oder mehr als ein Lot
  erzeugen;
- fehlende Filter-/State-Evidenz blockiert fail-closed. End-to-End-Paritaet mit
  dem erst in Schritt 11 entstehenden Challenger Shadow wird dort abgenommen.

### Schritt 4 - Kontext-, Report- und Ausfuehrungskette angleichen

Ergebnis:

- Source-Report-Schema inklusive der neuen Resume-/Datenfelder synchron;
- ETHUSDC/BTCUSDC/ETHBTC auf demselben Informationsstand im Researchkern und
  Replay; die End-to-End-Challenger-Anbindung folgt in Schritt 11;
- Kontext kann nur veto/bestaetigen, nie handeln;
- verbrauchter Holdout bleibt sichtbar verbraucht und wird nicht neu etikettiert;
- der bestehende Single-Candidate-Sealed-Runner bleibt fuer seinen Vertrag
  erhalten; ein neues Pipeline-Final-Schema wird getrennt versioniert.

Abnahme:

- derselbe eingefrorene Kontextkandidat erzeugt im Researchkern und Replay
  identische Signale und Tradeentscheidungen;
- fehlender/versetzter Kontext blockiert fail-closed;
- kein Report kann aus historischer Prozess-Evidenz `fresh_sealed=true` machen;
- kein sichtbarer Forward-Monat kann nachtraeglich in das Pipeline-Finalfenster
  aufgenommen werden.

### Schritt 5 - Reports, Cache und Checkpoints komprimieren

Ergebnis:

- kompakter JSON-Index;
- getrennte deduplizierte Trade-/Daily-PnL-/Equity-Artefakte;
- keine mehrfach eingebetteten Millionen-Bar-Kurven;
- Resume je Outer-Origin und innerem Zyklus;
- Content-addressed Cache nach Daten-/Kontext-/Feature-/Kandidaten-/Fold-/
  Boundary-/Execution-/Simulatorhash;
- transaktionaler Checkpoint mit Code, Drei-Markt-Snapshot, Exchange Info,
  Pipelinegeneration, Trial-Ledger-Head, Origin-Digests, Rotation-State und
  Sealed-Store-Head.

Abnahme:

- ein 12-Origin-Lauf erzeugt kontrollierte, dokumentierte Artefaktgroessen;
- Resume und Cache-Hit liefern bitgleich dieselben Entscheidungsmetriken;
- Cache-Wiederverwendung ist im Trial-Ledger sichtbar;
- Atomic Replace, Lock, Digestpruefung und deterministische Trial-ID verhindern
  Teilstand oder doppelte Origin nach Prozessabbruch.

### Schritt 6 - Innere Auswahlpipeline und Fold-Planer extrahieren

Ergebnis:

```text
select_candidate(training_window, frozen_pipeline_config)
    -> candidate | NO_TRADE, evidence, fingerprints
```

Die bestehende Engine und die 40/12/3/2-Stufen werden wiederverwendet. Die
Fold-Boundaries werden durch den neuen exakten 6-x-60-Tage-Planer aus Abschnitt
6.3 erzeugt. Alle 12 getesteten Profile erhalten die gemeinsame 360-Tage-
Basisreihe; drei werden in volle WFV-Robustheit promoviert. Development-DSR/PBO
werden nach dem exakten Vertrag aus Abschnitt 7 berechnet, bevor eine Origin
einen Trading-Kandidaten auswaehlen darf.

Abnahme:

- Timestamp-Spies beweisen, dass die Funktion nichts nach `training_end` liest;
- gleicher Input/Hash erzeugt gleiche Auswahl;
- die volle taegliche Kandidatenmatrix, Trialzahl und alle
  `INSUFFICIENT_EVIDENCE`-Faelle sind reproduzierbar;
- alle 924 CSCV-Splits und DSR-Zwischenwerte sind reportiert;
- das globale Budget 4.160 erzeugt / 1.248 Basisreihen / 312 Full-WFV / 208
  Finalisten kann nicht ueberschritten werden.

### Schritt 7 - Multi-Timeframe-Feature-Store bauen

Ergebnis:

- kausal abgeschlossene 5m/15m/30m/1h/4h/1d-Daten;
- Feature-Version und Fit-State je Fold;
- gemeinsamer Drei-Markt-Watermark/Context-Timestamp;
- Opportunity- und Regimefeatures.

Abnahme:

- unfertige Bars sind nicht sichtbar;
- alle Normalisierungen werden nur auf Fold-Training fitten;
- Feature-Replay ist deterministisch;
- Warmup seedet alle drei Maerkte, erzeugt aber kein Signal oder PnL.

### Schritt 8 - Regime-Router und lokale Spezialisten verbinden

Ergebnis:

- Trend/Pullback, Kompression/Breakout, Range/Reversion, Stress/No-Trade;
- bestehende Familien hinter dem Router;
- ein Lot insgesamt;
- erklaerbarer Ablehnungsgrund fuer jedes Signal;
- gehashtes `FrozenCandidateBundle` fuer Router, Spezialisten, Fit-State,
  Kontextpolicy, Kosten, Rotation und Gueltigkeit.

Abnahme:

- Router kann jederzeit `NO_TRADE` waehlen;
- keine parallelen Lots;
- jede Tradeentscheidung ist auf Regime, Spezialist und Featurestand
  rueckfuehrbar;
- flache unvollstaendige `StrategyCandidate.params` koennen keinen Router als
  ausfuehrbar markieren.

### Schritt 9 - Zwoelf aeussere Monats-Origins implementieren

Ergebnis:

- komplette Neuauswahl je Origin;
- exakt naechstes Deployment-Intervall OOS, neue Entries erst `T+24h`;
- verkettetes 365-Tage-Ledger;
- getrennter 12-Deployment- und UTC-Calendar-/Exit-Trade-Aggregator;
- versionierter Exit-only-Outer-Rotation-State;
- Outer-Ergebnisse bis zum Ende geschlossen.

Abnahme:

- `pipeline_refit_per_origin=true`;
- zwoelf unterschiedliche Fit-Stichtage;
- OOS-Abdeckung exakt und ohne Duplikate;
- kein Outer-Wert beeinflusst einen spaeteren Fit;
- Grenzpositionen werden einmalig per realem MTM-Tag und Exit-Zeit verbucht;
- alter Bundle-State kann nur exiten, neuer erst nach `entry_enabled_at` und
  `flat_time` einsteigen.

### Schritt 10 - Statistik, Monthly Gate und aktuellen Refit bauen

Ergebnis:

- Prozessmetriken, Zielabstand, kandidatengleiche Capture-Ratio, PF, Drawdown,
  Deployment-Intervalle, Kalendermonate/-quartale, Regime, Konzentration und
  Stress;
- Development-DSR/PBO getrennt vom 10.000er Outer-Block-Bootstrap;
- getrennte Felder `historically_hit`, `historical_bootstrap_lower_bound`,
  `freshness`, `sealed_bootstrap_target_supported` und
  `statistically_supported`;
- Refit auf neuesten 730 Tagen mit `valid_from`/`valid_until` und
  Champion/Challenger/Cash-Entscheidung, bis zur Vertragsaenderung jedoch nur
  `diagnostic_only`;
- getrennt versionierter Pipeline-Final-Evaluator fuer ein einziges frisches,
  vorregistriertes und bis Tag 365 vollstaendig versiegeltes Online-Refit-Jahr.

Abnahme:

- fehlende Evidenz blockiert;
- Trial-Zaehler kann nicht zurueckgesetzt werden;
- Gates werden nicht aus dem Outer-Ergebnis heraus angepasst;
- Seed und 5-/10-/20-Tage-Bootstrap sind aus dem Pre-Bootstrap-Manifest
  bitgleich reproduzierbar;
- verbrauchte Historie kann niemals `statistically_supported=true` setzen;
- der Single-Candidate-Sealed-Runner kann keinen Protocol-v3-Finalstatus
  erzeugen, und sichtbare Forward-Monate koennen nicht nachregistriert werden;
- alle bestehenden strengeren Quality-Gate-v1-Grenzen bleiben wirksam;
- ein abgelaufener Kandidat kann keinen neuen Einstieg erzeugen.

### Schritt 11 - Research Challenger Shadow und UI anschliessen

Waehren des Laufs sichtbar:

- Datensnapshot und Hash;
- Origin 1-12, innerer Fold, Kandidatenstufen;
- Resume/Checkpoint und technische Safety;
- keine vorzeitig geoeffnete Outer-PnL.

Durchgehend erhalten und sichtbar bleiben die Pflichtaktionen fuer
Datenpruefung sowie Backtest Start, Pause, Fortsetzen, Abbruch, Neustart und
Zuruecksetzen. Paper, Testtrade und Live bleiben als gesperrte Zustaende
sichtbar. Der neue Research-Challenger-Button ersetzt oder versteckt keinen
dieser Bedien- oder Sicherheitszustaende.

Nach Abschluss sichtbar:

- Prozess-OOS und alle Pflichtmetriken;
- `historically_hit`, `historical_bootstrap_lower_bound`, `freshness`,
  `statistically_supported` und Zielabstand;
- Champion/Challenger/Cash und Folgemonatsgueltigkeit;
- manueller Button nur fuer `research_challenger_shadow`;
- klare Trennung von historischer Pseudo-Live-, verbrauchter Holdout- und neuer
  Forward-Evidenz.

Abnahme:

- keine Orders, kein Live, kein Paper und kein bestehender Testtrade-Pfad;
- keine API-Keys, Kontodaten, privaten Endpunkte oder Trading-API; Laufdaten
  bleiben ausserhalb von Git;
- Signale/Fills bleiben virtuell und reproduzierbar;
- UI-Refresh ist zustandsneutral, Daten- oder Kontextluecken blockieren;
- ein Drei-Markt-Watermark verarbeitet `t` erst nach drei exakt ausgerichteten
  geschlossenen Kontext-/Handelsbars;
- eigener Reporttyp, Schema, Storage-Root, Controller und UI-Action verhindern,
  dass `adopt_for_shadow` einen retrospektiven Challenger finden oder annehmen
  kann;
- Golden-Trade-Fixtures aus Schritt 3 sind end-to-end im Challenger Shadow
  bitgleich;
- ein Familien-/Featurewechsel erzeugt eine neue Pipelinegeneration und ein
  leeres Forward-Ledger;
- GUI-Neustart setzt den Run aus dem letzten gueltigen Checkpoint fort.

### Schritt 12 - Erst danach neuer voller Research-Lauf

Der erste Protocol-v3-Lauf ist erfolgreich gestartet, wenn:

- die Rolling-Reuse-Vertragsaenderung beschlossen ist oder der Lauf strikt
  `diagnostic_only` bleibt;
- alle P0-Paritaets-/Snapshot-/Schema-/Resume-Tests gruen sind;
- Warmup aller drei Maerkte und der Trial-History-Status ehrlich gebunden sind;
- zwoelf Outer-Origins wirklich refitten;
- alle 365 Prozess-OOS-Tage einmalig abgedeckt sind;
- Kontext aktiviert und im Research Challenger Shadow ausfuehrbar ist;
- bestehender Audit/Sealed-Holdout, Live, Paper, Testtrade und Orders geschlossen
  bleiben;
- die ersten Checkpoints kompakt und reproduzierbar sind.

Danach wird das Ergebnis ausgewertet. Vorher werden keine Gates gelockert und
keine Parameter anhand von Outer-Ergebnissen veraendert.

## 13. Definition von Erfolg

Der zukuenftige Backtest beantwortet am Ende genau diese Fragen:

1. Welche Kandidatenfamilie und welche Parameter haette die unveraenderte
   Pipeline an jeder der letzten zwoelf Deployment-Grenzen gewaehlt?
2. Was haette die verkettete Policy mit neuer Entrylogik und gegebenenfalls
   alter Exit-only-Position im jeweiligen Folgeintervall nach realistischen
   Kosten verdient?
3. Erreichte der verkettete Prozess historisch mindestens 3 USDC pro
   Kalendertag?
4. Ist dieses Ergebnis nach Kosten, Drawdown, Regimen, Parameter-Nachbarschaft,
   Development-DSR/PBO und retrospektivem Outer-Bootstrap noch belastbar, ohne
   daraus falsche frische Evidenz abzuleiten?
5. Welchen Kandidaten waehlt dieselbe Pipeline aus den neuesten 730 Tagen fuer
   das kommende Deployment-Intervall, sofern der Vertrag diese Rolling-
   Selektion erlaubt?
6. Ist ein Wechsel gegenueber Champion und Cash gerechtfertigt?
7. Welche Aussage ist nur historisch, und welche stammt aus einem wirklich
   vorab versiegelten neuen 365-Tage-Fenster?

Nur wenn diese sieben Antworten vollstaendig und reproduzierbar vorliegen, ist
der Monats-Backtest fachlich das, was der Nutzer beabsichtigt.

## 14. Quellen und methodische Grundlage

- [Tashman (2000), Out-of-sample tests of forecasting accuracy](https://doi.org/10.1016/S0169-2070(00)00065-0)
- [Varma und Simon (2006), Bias in error estimation when using cross-validation for model selection](https://brb.nci.nih.gov/techreport/Varma-Simon-CrossValid.pdf)
- [Dwork et al. (2015), Generalization in Adaptive Data Analysis and Holdout Reuse](https://papers.nips.cc/paper_files/paper/2015/hash/bad5f33780c42f2588878a9d07405083-Abstract.html)
- [White (2000), A Reality Check for Data Snooping](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00152)
- [Hansen (2005), A Test for Superior Predictive Ability](https://doi.org/10.1198/073500105000000063)
- [Bailey und Lopez de Prado, The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- [Lo (2002), The Statistics of Sharpe Ratios](https://traders.berkeley.edu/papers/The-Statistics-of-Sharpe-Ratios.pdf)
- [Politis und Romano (1994), The Stationary Bootstrap](https://doi.org/10.1080/01621459.1994.10476870)
- [Binance Spot Filters](https://developers.binance.com/en/docs/products/spot/filters)
- [Binance Spot Commission FAQ](https://developers.binance.com/en/docs/products/spot/faqs/commission_faq)
- [Binance Spot REST API](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Binance Public Data](https://data.binance.vision/)
