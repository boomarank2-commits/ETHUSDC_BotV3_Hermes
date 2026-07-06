# 08 - Human Backtest Dashboard Fields

Diese Datei definiert, welche Werte ein Mensch sehen muss, um einen Backtest als brauchbar oder schlecht einzuordnen.

Optik ist zweitrangig. Klarheit ist Pflicht.

---

## 1. Status oben im Dashboard

Pflichtfelder:

- Botname
- Symbol: ETHUSDC
- Quote: USDC
- Modus: idle / data_check / backtest / paper / testtrade / live_locked / error
- aktive Run-ID
- Runtime-Konsistenz
- letzter Fehler
- letzter Refresh
- Startkapital
- Risikoprofil
- Zeitbudget

---

## 2. Datenstatus

Pro Datenquelle sichtbar:

- Datenname
- Symbol
- Rolle
- Status
- Fortschritt
- verfuegbare Tage
- benoetigte Tage
- included_in_backtest ja/nein
- diagnostic_only ja/nein
- positive_candidate_influence_allowed ja/nein
- Fehler/Warnung/Sperrgrund

Pflichtdaten:

- ETHUSDC Klines 1m
- ETHUSDC AggTrades
- ETHUSDC Trades
- ETHUSDC Exchange Info
- Fee Reference
- Slippage-Modell
- BTCUSDC Klines 1m
- ETHBTC Klines 1m
- derived timeframes
- market context features
- microstructure features, falls reif
- BookTicker, falls reif
- Orderbook, falls reif

---

## 3. Backtest-Kette

Die UI muss die Kette sichtbar machen:

```text
Daten -> Features -> Training -> Kandidaten -> Spezialisten -> Router -> Engine -> Trades -> Reports
```

Pflichtfelder:

- Phase
- aktueller Schritt
- Progress
- checked_candidates
- valid_candidates_found
- opportunity_event_count
- candidate_situation_count
- recognized_setup_count
- final_profitable_specialist_cluster_count
- trade_allowed_setup_count
- no_trade_setup_count
- router_trade_signals
- engine_entry_attempts
- engine_entry_executions
- engine_entry_rejections
- total_trades

---

## 4. Ergebnisfelder

Pflicht:

- total_profit_usdc
- usdc_per_day
- total_trades
- trades_per_day
- win_rate_pct
- profit_factor
- max_drawdown_usdc
- max_drawdown_pct
- fees_usdc
- slippage_usdc
- best_day_usdc
- worst_day_usdc
- best_full_month_usdc
- worst_full_month_usdc
- positive_days
- negative_days
- neutral_days
- no_trade_days
- active_days

---

## 5. Schrott-Erkennung

Ein Lauf muss klar als schlecht erkennbar sein, wenn:

- keine validen Kandidaten existieren
- keine Router-Setups existieren
- Router-Trade-Signale 0 sind
- Engine-Entry-Versuche 0 sind
- Trades 0 sind
- usdc_per_day unter Ziel liegt
- Fees/Slippage Edge auffressen
- Aktivitaet zu gering ist
- Reports fehlen
- Runtime inkonsistent ist

Die UI darf hier nicht gruen anzeigen.

---

## 6. Kandidatenuebernahme

Pflichtfelder:

- candidate_config exists ja/nein
- candidate_run_id
- active_run_id
- candidate_eligible_for_adoption
- adoption_allowed
- adoption_blockers
- active_config exists ja/nein
- Unterschied active vs candidate

Uebernahme darf nur aktiv sein, wenn alle Sperren gruen sind.

---

## 7. Live/Paper/Testtrade-Sperren

Pflicht:

- Paper freigegeben ja/nein
- Testtrade freigegeben ja/nein
- Live freigegeben ja/nein
- Sperrgrund je Modus

Live bleibt standardmaessig gesperrt.

---

## 8. Minimaler UI-Erfolg

Ein Nutzer muss nach einem Backtest in weniger als einer Minute erkennen:

1. War der Lauf technisch erfolgreich?
2. War der Lauf fachlich brauchbar?
3. Wurde das Ziel erreicht?
4. Falls nein: warum nicht?
5. Was ist der naechste sinnvolle Schritt?
