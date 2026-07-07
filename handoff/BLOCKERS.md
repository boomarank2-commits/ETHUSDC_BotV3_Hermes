# Blockers

Current blockers:
- User approval required before any next implementation step.
- No real market data has been downloaded or audited from disk.
- Inventory status command shows path presence only; it does not validate kline completeness from real files.
- The source-tree module command is verified with `PYTHONPATH=src`; no packaging/install workflow was changed in this ticket.
- Live trading remains locked by project contract.
- Paper trading remains locked.
- Testtrade remains locked.
- No mutable runtime truth should be created until explicitly approved.
- No raw market data should be stored inside the repository.

Not blockers:
- The data catalog template and schema represent required ETHUSDC/context sources.
- Pure in-memory kline audit rules exist for artificial or already-loaded records.
- Pure local inventory helpers can derive expected paths and mark them missing/present/blocked without a downloader.
- Inventory status command can display honest local path status in text or JSON.
