# Blockers

Current blockers:
- User approval required before any next implementation step.
- No real market data has been downloaded or audited from disk.
- Raw-data contract defines target paths only; it does not create folders or files.
- Raw-data manifest schema/template exists, but no real source manifest has been created next to data.
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
- Raw-data target path contract defines where future data and manifests may live outside the repository.
- Raw-data manifest template/schema now defines conservative not-downloaded/not-audited manifest metadata.
