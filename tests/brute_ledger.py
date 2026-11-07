"""Small, deliberately enumerating resource oracle derived from ISA circuits.

No imports from the estimator, no Profile composition, no interval sweep,
no digit-sum or repetition formula. Each gate charges currently live storage.
This is test-only and intentionally unsuitable for production-size circuits.
"""
from collections import Counter
from fractions import Fraction


class BruteLedger:
    def __init__(self, cost=lambda op, controls: 1):
        self.cost = cost
        self.live = {}
        self.peak, self.area, self.borrowed_area = Counter(), Counter(), Counter()
        self.time = Fraction(0)
        self.gates = 0

    def allocate(self, name, width, cls="data", borrowed=False):
        assert name not in self.live and width >= 0
        self.live[name] = (width, cls, borrowed)
        for cls in {entry[1] for entry in self.live.values()}:
            self.peak[cls] = max(self.peak[cls], sum(w for w, c, _ in self.live.values() if c == cls))

    def release(self, name):
        del self.live[name]

    def gate(self, op, controls):
        duration = Fraction(self.cost(op, controls))
        assert duration >= 0
        self.time += duration
        self.gates += 1
        for width, cls, borrowed in self.live.values():
            (self.borrowed_area if borrowed else self.area)[cls] += width * duration

    def resources(self):
        # The ideal witness has one class and unit clean/dirty rates.
        return {"time": self.time, "gate_count": self.gates,
                "peak_qubits[data]": self.peak["data"],
                "qubit_second[data]": self.area["data"] + self.borrowed_area["data"]}


def equality(ledger, width, inherited):
    """§4.1 ripple equality: compute prefix, copy answer, undo prefix."""
    ledger.allocate("carry", width + 1)
    ledger.gate("x", inherited)
    for _ in range(width):
        ledger.allocate("difference", 1)
        ledger.gate("cx", inherited + 1); ledger.gate("cx", inherited + 1)
        ledger.allocate("negated", 1)
        ledger.gate("x", inherited); ledger.gate("cx", inherited + 1)
        ledger.allocate("product", 1)
        for op, own in [("ccx", 2), ("cx", 1), ("ccx", 2), ("cx", 1), ("x", 0), ("cx", 1), ("cx", 1)]:
            ledger.gate(op, inherited + own)
        for name in ["product", "negated", "difference"]:
            ledger.release(name)
    ledger.allocate("answer", 1)
    for _ in range(3):
        ledger.gate("cx", inherited + 1)
    ledger.release("answer")
    for _ in reversed(range(width)):
        # Reverse the allocation and gate order of the prefix above. Time
        # does not depend on operand names, but each lifetime still matters.
        for name in ["difference", "negated", "product"]:
            ledger.allocate(name, 1)
        for op, own in [("cx", 1), ("cx", 1), ("x", 0), ("cx", 1), ("ccx", 2), ("cx", 1), ("ccx", 2)]:
            ledger.gate(op, inherited + own)
        ledger.release("product")
        ledger.gate("cx", inherited + 1); ledger.gate("x", inherited)
        ledger.release("negated")
        ledger.gate("cx", inherited + 1); ledger.gate("cx", inherited + 1)
        ledger.release("difference")
    ledger.gate("x", inherited)
    ledger.release("carry")


def dispatch(ledger, address_width, cells, width, inherited=0, exchange=False):
    """§3.7 stack: visit every cell; prepare constant, compare, access, undo."""
    for cell in range(cells):
        ledger.allocate("constant", address_width)
        for bit in range(address_width):
            if cell & (1 << bit):
                ledger.gate("x", inherited)
        ledger.allocate("equal", 1)
        equality(ledger, address_width, inherited)
        for _ in range(width):
            ledger.gate("swap" if exchange else "cx", inherited + (1 if exchange else 2))
        equality(ledger, address_width, inherited)
        ledger.release("equal")
        for bit in reversed(range(address_width)):
            if cell & (1 << bit):
                ledger.gate("x", inherited)
        ledger.release("constant")
