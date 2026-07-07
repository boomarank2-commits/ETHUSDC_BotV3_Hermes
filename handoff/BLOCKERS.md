# Blockers

Current blockers:
- User approval required before any next implementation step.
- No real market data has been downloaded or audited from disk.
- No user-approved command has been added yet to run the inventory against `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Inventory currently checks path presence only; it does not validate kline completeness from real files.
- Live trading remains locked by project contract.
- Paper trading remains locked.
- Testtrade remains locked.
- No mutable runtime truth should be created until explicitly approved.
- No raw market data should be stored inside the repository.

Not blockers:
- The data catalog template and schema represent required ETHUSDC/context sources.
- Pure in-memory kline audit rules exist for artificial or already-loaded records.
- Pure local inventory helpers can derive expected paths and mark them missing/present/blocked without a downloader.
