# Contract data

`ref-0.9.json` is copied byte-for-byte from the **published specification data**
`bennett-isa-spec/spec/ref-0.9.json`, not from a sibling implementation. The
document and envelope hashes are in SPEC_VERSIONS.toml. The estimator's parser,
arithmetic, summaries and source adapters are independent code derived from the
published prose/grammar. No VM/reference/scheduler source was copied or imported.

`tests/fixtures/example1.bisa` through `example10.bisa` are the ten complete
object code fences of published ISA 0.9 §16.3, extracted in document order,
preserving the final LF. Their normative declared hashes are checked.

`classical-step-16.json` is an estimator test target written from §8's schema.
It declares a one-second classical step, no quantum gates and pointer widths
16/32/64 so rung-3's original 16-bit object can be tested without changing that
object or pretending a 32/64-bit target admits it.

Sibling `bennett-targets/targets/*.json`, conformance ladder data and the
published controlled-action certificate are read as data in the tests. The VM
is invoked only as a binary differential oracle. See scripts/differential.py
for its exact comparison scope and unavailable rung-2 result.
