# ISA 0.9 estimator requirements

Contract: SPEC_VERSIONS.toml pins the published ISA document and ref catalog.
This matrix records requirements and verification coverage, not a replacement
task tracker. Durable implementation work is `bennett-estimate-bph` and children.

| Requirement | Published clause IDs / section | Implementation and verification |
|---|---|---|
| EST-01 Read canonical object sections, reject unknown fields, preserve typed metadata | ISA-9.1, ISA-16.1, ISA-16.2 | Partial independent reader; section ordering, duplicate JSON keys, canonical metadata/whitespace and large-number checks. Full opcode/type/link validation remains `.1`. |
| EST-02 Recompute interface/closure/object identities and SCCs | ISA-9.2; corrected layout paths in ISA-9.2-P1 | All ten §16.3 normative examples match every declared interface hash. Reader also handles 0.8 dotted layout paths for rung-3 data. Complete unresolved linking remains `.1`. |
| EST-03 Load target descriptions as data | ISA-8.1, ISA-8.2, ISA-8.3, ISA-8.4 | Tests load every JSON in sibling targets/; no target implementation code imported. Schema/expression checks are partial; concrete topology placement remains `.2`. |
| EST-04 Evaluate rational expression AST with context bindings and no floating logarithms | ISA-8.1; K9 EPS-DECADE | Arbitrary integers/Fraction, exact ceil/division and epsilon decade/log2 witnesses. Decimal input text is preserved for costing. Binary64 conversion is used only for JCS number spelling. |
| EST-05 First native match, inclusive total controls, schemes and native-only template leaves | ISA-8.3 | Native match and non-nesting scheme cost traversal present. Full scheme/schema/type/lifetime validation and scheduled choices remain `.2`; epsilon batch allocation is still required. |
| EST-06 Sum counts, sequential makespan, per-class occupancy and concurrent peak; dirty ownership rates | ISA-8.2 | Composable profiles implement sequential algebra. Mixed-lifetime class total coordinates avoid summing separate peak maxima. Tests exercise sequence, repetition, borrow occupancy and per-class rows. Explicit start times/borrow-pool ownership remain `.2`. |
| EST-07 Realise every classical/effect instruction as a classical leaf, never invented quantum gates | ISA-4.1, ISA-7.3, ISA-7.4, ISA-11.1-P2 | Catalog contains all cc.* recipes; resolved integer arithmetic/branch/call/memory cost interpreter is partial. Register/measurement/history/host-service and exact fault paths remain `.1`. |
| EST-08 Charge all padded B steps and every oracle row, including idle support | ISA-3.6, ISA-5.2-P3, ISA-11.1-P22, ISA-11.1-P29 | Oracle adapter covers const, binop, div/rem, icmp, select, casts, mov/parmov, label/addr, retval, faultif/fault, qjump/qbranch/qjumpr. Supports unused resolved arguments. Uses published step/commit recipes and B multiplication; tests B=0,1,2,3,2^40. Reading classical pseudo-locations needs EST-SOURCE-01. |
| EST-09 Form layout/state/frames and fixed lproc binding instances in canonical order | ISA-3.7-P5, ISA-3.7-P6, ISA-7.2, K25/K26/K27 | Root layout state is implemented: minimum counter widths, ordinary memory, stack-cell width, pinned table packing, global-image initialisation, locations and compact B frames. Tests prove allocation-order occupancy (one extra image bit adds exactly 302 qubit-seconds in the stated fixture). Full memory/activation/fixed-instance binding remains `.1`, with EST-SOURCE-01/02 requiring published decisions. |
| EST-10 Structured memory, predicates, loops and calls preserve full-domain costs | ISA-4.3 through ISA-4.7, K19–K28, K62, K77 | Primitive source adapters, basic controlled action calls and catalog constructor algebra present; trillion-iteration qloop takes constant summary work. A 2^20-cell source lookup uses fewer than 1000 constructor visits; small dispatch summaries equal literal traversal. Complete semantic calls, qinplace, source adjoints and cleanup partition remain `.1`. |
| EST-11 Consume all 219 published ref recipes without exchanging implementation code | ISA-11.1-P1 through ISA-11.1-P29 | Byte-identical public JSON is vendored and envelope hash checked. Generic constructors are interpreted as cost summaries. This does not claim each recipe/source binding has an instantiated conformance witness. |
| EST-12 Match schedules verbatim: paths, specificity, ties, per-kind defaults, stages and placements | ISA-11; K55, K63, K64, K65, K80, K81 | Default empty schedule is explicit and hashed. Matching nonempty schedules/topology fail loudly pending `.2`; they are not silently ignored. Full rational-equivalent selector/binding handling remains required. |
| EST-13 Bind complete resolved arguments and each token's own tuple | ISA-10.1/K12; ISA-12.3/K13; K77 | Typed argument range/arity/hash encoding implemented. CLI prints explicit invocation; unused i128/f64/token bindings preserve exact values and hashes without adding quantum wires. Read pseudo-location binding is a demonstrated contract gap (EST-SOURCE-01); complete nested token channels remain `.1`. |
| EST-14 Report all scalar resource rows, escaped per-class zero rows, exact fractions and upward decimals | ISA-10.1/K12 | Implemented for supported cost paths. Independent tests cover 1/3, 2/3, terminating values, large/small exponents and percent escaping. Never compare rounded displays for admission. |
| EST-15 Read typed certificate frames, claims and estimate rows; distinguish reading from proof | ISA-9.4, ISA-12.1, ISA-12.2, ISA-12.3/K12/K13 | Reader checks the published controlled-action certificate, frame expressions/ranges and reduced exact-resource/display rows. Complete nested domain/claim validation and independent correctness checking remain `.2`. No proof label is inferred from a producer's resource map. |
| EST-16 Bind/rebuild executable estimate certificates, complete frames and contexts | ISA-10.1/K12 certificate binding; ISA-12.1 invocation contexts | K12 resource cross-check entry exists for supported estimates; certificate production, full reconstructed context/frame checks and error composition remain `.2`. CLI is not a complete launch-ABI implementation. |
| EST-17 Differential counts are exact only where a published binary states counts | NorthStar §5.1; ISA-14.1; job rung-2/rung-3 requirement | Five rung-3 resolved classical paths agree exactly with the VM. Rung-2 lacks ISA output; `.3` tracks its admission plus coherent gate-count differentials. No basis execution is a padded estimate. |
| EST-18 Useful Grover estimate at 2^20 rows with honest recovery evidence | NorthStar §8 rung 4(c), §5; ISA-5.7/T6; I2 `b-isa-spec-r51` | Still required. Algebraic repetition scales without gate materialisation. No structure recovery or meaningful whole SQLite/Grover result is claimed from that alone. |
| EST-19 Deterministic JSON CLI, parameterised arithmetic and honest labels | ISA-10.1; job CLI contract | Implemented CLI for current coverage. Exact costs and conditional bounds have separate rational fields and explicit assumptions. Structure-recovered is reserved for checked transformation evidence, not produced yet. |
| EST-20 Gate precisely the pushed SHA in a clean sibling worktree | Job gate contract | Hook reads/deduplicates pushed SHAs, ignores deletions, and executes scripts/check per detached worktree. Orchestration is tested with an explicit VCS double, including failed-check cleanup; no real git process runs in that test. Local working-tree gate contains no git; real clean-SHA invocation belongs to runner. |

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
target decisions. Explicit overlapping schedules need the separate `.2` work.

## Contract decisions and scope

The published K12 text settles the previously open hsd/c15 choices. Implement
that text; an open Bead status does not make it permissible to choose different
parameter or decimal semantics. I2 concerns an efficiency construction permitted
by T6; retaining the original row-budget fault boundary remains mandatory.

No source family or north-star capability is removed. Current explicit errors
identify remaining implementation work or the two source-binding decisions in
[CONTRACT_GAPS.md](CONTRACT_GAPS.md). The parameter/implicit-load source objects
are accepted by the published VM binary with matching hashes. The source
parameter function returns the expected payload and reference steps for all
four x/a combinations. Exact literal-width alternatives have different peak
and occupancy, so one must not be silently chosen as a published estimate.

Exact text and witnesses are queued for `bennett-isa-spec` in
`.tmp/sol-estimate/cross-repo-beads.md` under COMMON rule 14, with local tracking
`bennett-estimate-bph.4`. The sandbox has read-only access to sibling databases.
The proposed policies remain unadopted pending upstream decision.
