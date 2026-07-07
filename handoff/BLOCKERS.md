# Blockers

Current blockers:
- User approval required before any next implementation step.
- No real market data has been downloaded or audited from disk.
- No user-approved local raw data inventory has been scanned yet.
- Live trading remains locked by project contract.
- Paper trading remains locked.
- Testtrade remains locked.
- No mutable runtime truth should be created until explicitly approved.
- No raw market data should be stored inside the repository.

Not blockers:
- The data catalog template and schema can now represent required ETHUSDC/context sources.
- Pure in-memory kline audit rules exist for artificial or already-loaded records.
- The project can proceed to a later local inventory step without introducing a downloader.
