# Blockers

Current blockers:
- User approval required before any next implementation step.
- No real market data has been downloaded or audited from disk.
- Raw-data contract defines target paths only; it does not create folders or files.
- No manifest schema/template has been implemented yet for future raw-data directories.
- Inventory status command shows path presence only; it does not validate kline completeness from real files.
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
- Raw-data target path contract now defines where future data and manifests may live outside the repository.
