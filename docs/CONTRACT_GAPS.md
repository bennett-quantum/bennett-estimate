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

## EST-CONTEXT-03: token identity aliasing is not encoded by K13 tuples

K12/K13 correctly fix decimal handling and tuple-only parameter encoding. This
is a separate context question: §5.3 matched pairs retain token identities as
well as tuples, §5.4 produces a fresh token for each successful budget.mint,
and §4.1 uncall compares recorded boundary argument values. Equal four-string
tuples do not say whether two input operands are one handle or two handles.

`tests/fixtures/token-alias-source-gap.bisa` is VM-admitted with object hash
`cda0f55ff3f299b165453ff9162b051ddf96856a799d22e09499c226bf35c011`.
Its CC root calls a no-op R function with token a, then uncalls with token b.
Under handle identity equality, the same handle at both positions completes in
four source steps; two distinct handles for the same tuple fault at the third
step. Both encode as args [["1","0","0","0"],["1","0","0","0"]] and have the
same K13 params_hash. These two counts are derived from the printed instructions,
not claimed as a VM execution differential: the installed run-cc binary reports
budget.mint unimplemented, and run-program cannot expand lift.retval yet.
The oracle declaration provides a program oracle for validating host tokens.

There is also a Q-region consequence: two oracle-call occurrences using a and b
may or may not be a K81 matched pair, so cleanup-carrier applicability/selection
can depend on the same absent alias relation. This must be decided before
implementations guess a root alias policy. Current code distinguishes known fresh
mints, preserves forwarding of a single argument, and raises EST-CONTEXT-03 only
when an unresolved equality actually matters; a stated conditional step bound
remains available. Reusing a Python list is not an alias declaration in JCS.

Proposed normative text (UNADOPTED, preserving identity-based matching):

> Token identity context. A resolved invocation additionally carries
> token_aliases, an array of nonnegative integer identity-class labels. Position
> zero denotes the separately supplied invocation token; subsequent positions
> denote token-typed arguments in signature order. Equal labels denote the same
> valid token identity and require equal tuples; unequal labels denote distinct
> identities even when their tuples agree. Labels are canonical by first
> occurrence, starting at zero. This records equality, never a process-local
> handle. With no token arguments the array is [0]; otherwise the request MUST
> supply it and a missing or conflicting context is E_ARG.
>
> bindings.invocation and schedule bindings carry this token_aliases array. It is
> copied and compared as part of request/schedule/certificate matching. The
> existing params_hash remains SHA-256 of the args array. Source forwarding and
> fixed-binding formation preserve these identity classes; a successful
> budget.mint introduces a fresh identity class attached to its defining
> occurrence. Nested contexts preserve the resolved classes through their call
> paths instead of reconstructing identities from tuple equality.
>
> The estimate request accepts token_aliases_jcs and token_aliases_len following
> params_len; the scheduler exposes bennett_sched_request_set_token_aliases with
> the same JCS array. Their parsers validate canonical labels, arity and tuple
> consistency before realisation. Certificate invocation schemas admit the
> token_aliases field and require it for scheduled identity-dependent subjects.

This is a proposed contract change, not implemented schema or policy. The
orchestrator must file it in bennett-isa-spec under COMMON rule 14. A different
ratified identity/equality rule could resolve it instead. Existing K12/K13
choices have not been reopened or silently replaced.

## EST-SOURCE-03: return delivery scans can exceed the history slot

Local tracking: bennett-estimate-bph.6. The pinned ISA document is unchanged
(SHA-256 021d5df978f293c36174b73de9facc0884f7502a4bc5c0ab7a621b0ca7071c25).
Witness: tests/fixtures/ret-delivery-source-gap.bisa, object hash
b026d3de1b9636bdb7c45deb771f3ccb468fd0e0dbb2bee38da6863500e4d500.
The published VM admits it and returns payload 1/code 0/steps 4 with
`run-oracle ... root --input '' --budget 4,1,8,1`.

The oracle declares r:reg[1] and an unused ghost:reg[8]; its zero-argument
lproc declares one reg[1] result. S_cells=3 gives Sc=4 and depth_limit=1
gives Dc=2. The call's three slots have widths (4,4,2); the return's
slots have widths (1,4,2). Section 3.6 therefore gives W=(4,4,2), so the
published lift.ret delivery formal N=4. K25 nevertheless requires the
complete Globals list with ghost's actual declared width 8. The recipe's
R4 loop visits bit 0..width-1 and references delivery[4] outside that
four-wire actual. Direct published-recipe expansion fails at that index;
this is not a VM payload failure or a guessed lproc binding.

Proposed exact normative change, UNADOPTED: append to the §3.6 Frame
layout paragraph:

> If the instantiated lproc closure contains lift.ret, W_1 is additionally
> at least W_max (§3.7), including locations that do not occur in a row's
> write set. The ref lift.ret formal N is this complete W_1-bit disp_1
> slot. Every frame retains that width. This makes the complete K25
> closure-delivery scan well-typed at every location. Other slot widths
> remain the maxima of their listed captures and assignments.

This would widen the witness's first slot from 4 to 8 and its history
frame from 17 to 21 bits. It changes exact resource costs and must be
published before a consumer adopts it. An equivalent ratified recipe
change that bounds each delivery scan by min(width,N) could instead
resolve the conflict, but no such scalar/formal adapter is currently
specified. The estimator raises EST-SOURCE-03 for positive-B affected
requests and emits CLI pending evidence with no resource rows. B=0 has
no step expansion and needs no delivery access; its construction/commit
estimate remains available. All other independent implementation work
continues.
