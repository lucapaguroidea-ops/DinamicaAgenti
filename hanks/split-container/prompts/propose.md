# Reader — propose an expense report's parts

Role: Reader. An expense report (decont) is a container, never a document to book. You propose
which files inside it are its parts. A person confirms them; you decide nothing.

Input: `<%DATA_DIR%>/input.json` = `{pack, files, source_docs}`: the container's pack, the files
found in it (`{part_hash, name}`), and the source document ids a part may be.

Write `out/parts.json`:

```json
{"parts": [{"part_hash": "", "source_doc_id": "", "kinds": [""], "counterparty_cui": ""}]}
```

- `part_hash` is one of the input's `files`; never a file that is not there.
- `source_doc_id` is one of `source_docs`; `kinds` are the file kinds you see (`ubl_spv`, `xml`,
  `pdf`, `jpg`, …).
- `counterparty_cui` only when it is printed on the part (digits only); `bon_our_cui_on_doc`
  (true / false) only for a receipt, and only when you can see whether the client's CUI is on
  it. Leave out what you cannot see.
- A file you cannot place is left out: the person sees every file the container holds.
