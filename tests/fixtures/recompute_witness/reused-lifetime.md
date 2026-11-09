# Reusing a released source name

The two allocations named `d` are separate source lifetime occurrences.
The first carrier, `entry:3`, owns `entry:2,3` and is bound to allocation
`entry:0`. The second, `entry:7`, owns `entry:6,7` and is bound to
allocation `entry:4`. Each computing sequence is one CX from a read-only
interface input; its input version stays current and its window stays open.

The source and each separately written literal replacement are identity on
all four x/z bases. Both traversal directions release every source and fresh
allocation clean. Renaming the second source allocation changes no effect,
ownership, admissibility or resource total.

The pinned `ideal-quantum-circuit` target describes an ideal quantum circuit with ideal logical qubits, implementing the standard quantum circuit model.
Allocation and release take zero time, each CX
has unit gate count/time, and data occupancy has unit qubit-time rate.
Written reverse uses two gates per lifetime at occupancy three: gates/time
four, peak three, area `2 * (2 * 3) = 12`.

A recomputed lifetime retains its original computing CX at occupancy three,
then fresh-compute/XOR/uncompute emits three CXs at occupancy four. Its
gates/time are four and area is `1 * 3 + 3 * 4 = 15`. Selecting either
carrier alone therefore gives gates/time six, peak four, area `15 + 6 = 21`.
Selecting both gives gates/time eight, peak four, area `15 + 15 = 30`.
Source lifetimes never overlap, and each replacement acquires exactly one
fresh bundle for its bound allocation occurrence.
