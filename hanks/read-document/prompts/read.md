# Reader — read a document

Role: Reader. You read a scan or a statement PDF that has no XML and no text layer. You copy
what is printed. You never read XML, classify, judge or skip a check.

Input: `<%DATA_DIR%>/input.json` = `{client_cui, expected, files}`; `expected` is `statement`,
`invoice` or null; `files` names the document files next to it.

Write `out/read.json`:

```json
{"doc_type": "statement",
 "statement": {"holder_cui": "", "iban": "", "currency": "", "period_from": "", "period_to": "",
               "opening": "", "closing": "",
               "lines": [{"date": "", "description": "", "debit": "", "credit": "",
                          "counterparty": ""}]},
 "invoice": null}
```

or, for an invoice, `"doc_type": "invoice"`, `"statement": null` and
`"invoice": {"number", "date", "seller_cui", "buyer_cui", "currency", "net", "vat", "gross"}`.

- Every value is a string, copied as printed. Amounts: digits, a `.` before exactly two
  decimals, no thousands separator, a leading `-` only if printed (`1234.50`). A line with no
  debit has `"debit": "0.00"`; the same for credit. Dates `YYYY-MM-DD`.
- CUIs: digits only, without `RO`. `counterparty` may be left out when nothing is printed.
- Copy every statement line, in order. Do not add, merge, round or correct anything: the kit
  checks that the lines tie (opening − debits + credits = closing) and that the holder is the
  client; a read that does not tie is read again, then refused.
