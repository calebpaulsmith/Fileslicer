# Source Manifest — sample_input

- **Target:** chatgpt
- **Mode:** balanced
- **Total documents:** 5
- **OK:** 4  |  **Skipped:** 0  |  **Failed:** 1
- **Estimated total tokens:** 288

| DOC_ID | Source File | Path | Type | Status | Tokens | Chars | Words | Bundle | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DOC_0001 | data.csv | data.csv | csv | ok | 99 | 298 | 61 | 02_BUNDLE_001.md | - |
| DOC_0002 | intro.html | manuals/pages/intro.html | html | failed | 0 | 0 | 0 | - | Reader crashed: No module named 'bs4' \| ModuleNotFoundError: No module named 'bs4' |
| DOC_0003 | icon.png | notes/icon.png | image | ok | 53 | 111 | 13 | 02_BUNDLE_001.md | image copied; no OCR in v1 |
| DOC_0004 | quick.txt | notes/quick.txt | text | ok | 49 | 93 | 16 | 02_BUNDLE_001.md | - |
| DOC_0005 | README.md | notes/README.md | text | ok | 87 | 244 | 39 | 02_BUNDLE_001.md | - |
