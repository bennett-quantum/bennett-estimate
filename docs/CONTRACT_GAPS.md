# Source binding decisions required for exact estimates

These are contract questions for `bennett-isa-spec`, tracked locally by
`bennett-estimate-bph.4`. The proposals below have **not** been adopted by this
estimator. The decimal/resource-row choices in K12 remain settled; these gaps
concern the source-derived operation set, before exact rational aggregation.

The evidence is against the document and catalog pinned in SPEC_VERSIONS.toml.
No sibling implementation was consulted as a source of semantics.

## EST-SOURCE-01: fixed classical pseudo-location wire binding

The legal memoryless oracle in `tests/fixtures/parameter-source-gap.bisa` reads
`a:i1` in `r = lift.add x a`, with B=2. Its reference payload is `(x+a) mod 2`.
Both arguments `"0"` and `"1"` are well typed under K13 and MUST be supported
under K12. This is not a basis-input request: x, target and fault remain quantum.

Relevant published text:

- §4.7 says an iN/ptr argument is a pseudo-location of its bit width, and an
  f64 argument is a 64-bit pseudo-location preserving the binary64 bits.
- §3.7 says classical parameters are not locations, stack cells or frame slots.
- K19 wire actuals are live wire names, indexed wires, concatenations or ranges;
  a K24 `value` actual does not supply a wire actual.
- `ref-0.9.json` recipe `lift.add` requires `b:wire[N]`. Its first source capture
  uses CX from that wire; it has no `value` formal or constant-preparation arm.
- K25's exact State list has pc/pc-prime/fault/code/result, layout state,
  locations, local regions, table and frames. It includes no allocation or
  initialisation rule for a classical pseudo-location.

Consequently a builder needs a rule defining the physical wire for `a`, its
class, lifetime, initial value, sharing and preparation/removal events. Allocating
it once, allocating it per padded row, or specialising known controls gives
different resource rows/ordinals. The estimator must not select one silently.

Proposed exact text, for upstream acceptance or replacement, after K25's
construction-state paragraph:

> **Fixed classical pseudo-location state.** In the reference realisation,
> each non-token oracle classical argument read as a pseudo-location has a
> distinct clean allocation of its declared bit width. Each non-token classical
> parameter of a fixed lproc instance read as a pseudo-location has another
> distinct clean allocation of its declared width; equal
> values or shared argument positions do not merge these allocations. Their
> class is `any`. Append their State records immediately after `result_val`,
> first in oracle signature argument order, then in canonical fixed-instance
> order and each instance's classical parameter order. Their `initial` is the
> resolved unsigned bit-vector encoding; f64 uses its exact 64-bit pattern.
> Their `I` is empty. They are not source interface slots, global-id locations,
> stack cells or frame slots. A row reading such a pseudo-location binds its
> wire actual to this allocation. The existing State acquire/literal/inverse/
> release constructors provide all preparation and restoration events and
> their ordinary `$construct`/`$release` addresses. Tokens have no such record.

That is one reviewable policy, not an inference that it is the intended policy.
An alternative using classical specialisation must specify its exact reference
constructor trace, not merely assert that it computes the same function.

## EST-SOURCE-02: implicit length width in memory rows

`tests/fixtures/implicit-length-source-gap.bisa` has a legal `lift.load.i8`.
Its byte length is the mathematical integer 1. The published `lift.load` recipe
has independent integer formals `L`, `E`, `N`, `B`, allocates `len[L]`, and
prepares B into it. N=8 and B=1 are fixed by the source; the text does not fix
whether L=1, ptr_width, or another adequate width. Even if E is unchanged,
different L changes peak space and occupancy. The explicit `lift.boundscheck p 1`
in normative example 2 likewise needs a wire actual for the literal operand.

Proposed exact text, in the §11.1 source-binding rules:

> For `lift.load.iN` and `lift.store.iN`, bind B=N/8 and
> L=max(1,ceil(log2(B+1))). Bind E=max(ptr_width,L)+1. The recipe's private
> `len` allocation has precisely L wires. A literal length n in
> `lift.boundscheck p n` has the same minimal unsigned width
> L=max(1,ceil(log2(n+1))) and E=max(ptr_width,L)+1. A nonliteral length uses
> its declared pseudo-location/location bit width as L. The literal form
> expands through the published `lift.boundscheck.literal` adapter below;
> it is not an implementation-specific prelude.

The proposal requires publishing this additional adapter (and updating the
catalog count/envelope binding), with formals
`P,L,E,C,T,F,B,p,base,size,live,pinned,atop,flag,faulted,code` typed like the
existing `lift.boundscheck`, except integer B replaces wire n:

```json
[
  {"alloc":"len","class":"any","state":"clean","width":"L"},
  {"invoke":"value.literal","args":["L","B","len"]},
  {"invoke":"lift.boundscheck","args":["P","L","E","C","T","F","p","len","base","size","live","pinned","atop","flag","faulted","code"]},
  {"inverse":true,"body":[{"invoke":"value.literal","args":["L","B","len"]}]},
  {"release":"len"}
]
```

All allocations are unconditional and literal/row semantic gates inherit the
row's effective controls, following the existing constructor rules. If upstream
chooses another length-width or literal-binding policy, it must publish that
trace and a numerical resource/ordinal witness instead.

## Evidence and required resolution

The tests independently admit the two objects; the published VM binary also
accepts both with matching object hashes and returns `(x+a) mod 2`, code 0 and
two reference steps for all four x/a combinations. K19 cannot bind an integer
as a wire. The tests also exhibit distinct resource results for L=1 versus
L=32 on the same load recipe shape. They do not bless either trace as the
published source binding. The supported source adapter reports these IDs before
emitting an exact estimate for the affected inputs.

Completion requires a published source-binding decision with positive/negative
source witnesses, exact resource/ordinal witnesses and any resulting expansion
identity update. Pending that decision, layout/state construction and other
unambiguous implementation work can continue, but full K12 parameterised/source
coverage cannot honestly be marked complete.
