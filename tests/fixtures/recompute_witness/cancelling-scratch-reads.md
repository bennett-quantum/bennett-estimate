# Cancelling scratch reads: hand-derived expectations

The source and candidate are the identical program proposed by Sol SOL-1
and Muse B1, with the common computation expanded into separate rows.
Source points start at `entry:0` for allocation. The terminal release at
`entry:7` owns `entry:3,6,7`; the two readers at `entry:4,5` remain once,
in source order, outside that ownership.

For any interface bits `(x,z,y)`, the source computes `d=x XOR z`, then
the owned `cx z d` restores `d=x`. The two retained reads change `y` to
`y XOR x XOR x = y`; the final owned `cx x d` restores `d=0`.
The candidate retains `d=x XOR z` during both reads, so their joint effect
is `y XOR (x XOR z) XOR (x XOR z) = y`. Fresh replay computes
`u=x XOR z`, XORs it into `d` to make `d=0`, then uncomputes `u` to 0.
Both interface maps are therefore identity on all eight bases, with every
release clean: zero differing outputs and zero dirty releases per direction.
All gates are phase-free CXs, so the equality also holds under control and
with external entanglement. Inverse traversal exchanges allocation/release
and reverses self-adjoint CXs, giving the same identity and clean releases.

At `(x,z,y)=(0,1,0)`, the retained readers leave intermediate `y` values
`[0,0]` in the source and `[1,0]` in the candidate. Their individual
in-context effects differ on all four bases with `z=1` but cancel exactly.
This distinguishes composed semantic equality from a per-read requirement.

The gate-pinned `ideal-quantum-circuit` target describes an ideal quantum circuit with ideal logical qubits, implementing the standard quantum circuit model.
With unit gate time and data occupancy rate and zero allocation/release time, four original/retained CXs run with
four live wires and five replay/XOR/uncompute CXs run with five. Thus the
future recompute totals are gates/time 9, peak 5, and qubit-time
`4*4 + 5*5 = 41`, independently of estimator output.
