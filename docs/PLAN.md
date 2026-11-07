# ISA 0.9 estimator requirements

Contract: SPEC_VERSIONS.toml pins the published ISA document and ref catalog.
This matrix records requirements and verification coverage, not a replacement
task tracker. Durable implementation work is `bennett-estimate-bph` and children.

| Requirement | Published clause IDs / section | Implementation and verification |
|---|---|---|
| EST-01 Read canonical object sections, reject unknown fields, preserve typed metadata | ISA-9.1, ISA-16.1, ISA-16.2 | Partial independent reader; section ordering, duplicate JSON keys, canonical metadata/whitespace and large-number checks. Full opcode/type/link validation remains `.1`. |
| EST-02 Recompute interface/closure/object identities and SCCs | ISA-9.2; corrected layout paths in ISA-9.2-P1 | All ten §16.3 normative examples match every declared interface hash. Reader also handles 0.8 dotted layout paths for rung-3 data. Tier, location/interface roles, bounds and terminators are also checked. Complete unresolved linking remains `.1`. |
| EST-03 Load target descriptions as data | ISA-8.1, ISA-8.2, ISA-8.3, ISA-8.4 | Tests load every JSON in the gate-pinned target corpus; no target implementation code imported. Numbers-only schema contexts, scheme expression scopes and concrete topology placements are checked. All pinned targets load as data; K86 model metadata is accepted/hash-bound, with unchecked or unsupported-model obligations reported; remaining validation work stays `.2`. |
| EST-04 Evaluate rational expression AST with context bindings and no floating logarithms | ISA-8.1; K9 EPS-DECADE | Arbitrary integers/Fraction, exact ceil/division and epsilon decade/log2 witnesses. Decimal input text is preserved for costing. Binary64 conversion is used only for JCS number spelling. |
| EST-05 First native match, inclusive total controls, schemes and native-only template leaves | ISA-8.3 | Native match and non-nesting scheme cost traversal present. Native/template scheme charging, chosen realisations, template schema/scopes and exact epsilon batch allocation are implemented. Full type/lifetime and source validity verification remains `.2`. |
| EST-06 Sum counts, sequential makespan, per-class occupancy and concurrent peak; dirty ownership rates | ISA-8.2 | Composable profiles implement sequential algebra. Mixed-lifetime class total coordinates avoid summing separate peak maxima. Tests exercise sequence, repetition, borrow occupancy and per-class rows. Streaming endpoints implement explicit start times, dependencies, parallel limits, capacity fallback and resolved classes. Default summaries prove capacity from their sequential peak; K58 populations compose through repeats without enumeration. Borrow-pool ownership replacement remains `.2`. |
| EST-07 Realise every classical/effect instruction as a classical leaf, never invented quantum gates | ISA-4.1, ISA-7.3, ISA-7.4, ISA-11.1-P2 | Catalog contains all cc.* recipes; resolved integer arithmetic/branch/call/memory cost interpreter is partial. Cancellation-aware classical uncall and clock effects are implemented; CC/R registers, dynamic widths, aliases, slice/concat, opaque ids, classical-call transfers and source-frame segment reversal are implemented, including raw inverse quantum calls and separately charged reversed classical frames. Deterministic block read/write/image/segment reversal and zero-length entropy are implemented. Minted-token validity follows active history. Proved-clean measurements consume/release aliases, check widths and prohibit segment uncall; unresolved outcomes and positive entropy/host replies stay `.1`. |
| EST-08 Charge all padded B steps and every oracle row, including idle support | ISA-3.6, ISA-5.2-P3, ISA-11.1-P22, ISA-11.1-P29 | Oracle adapter covers signed/unsigned const, binop, div/rem, icmp, select, casts, mov/parmov, label/addr, alloc (four ordered slots), free, location-length boundscheck, call/ret activation, oracle_call/oracle_uncall/perm_call, retval, faultif/fault, qjump/qbranch/qjumpr. Supports unused resolved arguments. Uses published step/commit recipes and B multiplication; tests B=0,1,2,3,2^40. Reading classical pseudo-locations needs EST-SOURCE-01. |
| EST-09 Form layout/state/frames and fixed lproc binding instances in canonical order | ISA-3.7-P5, ISA-3.7-P6, ISA-7.2, K25/K26/K27 | Root layout state is implemented: minimum counter widths, ordinary memory, stack-cell width, pinned table packing, global-image initialisation, locations and compact B frames. Tests prove allocation-order occupancy (one extra image bit adds exactly 302 qubit-seconds in the stated fixture). Fixed binding closure now uses entry argument/region positions, canonical SCC/member/key row order, global location ids, mixed call/return slots and captured instance templates. Recursive instances and nested token forwarding match replay. Remaining memory bindings and EST-SOURCE-01 through 04 require implementation or published decisions. |
| EST-10 Structured memory, predicates, loops and calls preserve full-domain costs | ISA-4.3 through ISA-4.7, K19–K28, K62, K77 | Primitive source adapters, basic controlled action calls and catalog constructor algebra present; trillion-iteration qloop takes constant summary work. A 2^20-cell source lookup uses fewer than 1000 constructor visits; small dispatch summaries equal literal traversal. Action/oracle calls retain token channels and invocation paths; qinplace uses the published private allocation/release sequence. K62 primitive/call source replacements and intrinsic copy/load/oracle-uncall recompute are present. Raw call reversal retains forward ordinals; nested oracle calls use explicit per-call tuples. Complete adjoint and K81 release-ended/call cleanup partitioning remain `.1`/`.2`. |
| EST-11 Consume all 219 published ref recipes without exchanging implementation code | ISA-11.1-P1 through ISA-11.1-P29 | Byte-identical public JSON is vendored and envelope hash checked. Generic constructors are interpreted as cost summaries. K25 record fields are captured/validated even in unvisited arrays; immutable integer/wire records reuse validation only for matching canonical schemas and outer shape bindings. Mutated/incompatible schemas revalidate. Nested inverse scratch identity is checked. Literal and image summaries preserve exact set-bit/class costs. This does not claim each recipe/source binding has an instantiated conformance witness. |
| EST-12 Match schedules verbatim: paths, specificity, ties, per-kind defaults, stages and placements | ISA-11; K55, K63, K64, K65, K80, K81 | Default empty schedule is explicit and hashed. Supported action/oracle paths consume matching nonempty schedules and topology. Selectors resolve independently per kind with ties; decimal-string coordinates and inherited control counts match exact integer values, and large generated coordinates retain lossless keys; K64 support points and inverse-step forward ordinals are tested. K55 known Q-domain ties are checked at admission before target realization; root-token-forwarded nested oracle domains retain concrete-time checks. Default CC/R topology replay reserves all live registers and validates adjacency/scratch/profile equality. CC/R budget propagation, nonempty nested-schedule replay and general K81 cleanup partitioning remain `.2`; potentially applicable unimplemented replay paths report pending instead of silently emitting exact costs. |
| EST-13 Bind complete resolved arguments and each token's own tuple/identity | ISA-10.1/K12; ISA-12.3/K13; K77, K91 | Typed argument range/arity/hash encoding implemented. CLI requires explicit oracle/token budgets and prints explicit invocation; unused i128/f64/token bindings preserve exact values and hashes without adding quantum wires. Additive explicit token_aliases validates canonical partitions and preserves identity through CC/Q calls, fixed bindings, captures, qinplace and reversal. Only oracles prepend a primary token. Read pseudo-location binding remains EST-SOURCE-01. Strict legacy cutover and complete certificate-context adoption remain `.5`. |
| EST-14 Report all scalar resource rows, escaped per-class zero rows, exact fractions and upward decimals | ISA-10.1/K12 | Implemented for supported cost paths. Independent tests cover 1/3, 2/3, terminating values, large/small exponents and percent escaping. Never compare rounded displays for admission. |
| EST-15 Read typed certificate frames, claims and estimate rows; distinguish reading from proof | ISA-9.4, ISA-12.1, ISA-12.2, ISA-12.3/K12/K13 | Reader checks the published controlled-action certificate, nested invocation/claim/domain/table/sampler/structural/interval schemas, verification indices/fault counts, cleanup/error/composition fields, frame expressions/ranges and reduced exact-resource/display rows. Positional control/borrow labels and unbounded legal widths/counts are preserved; producer labels remain requests. Full domain resolution needs the linked object. B5 descriptors reconstruct every streamed lifetime, and root certificate frame widths/classes/states/order are independently cross-checked. Complete nested domain/claim validation and correctness checking remain `.2`. No proof label is inferred from a producer's resource map. |
| EST-16 Bind/rebuild executable estimate certificates, complete frames and contexts | ISA-10.1/K12 certificate binding; ISA-12.1 invocation contexts | K12 resource cross-check entry exists for supported estimates; Streamed root frame and nested invocation records are produced; K12 resource certificate output enriches supplied, identically bound proof metadata and independently rechecks rows/frame. Nested common-context/error composition and independent correctness evidence remain `.2`. CLI is not a complete launch-ABI implementation. |
| EST-17 Differential counts are exact only where a published binary states counts | NorthStar §5.1; ISA-14.1; job rung-2/rung-3 requirement | Five successful paths, three 3-step faults and nested/impure cancellation paths (11/8 forward steps) agree with VM step counts; nested time16 includes five reversed frames. All 86 K82 leaf digests match, and their literal/closed-form cost profiles agree. A native pair action agrees with the VM on 8 gates and time18 (VM total25 less7 classical steps); its action space rows are stated lower bounds across scopes. Ten complete CC programs match every resource row, steps and terminal status (pair, slice/concat, stale-alias fault, block image, disjoint inverses, quantum uncall, nested classical uncall, clean measurement, measurement-uncall fault and private-workspace measurement). Topology forecasts have own spec/profile checks; VM currently rejects the topology target, so that differential is explicitly unavailable. Rung-2 lacks ISA output; `.3` retains full program differentials. No basis execution is a padded estimate. |
| EST-18 Useful Grover estimate at 2^20 rows with honest recovery evidence | NorthStar §8 rung 4(c), §5; ISA-5.7/T6; I2 `b-isa-spec-r51` | Still required. Algebraic repetition scales without gate materialisation. No structure recovery or meaningful whole SQLite/Grover result is claimed from that alone. |
| EST-19 Deterministic JSON CLI, parameterised arithmetic and honest labels | ISA-10.1; job CLI contract | Implemented CLI for current coverage. Exact costs and conditional bounds have separate rational fields and explicit assumptions. Structure-recovered is reserved for checked transformation evidence, not produced yet. |
| EST-20 Gate precisely the pushed SHA in a clean sibling worktree | Job gate contract | The public pinned gate stub and gate.toml select pushed-SHA worktrees plus pinned sibling data/VM builds. Tests validate the manifest/stub and the git-free working-tree entry, including error propagation. Shared protocol tests belong to the public dev tool. Actual clean-SHA invocation and hook-check remain runner-owned. |

## Summary algebra

A profile carries duration t, count vector C, space change d, peak p and
integral a, per class and cleanliness. For sequential profiles x then y:

```
t = tx + ty                       C = Cx + Cy
d = dx + dy                       p = max(px, dx + py)
a = ax + ay + dx * ty
```

Repeating n identical profiles uses `t=n*t0`, `C=n*C0`, `d=n*d0`,
`p=p0+max(0,(n-1)*d0)` and
`a=n*a0+d0*t0*n*(n-1)/2`. A balanced repeated body has d0=0.
Caller interface space is added for the complete invocation duration.
Peak has a combined class coordinate as well as cleanliness coordinates.
This algebra is exact for sequential profiles with the stated allocation and
target decisions. The streaming ledger handles explicit overlap separately from this algebra,
using allocation endpoints and per-wire dependencies without retaining gates.

The §3.7 stack recipes use the same address-popcount summary as §11.1
dispatch, with C physical cells, K-bit stride and only the low N cell bits
participating. The exact literal-X total for addresses 0 through C-1 is
twice their binary digit sum. Balanced literal subprofiles preserve target
scheme workspace area and peak. Tests compare all resource coordinates
against literal expansion and bound summary work for C=2^20. Alias checks
guard the homogeneous-wire proof; unsupported layouts retain traversal. Global
return delivery groups by width/class and exact location-id popcounts, with
validated record arrays and target/control-alias-aware profile caching. Small
mixed-class/inverse/scheme profiles match literal expansion; a32-procedure
source test bounds field validation linearly.

Plain source loops build a finite transition system of immutable wire handles,
shapes and liveness. A repeated complete binding state permits exact repetition
of that cost cycle; prefix and suffix preserve their distinct lifetimes. This
implements visit-local binding carry-over without a gate list or a program
transformation. Tests cover changing local width/class/state, zero visits, 2^40 visits,
iteration coordinates, source adjoints and raw reversal. Carried live names
and types must agree at entry/exit (§4.6); differing carried widths reject.
Legal class changes and qif cross-arm lifetimes preserve each binding. While
forward/source-adjoint/raw-inverse flag orders match replay. The while summary
composes exact flag preparation, prefix/cycle/suffix body costs and unpreparation
in their published order. At 2^40 visits it takes fewer than 1000 constructor
visits; small profiles agree with replay, including scheme workspace and accuracy.

## Contract decisions and scope

The published K12 text settles the previously open hsd/c15 choices. Implement
that text; an open Bead status does not make it permissible to choose different
parameter or decimal semantics. I2 concerns an efficiency construction permitted
by T6; retaining the original row-budget fault boundary remains mandatory.

No source family or north-star capability is removed. Current explicit errors
identify remaining implementation work or the filed source/context decisions in
[CONTRACT_GAPS.md](CONTRACT_GAPS.md). The parameter/implicit-load/return-delivery/jump-width source objects
are accepted by the published VM binary with matching hashes. The source
parameter function returns the expected payload and reference steps for all
four x/a combinations. Exact literal-width alternatives have different peak
and occupancy, so one must not be silently chosen as a published estimate.

Exact text and witnesses are queued for `bennett-isa-spec` in
`.tmp/sol-estimate/cross-repo-beads.md` under COMMON rule 14, with local tracking
`bennett-estimate-bph.4`. The sandbox has read-only access to sibling databases.
The source proposals remain unadopted pending upstream decision. K91 now resolves
EST-CONTEXT-03; local `.5` tracks adoption of its published token equality contract.
SPEC_VERSIONS.toml pins this additive partial feature separately. Explicit
partitions preserve identities and affect schedule hashes without changing
params_hash or object/catalog bytes. Legacy tuple-only behavior retains the base
profile until strict cutover. Source-gap requests retain complete bindings and
no resource rows; independent estimates continue.

K81 independent oracle-call pairs are implemented for flat oracle/permutation-primitive
action bodies with explicit token contexts. Current joint output versions, read/control
versions and token identities determine the source partition before expansion.
Reverse retains written paths; recompute retains caller targets and assigns fresh
T/F compute/XOR/uncompute to the carrier, with separate call indices0/1. Source
adjoints and raw inverses have distinct path behavior. Focused tests check all
resource coordinates, carrier ties before target costs and K63 actual call domains.
Typed decimal-string keys preserve adjacent i128 values and f64 bit patterns.
Inverse-pair certificate token metadata now binds aliases and checks tuple/budget
coverage given declaration order; it establishes no proof or args-domain verdict.
Release-ended chains, action-call prehistory, general source families and window
proofs remain required by EST-10/12; this family does not complete the partition.

The pinned published text includes K82. Typed recipes are closed; the 54
named-interface recipes import only their lexical free wire names. Direct
instantiation requires exactly that map. The catalog bytes and hash are unchanged.

## Round-1 quality floor

The default Cargo suite, coverage.py measurement, weak-test improvements,
independent brute ledger, regenerated literal provenance and byte-identical
phase refactor are documented in [quality.md](quality.md). These checks do not
close the larger source/schedule/proof requirements above. Every test input
and differential VM binary resolves through the gate pins. The ISA gate pin
now contains the additive K86/K91 contracts declared in SPEC_VERSIONS.toml.
