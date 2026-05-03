# BUNDLE_001 — sample_input

- **Project:** sample_input
- **Target:** chatgpt
- **Mode:** balanced
- **Bundle:** 1 of 1
- **Estimated tokens:** 425
- **Token budget:** 90,000
- **Token estimator backend:** tiktoken (cl100k_base)
- **Documents in bundle:** 5
- **Included DOC_IDs:** DOC_0001, DOC_0002, DOC_0003, DOC_0004, DOC_0005

## How to cite from this bundle

When you answer questions using these documents, cite both the `DOC_ID` and the `SOURCE_FILE` shown in each document's identity header. Prefer exact quotes for technical specifications, measurements, dates, deadlines, and warnings.

These documents were converted from their original formats. If a passage looks malformed, refer back to the original file listed in `SOURCE_PATH`.


<!-- ================================================== -->

---
DOC_ID: DOC_0001
SOURCE_FILE: data.csv
SOURCE_PATH: data.csv
ORIGINAL_EXTENSION: .csv
---

# CSV: data.csv

- **Row count:** 3
- **Column count:** 3
- **Columns:** part, price, in_stock
- **Original copied to:** `data/DOC_0001_data.csv`

## Preview (first 3 rows)

| part | price | in_stock |
| --- | --- | --- |
| fluid | 12.99 | True |
| filter | 8.5 | True |
| gasket | 3.25 | False |


<!-- ================================================== -->

---
DOC_ID: DOC_0002
SOURCE_FILE: intro.html
SOURCE_PATH: manuals/pages/intro.html
ORIGINAL_EXTENSION: .html
---

# Transmission Manual

Replace the fluid every **30,000 miles**.

## Tools required

* 10mm socket
* Drain pan

| Step | Action |
| --- | --- |
| 1 | Lift vehicle |
| 2 | Loosen plug |

![diagram](MISSING/../../missing/diagram.png)


<!-- ================================================== -->

---
DOC_ID: DOC_0003
SOURCE_FILE: icon.png
SOURCE_PATH: notes/icon.png
ORIGINAL_EXTENSION: .png
---

# Image: icon.png

![icon.png](assets/DOC_0003/icon.png)

[Image asset copied. No OCR performed in Version 1.]


<!-- ================================================== -->

---
DOC_ID: DOC_0004
SOURCE_FILE: quick.txt
SOURCE_PATH: notes/quick.txt
ORIGINAL_EXTENSION: .txt
---

A short plain text note.

Line two.
Line three: special chars - em-dash, cafe, naive, hello.


<!-- ================================================== -->

---
DOC_ID: DOC_0005
SOURCE_FILE: README.md
SOURCE_PATH: notes/README.md
ORIGINAL_EXTENSION: .md
---

# Sample Project

This is a small sample project used to smoke-test the packer.

## Goals

- Verify Markdown passthrough works.
- Verify HTML conversion strips scripts and preserves headings.
- Verify the manifest and bundle files are written.
