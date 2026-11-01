"""ISA 0.9 resource arithmetic. Only published contract documents are input.

Profiles compose durations, resource counts and live-space integrals. There is
no circuit, gate list, amplitude vector or chosen quantum input in this module.
"""
import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path

if hasattr(sys,"set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def keys(value, required, optional=(), context="record"):
    require(isinstance(value, dict), f"{context}: expected object")
    require(set(required) <= value.keys(), f"{context}: missing {set(required) - value.keys()}")
    require(value.keys() <= set(required) | set(optional), f"{context}: unknown {value.keys() - set(required) - set(optional)}")


def rational(value):
    require(not isinstance(value, bool), "boolean is not a number")
    require(isinstance(value, (int, Decimal, F, str)), "expected exact rational")
    try:
        return F(value)
    except (ValueError, ZeroDivisionError, OverflowError) as ex:
        raise ContractError(f"invalid rational: {value}") from ex


def integer(value, minimum=None):
    q = rational(value)
    require(q.denominator == 1, f"expected integer, got {value}")
    n = q.numerator
    require(minimum is None or n >= minimum, f"integer below {minimum}: {n}")
    return n


def unsigned(value):
    require(isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value), "K13: expected canonical unsigned decimal string")
    return int(value)


def decimal_up(q):
    q = rational(q)
    require(q >= 0, "K12: negative resource")
    if q == 0:
        return "0"
    def ten(n):
        return F(10**n) if n >= 0 else F(1, 10**-n)
    exponent = len(str(q.numerator)) - len(str(q.denominator))
    if q < ten(exponent):
        exponent -= 1
    scale = exponent - 33
    scaled = q / ten(scale)
    coefficient = -(-scaled.numerator // scaled.denominator)
    if scale >= 0:
        return str(coefficient * 10**scale)
    s = str(coefficient).rjust(-scale + 1, "0")
    return (s[:scale] + "." + s[scale:]).rstrip("0").rstrip(".")


def escape(name):
    allowed = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return "".join(chr(b) if b in allowed else f"%{b:02X}" for b in name.encode("utf-8"))


def _pairs(pairs):
    d = {}
    for key, value in pairs:
        require(key not in d, f"duplicate JSON field {key}")
        d[key] = value
    return d


def loads(text):
    try:
        return json.loads(text, parse_float=Decimal, object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f"nonfinite JSON {x}")))
    except (json.JSONDecodeError, UnicodeError) as ex:
        raise ContractError(f"invalid JSON: {ex}") from ex


def jcs(value):
    """RFC 8785 key order and ECMAScript finite number spelling.

    Decimal values retain their input rational for calculations. Conversion to
    binary64 here is exclusively for checking canonical interchange bytes.
    """
    if value is None: return "null"
    if value is True: return "true"
    if value is False: return "false"
    if isinstance(value, str):
        require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "JCS: lone surrogate")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int): return str(value)
    if isinstance(value, (Decimal, float)):
        f = float(value)
        require(math.isfinite(f), "JCS: number outside binary64")
        if not f: return "0"
        s = repr(f).lower()
        if "e" not in s: return s.removesuffix(".0")
        mantissa, exponent = s.split("e")
        exponent = int(exponent)
        if -6 <= exponent < 21:
            return format(Decimal(s), "f").rstrip("0").rstrip(".") if exponent < 0 else format(Decimal(s), "f")
        return mantissa.removesuffix(".0") + "e" + ("+" if exponent >= 0 else "-") + str(abs(exponent))
    if isinstance(value, list): return "[" + ",".join(jcs(v) for v in value) + "]"
    require(isinstance(value, dict), f"JCS: unsupported {type(value).__name__}")
    return "{" + ",".join(jcs(k) + ":" + jcs(value[k]) for k in sorted(value, key=lambda x: x.encode("utf-16-be"))) + "}"


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def expression(expr, env, tables):
    if isinstance(expr, (int, Decimal, F)) and not isinstance(expr, bool): return rational(expr)
    require(isinstance(expr, dict), "§8.1: invalid expression")
    if "var" in expr:
        keys(expr, ["var"], context="expression")
        require(expr["var"] in env, f"§8.1: unbound variable {expr['var']}")
        return rational(env[expr["var"]])
    if "table" in expr:
        keys(expr, ["table", "index"], context="table expression")
        require(expr["table"] in tables, "§8.1: unknown table")
        if expr["index"] == "k":
            require("k" in env, "§8.1: unbound k")
            index = integer(env["k"], 0)
        else:
            require(expr["index"] == "eps_decade", "§8.1: unknown table index")
            require("eps" in env and 0 < env["eps"] <= 1, "K9: eps outside (0,1]")
            x, index = env["eps"], 0
            while x < 1: x, index = x * 10, index + 1
        require(index < len(tables[expr["table"]]), "§8.1: table index outside array")
        return rational(tables[expr["table"]][index])
    keys(expr, ["op", "args"], context="expression")
    op, args = expr["op"], expr["args"]
    require(op in ["+", "-", "*", "/", "max", "min", "ceil", "log2inv_eps"], "§8.1: unknown operator")
    require(isinstance(args, list) and len(args) == (0 if op == "log2inv_eps" else 1 if op == "ceil" else 2), "§8.1: operator arity")
    if op == "log2inv_eps":
        require("eps" in env and 0 < env["eps"] <= 1, "§8.1: eps outside (0,1]")
        x, j = env["eps"], 0
        while x < 1: x, j = x * 2, j + 1
        return F(j)
    a = expression(args[0], env, tables)
    if op == "ceil": return F(-(-a.numerator // a.denominator))
    b = expression(args[1], env, tables)
    if op == "/":
        require(b != 0, "§8.1: division by zero")
        return a / b
    return {"+": lambda: a+b, "-": lambda: a-b, "*": lambda: a*b,
            "max": lambda: max(a,b), "min": lambda: min(a,b)}[op]()


def add_maps(a, b):
    return {k: a.get(k, 0) + b.get(k, 0) for k in a.keys() | b.keys()}


@dataclass
class Profile:
    time: F = F(0)
    counts: dict = field(default_factory=dict)
    delta: dict = field(default_factory=dict)
    peak: dict = field(default_factory=dict)
    area: dict = field(default_factory=dict)
    gates: dict = field(default_factory=dict)
    error: F = F(0)

    def __post_init__(self):
        self.time = rational(self.time)
        self.error = rational(self.error)

    @staticmethod
    def allocation(cls, state, n):
        key = (cls, state)
        return Profile(delta={key: n}, peak={key: max(n, 0)})

    def then(self, other):
        space = self.delta.keys() | other.delta.keys() | self.peak.keys() | other.peak.keys()
        return Profile(self.time + other.time, add_maps(self.counts, other.counts),
                       add_maps(self.delta, other.delta),
                       {k: max(self.peak.get(k, 0), self.delta.get(k, 0) + other.peak.get(k, 0)) for k in space},
                       {k: self.area.get(k, 0) + other.area.get(k, 0) + self.delta.get(k, 0) * other.time for k in space},
                       add_maps(self.gates, other.gates), self.error + other.error)

    def repeat(self, n):
        n = integer(n, 0)
        if n == 0: return Profile()
        return Profile(self.time*n, {k: v*n for k,v in self.counts.items()},
                       {k: v*n for k,v in self.delta.items()},
                       {k: v + max(0, (n-1)*self.delta.get(k, 0)) for k,v in self.peak.items()},
                       {k: self.area.get(k, 0)*n + v*self.time*n*(n-1)/2 for k,v in self.delta.items()},
                       {k: v*n for k,v in self.gates.items()}, self.error*n)

    def resources(self, target, interface=None):
        interface = interface or {}
        rows = {}
        for name, resource in target.doc["resources"].items():
            kind = resource["kind"]
            if kind in ["count", "time"]:
                rows[escape(name)] = self.time if kind == "time" else self.counts.get(name, F(0))
            else:
                for cls, desc in target.doc["classes"].items():
                    clean = (cls, "clean")
                    dirty = (cls, "borrowed")
                    base = interface.get(cls, 0)
                    if kind == "peak":
                        # Combined clean+borrowed peak is tracked separately in
                        # the class total coordinate, never summed maxima.
                        value = base + self.peak.get((cls, "total"), self.peak.get(clean, 0) + self.peak.get(dirty, 0))
                    else:
                        rate = rational(resource.get("rate", {}).get(cls, 1))
                        value = rate * (base*self.time + self.area.get(clean, 0) + self.area.get(dirty, 0)*rational(desc["dirty_rate"]))
                    rows[escape(name) + "[" + escape(cls) + "]"] = rational(value)
        return dict(sorted(rows.items()))


GATES = {"x": 1, "cx": 2, "ccx": 3, "swap": 2, "cz": 2,
         "h": 1, "s": 1, "sdg": 1, "t": 1, "tdg": 1, "rx": 1, "ry": 1, "rz": 1}
ADJOINT = {"s": "sdg", "sdg": "s", "t": "tdg", "tdg": "t"}


class Target:
    def __init__(self, doc, hash_):
        self.doc, self.hash = doc, hash_

    @classmethod
    def read(cls, text, canonical=True):
        d = loads(text)
        keys(d, ["resources", "classes", "ptr_widths_supported", "gates", "schemes", "qram", "capabilities", "objective", "tables", "imports"], ["topology"], "target")
        require(not canonical or text == jcs(d), "§8.1: target is not RFC 8785 canonical bytes")
        require(d["classes"], "target has no classes")
        for name, r in d["resources"].items():
            keys(r, ["kind", "unit"], ["rate"], "resource")
            require(r["kind"] in ["count", "time", "peak", "occupancy"], "invalid resource kind")
            for c, n in r.get("rate", {}).items():
                require(c in d["classes"] and rational(n) >= 0, "invalid resource class/rate")
        for name, kind in [("time", "time"), ("qubit_second", "occupancy"), ("peak_qubits", "peak")]:
            require(d["resources"].get(name, {}).get("kind") == kind, f"missing mandatory {name}")
        for c in d["classes"].values():
            keys(c, ["qubit_second", "dirty_rate", "capacity"], context="class")
            require(rational(c["qubit_second"]) >= 0 and rational(c["dirty_rate"]) >= 0, "negative class rate")
            if c["capacity"] != "unbounded": integer(c["capacity"], 0)
        for width in d["ptr_widths_supported"]: integer(width, 1)
        caps = d["capabilities"]
        keys(caps, ["measurement", "mbu", "max_parallel", "max_predicate_depth", "classical_step_time"], context="capabilities")
        keys(caps["measurement"], ["mid_circuit", "feedforward_latency"], context="measurement")
        require(caps["mbu"] is False, "§6.4: mbu is reserved false")
        require(isinstance(caps["measurement"]["mid_circuit"], bool), "invalid measurement capability")
        require(rational(caps["classical_step_time"]) >= 0 and rational(caps["measurement"]["feedforward_latency"]) >= 0, "negative latency")
        for k in ["max_parallel", "max_predicate_depth"]:
            if caps[k] != "unbounded": integer(caps[k], 0)
        for name, values in d["tables"].items():
            require(isinstance(values, list), "table must be array")
            for n in values: require(rational(n) >= 0, "negative table value")
        for gate in d["gates"]:
            keys(gate, ["op", "classes", "controls", "epsilon", "cost"], ["params"], "gate")
            require(gate["op"] in GATES or gate["op"] == "mcx", "unknown gate")
            require(gate.get("params", []) == (["theta"] if gate["op"] in ["rx", "ry", "rz"] else []), "gate parameter arity")
            require(gate["classes"] and all(c == "*" or c in d["classes"] for c in gate["classes"]), "unknown gate class")
            keys(gate["controls"], ["min", "max"], context="controls")
            low = integer(gate["controls"]["min"], 0)
            if gate["controls"]["max"] != "unbounded": integer(gate["controls"]["max"], low)
            require("time" in gate["cost"], "gate cost needs time")
            require(set(gate["cost"]) <= d["resources"].keys(), "undeclared resource cost")
            # Expression syntax/bindings are checked even for unreachable entries.
            cls.validate_expr(gate["epsilon"], {"k", "c", "eps"}, d["tables"])
            exact = gate["epsilon"] == 0
            for expr in [gate["epsilon"], *gate["cost"].values()]:
                cls.validate_expr(expr, {"k", "c", "eps"}, d["tables"])
                if exact: require(not cls.epsilon_dependent(expr), "§8.1/K9: exact entry depends on epsilon")
                if not isinstance(expr, dict): require(rational(expr) >= 0, "negative cost/epsilon")
        for scheme in d["schemes"]:
            keys(scheme, ["name", "realises", "ancillae", "template"], context="scheme")
            keys(scheme["realises"], ["op", "controls"], ["params"], "realises")
            keys(scheme["ancillae"], ["count", "state", "class"], context="ancillae")
            require(scheme["ancillae"]["state"] in ["clean", "dirty"] and scheme["ancillae"]["class"] in d["classes"], "invalid ancillae")
            cls.validate_expr(scheme["ancillae"]["count"], {"k", "c"}, d["tables"])
            for leaf in scheme["template"]:
                keys(leaf, ["gate", "wires"], ["params", "repeat"], "scheme leaf")
                if "repeat" in leaf:
                    keys(leaf["repeat"], ["var", "from", "to"], context="repeat")
                    require(leaf["repeat"]["var"] == "i", "invalid repeat variable")
        if "topology" in d:
            top = d["topology"]
            keys(top, ["vertices", "edges"], context="topology")
            for v in top["vertices"]:
                keys(v, ["class"], context="vertex")
                require(v["class"] in d["classes"], "unknown vertex class")
            previous = [-1, -1]
            for edge in top["edges"]:
                require(len(edge) == 2, "invalid edge")
                u, v = (integer(n, 0) for n in edge)
                require(u < v < len(top["vertices"]) and [u,v] > previous, "unsorted/duplicate/invalid topology edge")
                previous = [u,v]
        if d["qram"] is not None:
            keys(d["qram"], ["load", "store", "exch"], context="qram")
            for cost in d["qram"].values():
                keys(cost, ["cost"], context="qram operation")
                require("time" in cost["cost"] and set(cost["cost"]) <= d["resources"].keys(), "invalid qram costs")
                for expr in cost["cost"].values(): cls.validate_expr(expr, {"a", "w", "c"}, d["tables"])
        objective = d["objective"]
        require(set(objective) in [{"weighted"}, {"lexicographic"}], "invalid objective")
        names = objective.get("weighted", objective.get("lexicographic"))
        require(all(n in d["resources"] for n in names), "objective references unknown resource")
        if "weighted" in objective:
            for n in names.values(): require(rational(n) >= 0, "negative objective weight")
        return cls(d, digest(text if canonical else jcs(d)))

    @staticmethod
    def epsilon_dependent(expr):
        if not isinstance(expr, dict): return False
        return expr.get("var") == "eps" or expr.get("op") == "log2inv_eps" or expr.get("index") == "eps_decade" or any(Target.epsilon_dependent(x) for x in expr.get("args", []))

    @staticmethod
    def validate_expr(expr, bound, tables):
        if not isinstance(expr, dict):
            rational(expr)
            return
        if "var" in expr:
            keys(expr, ["var"], context="expression")
            require(expr["var"] in bound, "§8.1: variable outside context")
        elif "table" in expr:
            keys(expr, ["table", "index"], context="expression")
            require(expr["table"] in tables and expr["index"] in ["k", "eps_decade"], "invalid table expression")
            require(("k" if expr["index"] == "k" else "eps") in bound, "unbound table index")
        else:
            keys(expr, ["op", "args"], context="expression")
            op = expr["op"]
            require(op in ["+", "-", "*", "/", "max", "min", "ceil", "log2inv_eps"], "unknown expression op")
            require(len(expr["args"]) == (0 if op == "log2inv_eps" else 1 if op == "ceil" else 2), "invalid expression arity")
            if op == "log2inv_eps": require("eps" in bound, "unbound eps")
            for a in expr["args"]: Target.validate_expr(a, bound, tables)

    def gate(self, op, classes, controls, eps=F(0), own=None, theta=None, native_only=False):
        own = {"cx": 1, "ccx": 2, "mcx": len(classes)-1}.get(op, 0) if own is None else own
        env = {"k": F(own), "c": F(controls), "eps": rational(eps)}
        def covers(entry):
            r = entry["controls"]
            return entry["op"] == op and controls >= r["min"] and (r["max"] == "unbounded" or controls <= r["max"])
        for g in self.doc["gates"]:
            if not covers(g): continue
            pattern = g["classes"]
            if not (len(pattern) == 1 and all(pattern[0] in ["*", c] for c in classes) or len(pattern) == len(classes) and all(p in ["*", c] for p,c in zip(pattern, classes))): continue
            achieved = expression(g["epsilon"], env, self.doc["tables"])
            require(achieved >= 0, "negative achieved epsilon")
            if achieved > eps: continue
            costs = {n: expression(x, env, self.doc["tables"]) for n,x in g["cost"].items()}
            require(all(v >= 0 for v in costs.values()), "§8.1: negative evaluated cost")
            return Profile(time=costs["time"], counts={n:v for n,v in costs.items() if self.doc["resources"][n]["kind"] == "count"}, gates={op: 1}, error=achieved)
        require(not native_only, f"§8.3: scheme leaf {op} has no native match")
        for s in self.doc["schemes"]:
            if not covers(s["realises"]): continue
            anc = s["ancillae"]
            n = integer(expression(anc["count"], env, self.doc["tables"]), 0)
            state = "borrowed" if anc["state"] == "dirty" else "clean"
            out = space_profile(anc["class"], state, n)
            for leaf in s["template"]:
                repeat = leaf.get("repeat")
                lo, hi = (integer(expression(repeat[k], env, self.doc["tables"]), 0) for k in ["from", "to"]) if repeat else (0,1)
                for i in range(lo, hi):
                    context = dict(env, i=F(i))
                    wire_classes = []
                    for w in leaf["wires"]:
                        if w in ["t", "t2"]:
                            target_index=controls+(0 if w=="t" else 1)
                            require(target_index<len(classes),"scheme references absent t2")
                            wire_classes.append(classes[target_index])
                        else:
                            match = re.fullmatch(r"([ca])\[(.*)\]", w)
                            require(match, "invalid template wire")
                            index = integer(expression(loads(match[2]), context, self.doc["tables"]), 0)
                            require(index < (n if match[1] == "a" else controls), "scheme wire outside bundle")
                            wire_classes.append(anc["class"] if match[1] == "a" else classes[index])
                    leaf_op = leaf["gate"]
                    c = {"cx":1, "ccx":2, "mcx":len(wire_classes)-1}.get(leaf_op,0)
                    out = out.then(self.gate(leaf_op, wire_classes, c, eps, native_only=True))
            return out.then(space_profile(anc["class"], state, -n))
        raise ContractError(f"E_GATE_UNSUPPORTED: {op}, c={controls}, classes={classes}, eps={eps}")


def space_profile(cls, state, n):
    p = Profile.allocation(cls, state, n)
    p.delta[(cls, "total")] = n
    p.peak[(cls, "total")] = max(n, 0)
    return p


@dataclass(frozen=True)
class Bundle:
    identity: str
    width: int
    cls: str
    offset: int = 0
    state: str = "clean"

    def bit(self, index):
        require(0 <= index < self.width, f"wire index {index} outside {self.identity}[{self.width}]")
        return Bundle(self.identity, 1, self.cls, self.offset + index, self.state)


@dataclass
class Captured:
    body: list
    env: dict
    controls: tuple


@lru_cache(maxsize=2)
def catalog_document(text):
    return loads(text)


@lru_cache(maxsize=2)
def catalog_identity(text):
    require(jcs(catalog_document(text)) == text,"noncanonical expansion library")
    return digest("isa=0.9\nexpansion=ref\nversion=0.9\n"+text+"\n")


def scalar(x, env):
    if isinstance(x, int): return x
    if isinstance(x, str):
        require(x in env and isinstance(env[x], int), f"K19: unbound integer {x}")
        return env[x]
    require(isinstance(x, list) and x, "K19: invalid scalar")
    op, *args = x
    require(op in ["+", "-", "*", "div", "mod", "bit"] and len(args) == 2, "K19: scalar opcode/arity")
    a, b = [scalar(a, env) for a in args]
    if op in ["div", "mod"]: require(b > 0, "K19: nonpositive divisor")
    if op == "bit":
        require(a >= 0 and b >= 0, "K23: negative bit operand")
        return (a >> b) & 1
    return {"+":lambda:a+b, "-":lambda:a-b, "*":lambda:a*b, "div":lambda:a//b, "mod":lambda:a%b}[op]()


def wire(x, env):
    if isinstance(x, Bundle): return [x]
    if isinstance(x, list): return [w for part in x for w in wire(part, env)]
    if isinstance(x, dict):
        if set(x) == {"range", "from", "to"}:
            bundle = wire(x["range"], env)
            require(len(bundle) == 1, "K19: range needs one contiguous bundle")
            b = bundle[0]
            lo, hi = scalar(x["from"], env), scalar(x["to"], env)
            require(0 <= lo <= hi <= b.width, "K19: invalid wire range")
            return [Bundle(b.identity, hi-lo, b.cls, b.offset+lo, b.state)]
        if "cells" in x: return wire(x["cells"], env)
    require(isinstance(x, str), "K19: invalid wire actual")
    match = re.fullmatch(r"([^\[]+)\[(.*)\]", x)
    if match:
        b = wire(match[1], env)
        index = scalar(loads(match[2]), env)
        require(index >= 0, "negative wire index")
        for part in b:
            if index < part.width: return [part.bit(index)]
            index -= part.width
        raise ContractError(f"wire subscript outside {x}")
    require(x in env, f"K19: unbound wire {x}")
    value = env[x]
    if isinstance(value, dict) and "storage" in value: value = value["storage"]
    return wire(value, env)


def bits(wires):
    # Used only for gate operands/control sets, never for a storage-sized bundle.
    return tuple((b.identity, b.offset+i, b.cls) for b in wires for i in range(b.width))


class Catalog:
    def __init__(self, text, target):
        doc = catalog_document(text)
        keys(doc, ["isa", "name", "version", "recipes"], context="library")
        require(doc["isa"] == doc["version"] == "0.9" and doc["name"] == "ref", "unsupported expansion library")
        self.hash = catalog_identity(text)
        require(self.hash == "5de4e4995350313e50217880ba1b95de39cd043283b726337d4894efb005d197", "published ref@0.9 identity mismatch")
        self.recipes = {r["kind"]: r for r in doc["recipes"]}
        require(len(self.recipes) == 219, "incomplete expansion catalog")
        self.target, self.visits, self.serial = target, 0, 0
        self.stack = []
        self.symbols = {}
        self.eps = F(0)
        self.closed_form = True
        self.default_class = next(iter(sorted(target.doc["classes"])))

    def bind(self, formals, actuals, caller, controls):
        require(len(formals) == len(actuals), "K19: recipe argument arity")
        env = dict(caller)
        seen = set()
        for formal, actual in zip(formals, actuals):
            name = formal if isinstance(formal, str) else formal["name"]
            require(name not in seen, "duplicate formal")
            seen.add(name)
            kind = "integer" if isinstance(formal, str) else formal["type"]
            if kind == "integer": value = scalar(actual, caller)
            elif kind in ["wire", "environment"]:
                value = wire(actual, caller)
                if kind == "wire": require(sum(b.width for b in value) == scalar(formal["width"], env), "K19: wire width mismatch")
                else: controls = tuple(dict.fromkeys(controls + bits(value)))
            elif kind == "body":
                value = caller[actual] if isinstance(actual, str) else Captured(actual, dict(caller), controls)
                require(isinstance(value, Captured), "invalid captured body")
            elif kind == "templates":
                value = caller[actual] if isinstance(actual, str) else [(a, dict(caller), controls) for a in actual]
                require(len(value) == scalar(formal["length"], env), "K22: template length mismatch")
            elif kind in ["angle", "image", "symbol", "class", "event", "records", "allocation", "value", "arguments", "region"]:
                value = caller.get(actual, actual) if isinstance(actual, str) else actual
                if kind == "allocation": require(isinstance(value, Bundle), "K27: invalid allocation handle")
                if kind == "image": require(isinstance(value, str) and re.fullmatch(r"(?:[0-9a-f]{2})*", value), "K21: invalid image")
                if kind == "angle": require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-f]{16}", value) and (int(value[2:],16)>>52)&2047 != 2047, "K20: invalid angle")
                if kind == "region":
                    require(isinstance(value, dict), "K26: invalid region")
                    keys(value, ["address", "cell", "role", "origin", "cells"], context="region actual")
                    require(value["address"] == scalar(formal["address"],env) and value["cell"] == scalar(formal["cell"],env) and value["role"] == formal["role"], "K26: region shape/role mismatch")
                    require(value["origin"].startswith(("local:","interface:")) and value["origin"].split(":",1)[1], "K26: invalid origin")
                    require(sum(b.width for b in wire(value["cells"], caller)) == (1 << value["address"])*value["cell"], "K26: cells width mismatch")
            else: raise ContractError(f"unknown formal type {kind}")
            env[name] = value
        return env, controls

    def recipe(self, name, args, env=None, controls=(), inverse=False):
        require(name in self.recipes, f"unknown reference recipe {name}")
        # The pinned recipe dependency graph is acyclic. A finite captured
        # body may invoke the same higher-order recipe again (K19), e.g.
        # qloop(7,qloop(3,B)); recipe-name re-entry alone is not recursion.
        self.stack.append(name)
        try:
            r = self.recipes[name]
            bound, controls = self.bind(r["parameters"], args, env or {}, controls)
            if self.closed_form and name in ["dispatch.copy","dispatch.store","dispatch.exchange"] and not self.target.doc.get("topology"):
                p=self.dispatch_summary(name,bound,controls)
                if p is not None: return p
            return self.body(r["body"], bound, controls, inverse)
        finally:
            self.stack.pop()

    def dispatch_summary(self,name,env,controls):
        A,C,W=env["A"],env["C"],env["W"]
        require(0<=C<=1<<A and W>0,"invalid address dispatch shape")
        cells=wire(env["cells"],env)
        if len(cells)!=1: return None
        if C==0: return Profile()
        # Literal equality inputs vary by address; their total X count has an
        # exact binary digit sum. The comparator and each cell operation are
        # invariant under renaming homogeneous cell wires.
        self.serial+=1
        counter=Bundle(f"dispatch:{self.serial}:counter",A,self.default_class)
        eq=Bundle(f"dispatch:{self.serial}:eq",1,self.default_class)
        compare=self.recipe("bind.value.icmp.eq",[A,env["a"],counter,eq],env,controls)
        value=wire(env["v"],env)
        if len(value)!=1: return None
        leaf="swap" if name=="dispatch.exchange" else "cx"
        joined=tuple(dict.fromkeys(controls+bits([eq])))
        cell=cells[0]
        ws=[value[0].bit(0),cell.bit(0)] if name=="dispatch.store" else [cell.bit(0),value[0].bit(0)]
        data=self.body([{"gate":leaf,"wires":ws}],env,joined).repeat(W)
        base=space_profile(counter.cls,"clean",A).then(space_profile(eq.cls,"clean",1)).then(compare).then(data).then(compare).then(space_profile(eq.cls,"clean",-1)).then(space_profile(counter.cls,"clean",-A))
        p=base.repeat(C)
        ones=sum((C>>(b+1))*(1<<b)+max(0,C% (1<<(b+1))-(1<<b)) for b in range(A))
        literals=self.target.gate("x",[w[2] for w in controls]+[counter.cls],len(controls),self.eps,own=0).repeat(2*ones)
        p.time+=literals.time
        p.counts=add_maps(p.counts,literals.counts)
        p.gates=add_maps(p.gates,literals.gates)
        p.error+=literals.error
        p.area[(counter.cls,"clean")]=p.area.get((counter.cls,"clean"),0)+A*literals.time
        p.area[(counter.cls,"total")]=p.area.get((counter.cls,"total"),0)+A*literals.time
        return p

    @staticmethod
    def invariant(nodes, variable):
        # Index-only changes on homogeneous bundles leave the cost profile
        # invariant. Scalar occurrences (including invoke arguments) do not.
        def visit(x, in_wire=False):
            if isinstance(x, str):
                return in_wire or x != variable and variable not in re.findall(r'"([^" ]+)"', x)
            if isinstance(x, list): return all(visit(v, in_wire) for v in x)
            if isinstance(x, dict):
                return all(visit(v, k in ["wires", "under"]) for k,v in x.items())
            return True
        return visit(nodes)

    def safe_index_fold(self,nodes,variable,lo,hi,env,controls):
        """Prove index renaming preserves arity, classes and control counts.

        Endpoint observations alone are insufficient: two affine indices can
        coincide only in the middle of a loop. Non-affine cases stay literal.
        """
        def affine(expr):
            if isinstance(expr,int): return 0,expr
            if isinstance(expr,str):
                if expr==variable: return 1,0
                if expr in env and isinstance(env[expr],int): return 0,env[expr]
                raise ValueError("unknown affine parameter")
            op,*args=expr
            if len(args)!=2: raise ValueError("arity")
            a,b=affine(args[0]),affine(args[1])
            if op=="+": return a[0]+b[0],a[1]+b[1]
            if op=="-": return a[0]-b[0],a[1]-b[1]
            if op=="*" and not a[0]: return b[0]*a[1],b[1]*a[1]
            if op=="*" and not b[0]: return a[0]*b[1],a[1]*b[1]
            if a[0]==b[0]==0: return 0,scalar(expr,env)
            raise ValueError("non-affine index")
        def mentions(x):
            if isinstance(x,str): return x==variable or '"'+variable+'"' in x
            if isinstance(x,list): return any(mentions(v) for v in x)
            if isinstance(x,dict): return any(mentions(v) for v in x.values())
            return False
        control_ids={c[0] for c in controls}
        def descriptors(actual):
            if isinstance(actual,list): return [v for a in actual for v in descriptors(a)]
            if isinstance(actual,Bundle):
                if actual.width!=1: raise ValueError("bundle operand")
                return [(actual.identity,0,actual.offset)]
            if not isinstance(actual,str): raise ValueError("complex wire")
            m=re.fullmatch(r"([^\[]+)\[(.*)\]",actual)
            if not m:
                bundles=wire(actual,env)
                if sum(b.width for b in bundles)>3: raise ValueError("wide control bundle")
                return [(b.identity,0,b.offset+i) for b in bundles for i in range(b.width)]
            coefficient,constant=affine(loads(m[2]))
            if m[1] not in env:
                if coefficient: raise ValueError("local indexed width")
                return [("local:"+m[1],0,constant)]
            bundles=wire(m[1],env)
            if len(bundles)!=1: raise ValueError("nonhomogeneous bundle")
            b=bundles[0]
            low,high=sorted([coefficient*lo+constant,coefficient*(hi-1)+constant])
            if not 0<=low<=high<b.width: raise ValueError("index range")
            if coefficient and b.identity in control_ids: raise ValueError("control intersection varies")
            return [(b.identity,coefficient,constant+b.offset)]
        def visit(x):
            if isinstance(x,list): return all(visit(n) for n in x)
            if not isinstance(x,dict): return True
            if "under" in x and mentions(x): return False
            if "gate" in x:
                if not mentions(x["wires"]): return True
                ds=descriptors(x["wires"])
                for i,(identity,a,b) in enumerate(ds):
                    for other,c,d in ds[:i]:
                        if identity!=other: continue
                        if a==c:
                            if b==d: return False
                        else:
                            root=F(d-b,a-c)
                            if root.denominator==1 and lo<=root<hi: return False
            return all(visit(v) for k,v in x.items() if k!="wires")
        try:
            return visit(nodes)
        except (ValueError,TypeError,KeyError,ContractError):
            return False

    def body(self, nodes, env, controls=(), inverse=False):
        require(isinstance(nodes, list), "K19: constructor body must be array")
        env = dict(env)
        # Declarations must also be available during inverse traversal. No wire
        # arrays are allocated: each bundle is one interval descriptor.
        for node in nodes:
            if "alloc" in node:
                n = integer(scalar(node["width"], env), 0)
                cls = node["class"]
                if isinstance(cls, dict): cls = cls["class"]
                if cls == "any": cls = self.default_class
                require(cls in self.target.doc["classes"], "unknown allocation class")
                self.serial += 1
                env[node["alloc"]] = Bundle(f"{self.serial}:{node['alloc']}", n, cls, state="borrowed" if node["state"] in ["dirty","borrowed"] else "clean")
        out = Profile()
        for node in reversed(nodes) if inverse else nodes:
            self.visits += 1
            require(isinstance(node, dict), "invalid constructor")
            if "gate" in node:
                keys(node, ["gate", "wires"], ["params"], "gate constructor")
                op = ADJOINT.get(node["gate"], node["gate"]) if inverse else node["gate"]
                operands = bits(wire(node["wires"], env))
                require(len(operands) == len(set(operands)), "K19: coincident gate operands")
                require(op in GATES and len(operands) == GATES[op] or op == "mcx" and len(operands) >= 1, "K19: gate arity/opcode")
                own = {"cx": 1, "ccx": 2, "mcx": len(operands)-1}.get(op, 0)
                require(not set(operands[own:]) & set(controls), "K19: effective control is a target")
                effective = tuple(dict.fromkeys(operands[:own] + controls))
                classes = [w[2] for w in effective + operands[own:]]
                p = self.target.gate(op, classes, len(effective), self.eps, own=own)
            elif "alloc" in node or "release" in node or "acquire" in node or "relinquish" in node:
                key = next(k for k in ["alloc", "release", "acquire", "relinquish"] if k in node)
                if key == "alloc": keys(node, ["alloc", "width", "class", "state"], context="allocation")
                else: keys(node, [key], context=key)
                b = env.get(node[key])
                require(isinstance(b, Bundle), f"K27: missing allocation {node[key]}")
                sign = 1 if key in ["alloc", "acquire"] else -1
                p = space_profile(b.cls, b.state, b.width * (-sign if inverse else sign))
            elif "for" in node:
                keys(node, ["for", "from", "to", "body"], context="loop")
                lo, hi = scalar(node["from"], env), scalar(node["to"], env)
                require(hi >= lo, "K19: reversed loop bounds")
                if lo == hi: p = Profile()
                elif self.invariant(node["body"], node["for"]) and self.safe_index_fold(node["body"],node["for"],lo,hi,env,controls) and not self.target.doc.get("topology") and all(not isinstance(v,list) or not v or not isinstance(v[0],Bundle) or len({b.cls for b in v}) == 1 for v in env.values()):
                    bound = dict(env, **{node["for"]: lo})
                    p = self.body(node["body"], bound, controls, inverse).repeat(hi-lo)
                else:
                    p = Profile()
                    for i in range(hi-1,lo-1,-1) if inverse else range(lo,hi):
                        p = p.then(self.body(node["body"], dict(env, **{node["for"]: i}), controls, inverse))
            elif "inverse" in node:
                keys(node, ["inverse", "body"], context="inverse")
                require(node["inverse"] is True, "invalid inverse")
                p = self.body(node["body"], env, controls, not inverse)
            elif "under" in node:
                keys(node, ["under", "body"], context="under")
                joined = tuple(dict.fromkeys(controls + bits(wire(node["under"], env))))
                p = self.body(node["body"], env, joined, inverse)
            elif "invoke" in node:
                keys(node, ["invoke", "args"], context="invoke")
                p = self.recipe(node["invoke"], node["args"], env, controls, inverse)
            elif "splice" in node:
                keys(node, ["splice"], context="splice")
                captured = env[node["splice"]]
                require(isinstance(captured, Captured), "unbound body")
                joined = tuple(dict.fromkeys(controls + captured.controls))
                p = self.body(captured.body, captured.env, joined, inverse)
            elif "image" in node:
                keys(node, ["image", "wires"], context="image")
                image = env.get(node["image"], node["image"])
                require(isinstance(image,str) and re.fullmatch(r"(?:[0-9a-f]{2})*",image), "K21: malformed image")
                bundle = wire(node["wires"], env)
                require(not image or sum(b.width for b in bundle) == len(image)*4, "K21: image width mismatch")
                p = Profile()
                offset = 0
                for byte in bytes.fromhex(image):
                    for i in range(8):
                        if byte & (1 << i):
                            cursor = offset+i
                            for b in bundle:
                                if cursor < b.width:
                                    p = p.then(self.target.gate("x", [b.cls], 0, self.eps))
                                    break
                                cursor -= b.width
                    offset += 8
            elif "declare" in node:
                keys(node, ["declare", "width", "class", "state", "body"], context="declare")
                cls = env.get(node["class"], node["class"]) if isinstance(node["class"],str) else node["class"]
                cls = cls.get("class") if isinstance(cls,dict) else cls
                if cls == "any": cls = self.default_class
                self.serial += 1
                b = Bundle(str(self.serial), integer(scalar(node["width"], env),0), cls, state=node["state"])
                p = self.body(node["body"], dict(env, **{node["declare"]: b}), controls, inverse)
                require(all(v == 0 for v in p.delta.values()), "K27: live declaration at scope exit")
            elif "visit" in node:
                keys(node, ["visit", "body"], context="visit")
                p = Profile()
                records = env[node["visit"]]
                for record in reversed(records) if inverse else records:
                    p = p.then(self.body(node["body"], dict(env, **record), controls, inverse))
            elif "apply" in node:
                keys(node, ["apply", "index", "args"], context="apply")
                templates = env[node["apply"]]
                index = scalar(node["index"], env)
                require(0 <= index < len(templates), "K22: template index outside array")
                template, captured_env, captured_controls = templates[index]
                bound, joined = self.bind(template["parameters"], node["args"], env, tuple(dict.fromkeys(controls+captured_controls)))
                bound = dict(captured_env, **{(f if isinstance(f,str) else f["name"]): bound[f if isinstance(f,str) else f["name"]] for f in template["parameters"]})
                p = self.body(template["body"], bound, joined, inverse)
            elif "classical" in node:
                keys(node, ["classical", "point"], context="classical event")
                p = Profile(time=rational(self.target.doc["capabilities"]["classical_step_time"]))
            elif "call" in node:
                keys(node, ["call", "args"], context="semantic call")
                symbol = env.get(node["call"], node["call"])
                require(symbol in self.symbols, "K19: unbound closure hash")
                callee = self.symbols[symbol]
                actuals = env[node["args"]] if isinstance(node["args"],str) else node["args"]
                bound, joined = self.bind(callee["parameters"], actuals, env, controls)
                p = self.body(callee["body"], bound, joined, inverse)
            elif "each" in node:
                keys(node, ["each", "in", "body"], context="each")
                p = Profile()
                bundles=wire(node["in"],env)
                for b in reversed(bundles) if inverse else bundles:
                    for i in range(b.width-1,-1,-1) if inverse else range(b.width):
                        p=p.then(self.body(node["body"],dict(env,**{node["each"]:b.bit(i)}),controls,inverse))
            else:
                raise ContractError(f"K19: unknown constructor {list(node)}")
            out = out.then(p)
        return out


NAME = r"[A-Za-z_][A-Za-z0-9_.]*"
SECTIONS = ["symbols", "imports", "functions", "data", "devices", "layout", "schedule", "certificate", "coverage"]


def parameters(text):
    out = []
    for part in text.split(", ") if text else []:
        m = re.fullmatch(f"({NAME}):([^ ]+)(?: (in|mut|token|classical))?", part)
        require(m, f"§16.2: invalid parameter {part}")
        out.append((m[1], m[2], m[3]))
    return out


def type_width(ty, ptr=32):
    if ty == "ptr": return ptr
    if ty == "f64": return 64
    if ty == "wire": return 1
    if re.fullmatch(r"i[1-9][0-9]*", ty): return int(ty[1:])
    m = re.fullmatch(r"(?:wire|reg|qreg)\[([1-9][0-9]*)\]", ty)
    if m: return int(m[1])
    m = re.fullmatch(r"region\[(0|[1-9][0-9]*),([1-9][0-9]*)\]", ty)
    if m: return (1 << int(m[1]))*int(m[2])
    raise ContractError(f"unknown/static-width type {ty}")


def operands(text):
    return re.findall(r"\([^)]*\)|\^[^ (]+\([^)]*\)|[^ ]+", text)


def list_operand(text):
    require(text.startswith("(") and text.endswith(")"), "expected operand list")
    return text[1:-1].split(", ") if text != "()" else []


def known_opcode(op):
    binary={"add","sub","mul","and","or","xor","shl","lshr","ashr","udiv","urem","sdiv","srem"}
    predicates={"icmp."+p for p in ["eq","ne","ult","ule","slt","sle"]}
    classical={"alloc","free","select","inttoptr","br","call","uncall","ret","trap","fault","effect","hostcall","budget.mint","measure"}
    registers={"qreg."+p for p in ["new","free","slice","concat","width","id","from_id"]}
    action={"qalloc","qborrow","qfree","qreturn","qcopy","quncopy","qxor","qexch","qinplace","qregion","qload","qunload","qstore","qexchm","qpred","qunpred","qif","qloop","oracle_call","action_call","adj","ctl","mcx"}
    lifted={"lift."+p for p in binary|predicates|{"select","mov","parmov","label","addr","boundscheck","alloc","free","faultif","call","ret","retval","oracle_call","oracle_uncall","perm_call"}}
    return op in binary|predicates|classical|registers|action|lifted|GATES.keys()|{"qjump","qbranch","qjumpr"} or bool(re.fullmatch(r"(?:lift\.)?(?:const|zext|sext|trunc|load|store)\.i[1-9][0-9]*",op)) or bool(re.fullmatch(r"(?:ptrtoint|measure)\.i[1-9][0-9]*",op))


@dataclass
class Instruction:
    op: str
    args: list
    lhs: list
    body: list = field(default_factory=list)
    otherwise: list = field(default_factory=list)
    block: str = ""
    ordinal: int = 0


@dataclass
class Function:
    name: str
    kind: str
    groups: list
    raw: str
    blocks: dict
    regs: list
    code: list


def parse_function(lines):
    m = re.fullmatch(f"(fn cc|fn r|oracle|action|perm_action|lproc) @({NAME}) " + r"\((.*?)\) \((.*?)\) \((.*?)\) \((.*?)\) \((.*?)\)", lines[0])
    require(m, "§16.2: malformed function header")
    kind, name = m[1].removeprefix("fn "), m[2]
    groups = [parameters(m[i]) for i in range(3,8)]
    regs, blocks, root = [], {}, []
    stack, current, ordinal = [], root, 0
    block = None
    for line in lines[1:]:
        if line.startswith("regs "):
            reg_match = re.fullmatch(r"regs \{ (.*?) \}(?: bounds \{[^}]*\})?", line)
            require(reg_match, "invalid regs declaration")
            regs = parameters(reg_match[1])
        elif line.startswith("^"):
            require(not stack, "block inside structured scope")
            b = re.fullmatch(rf"\^({NAME})"+r"\((.*?)\):", line)
            require(b and b[1] not in blocks, "invalid/duplicate block")
            block, ordinal = b[1], 0
            blocks[block] = (parameters(b[2]), [])
            current = blocks[block][1]
        elif line == "} {":
            require(stack, "unmatched else")
            current = stack[-1][1].otherwise
        elif line == "}":
            require(stack, "unmatched scope end")
            current, _ = stack.pop()
        else:
            require(block is not None, "instruction outside block")
            scoped = line.endswith(" {")
            text = line[:-2] if scoped else line
            lhs, text = text.split(" = ", 1) if " = " in text else ("", text)
            tok = operands(text)
            require(tok, "empty instruction")
            require(known_opcode(tok[0]),f"§4.8: unknown opcode {tok[0]}")
            inst = Instruction(tok[0], tok[1:], list_operand(lhs) if lhs.startswith("(") else [lhs] if lhs else [], block=block, ordinal=ordinal)
            current.append(inst)
            root.append(inst)
            ordinal += 1
            if scoped:
                stack.append((current, inst))
                current = inst.body
    require(not stack and blocks, "unclosed scope or no blocks")
    return Function(name, kind, groups, "\n".join(lines), blocks, regs, root)


def check_metadata_numbers(value):
    if isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        require(abs(value) < 2**53, "§9.1: metadata JSON number >=2^53; use decimal string")
    if isinstance(value, dict):
        for v in value.values(): check_metadata_numbers(v)
    if isinstance(value, list):
        for v in value: check_metadata_numbers(v)


class Object:
    @classmethod
    def read(cls, text):
        require("\r" not in text and text.endswith("\n"), "§16.1: object needs LF line endings and final LF")
        chunks = text[:-1].split("\n\n")
        header = re.fullmatch(r"bennett-object isa=(\d+\.\d+) object=(\d+\.\d+) launch=(\d+\.\d+) sched=(\d+\.\d+) cert=(\d+\.\d+) coverage=(\d+\.\d+) target=(\d+\.\d+) ptr_width=(0|[1-9][0-9]*)", chunks[0])
        require(header, "§16.2: malformed object header")
        versions = dict(zip(["isa","object","launch","sched","cert","coverage","target"], header.groups()[:7]))
        require(len(set(versions.values())) == 1 and versions["isa"] in ["0.8","0.9"], "unsupported/mixed object versions")
        out = cls()
        out.versions, out.ptr, out.text = versions, int(header[8]), text
        require(out.ptr > 0, "invalid pointer width")
        out.sections, out.functions = {}, {}
        last = -1
        base = [chunks[0]]
        for chunk in chunks[1:]:
            lines = chunk.split("\n")
            require(lines[0].startswith("section "), "§16.1: unexpected blank line")
            name = lines[0][8:]
            require(name in SECTIONS and SECTIONS.index(name) > last, "§9.1: unknown/duplicate/out-of-order section")
            last = SECTIONS.index(name)
            body = lines[1:]
            if name not in ["functions", "data"]:
                require(len(body) == 1, f"§9.1: {name} needs one JCS line")
                d = loads(body[0])
                require(isinstance(d,dict) and jcs(d) == body[0], f"§9.1: {name} is not a JCS object")
                check_metadata_numbers(d)
                out.sections[name] = d
            elif name == "data":
                data = {}
                for line in body:
                    m = re.fullmatch(f"({NAME}) ([0-9a-f]{{2}})*", line)
                    require(m, "§9.1: invalid data line")
                    n, image = line.split(" ")
                    require(n not in data, "duplicate data symbol")
                    data[n] = image
                out.sections[name] = data
            else:
                starts = [i for i,l in enumerate(body) if re.match(r"(?:fn (?:cc|r)|oracle|action|perm_action|lproc) @",l)] + [len(body)]
                require(starts[0] == 0, "malformed functions section")
                for lo,hi in zip(starts, starts[1:]):
                    fn_lines = body[lo:hi]
                    for line in fn_lines:
                        require(line == line.rstrip() and ("  " not in line.replace("regs {  }", "regs { }")), "§16.1: noncanonical instruction whitespace")
                    fn = parse_function(fn_lines)
                    require(fn.name not in out.functions, "duplicate function")
                    out.functions[fn.name] = fn
                out.sections[name] = body
            if name not in ["schedule", "certificate", "coverage"]: base.append(chunk)
        out.hash = digest("\n\n".join(base)+"\n")
        require("symbols" in out.sections, "missing symbols")
        symbols = out.sections["symbols"]
        for index, symbol in symbols.items():
            require(re.fullmatch(r"0|[1-9][0-9]*", index), "invalid symbol index")
            keys(symbol, ["name", "kind", "signature", "interface_hash"], context="symbol")
            require(re.fullmatch(r"[0-9a-f]{64}",symbol["interface_hash"]), "invalid interface hash")
            sig = symbol["signature"]
            kind = symbol["kind"]
            required = {"cc":["params","results"],"r":["params","results"],"oracle":["in","tgt","fault","mem","args"],"action":["mut","in","mem","args","bounds"],"perm_action":["mut","in","mem","args","bounds"],"lproc":["params","result","tokens","args","mem"],"data":["size"]}
            require(kind in required, "unknown symbol kind")
            keys(sig, ["tier","kind","abi",*required[kind]], context="signature")
            require(sig["kind"] == kind and sig["abi"] == versions["isa"], "signature version/kind mismatch")
            if kind != "data":
                require(symbol["name"] in out.functions and out.functions[symbol["name"]].kind == kind, "symbol/header mismatch")
                fn=out.functions[symbol["name"]];g=fn.groups
                def widths(group): return [type_width(ty,out.ptr) for n,ty,role in group]
                def mem(group):
                    result=[]
                    for n,ty,role in group:
                        m=re.fullmatch(r"region\[(0|[1-9][0-9]*),([1-9][0-9]*)\]",ty)
                        require(m and role in ["in","mut"],"invalid memory interface type/role")
                        result.append({"A":int(m[1]),"W":int(m[2]),"role":role})
                    return result
                if kind in ["cc","r"]:
                    require(sig["params"]==[ty for n,ty,r in g[0]] and sig["results"]==[ty for n,ty,r in g[1]] and not any(g[2:]),"§9.1: classical signature/header mismatch")
                elif kind=="oracle":
                    require(len(g[1])==len(g[2])==1 and sig["in"]==widths(g[0]) and sig["tgt"]==widths(g[1])[0] and sig["fault"]==widths(g[2])[0] and sig["mem"]==mem(g[3]) and sig["args"]==[ty for n,ty,r in g[4]],"§9.1: oracle signature/header mismatch")
                elif kind in ["action","perm_action"]:
                    require(sig["mut"]==widths(g[0]) and sig["in"]==widths(g[1]) and sig["mem"]==mem(g[2]) and sig["args"]==[ty for n,ty,r in g[3]] and not g[4],"§9.1: action signature/header mismatch")
                else:
                    require(len(g[1])==1 and sig["params"]==widths(g[0]) and sig["result"]==widths(g[1])[0] and sig["tokens"]==[ty for n,ty,r in g[2]] and sig["args"]==[ty for n,ty,r in g[3]] and sig["mem"]==mem(g[4]),"§9.1: lproc signature/header mismatch")
                for n,ty,r in fn.regs: type_width(ty,out.ptr)
            else:
                require(symbol["name"] in out.sections.get("data",{}) and integer(sig["size"],0)*2==len(out.sections["data"][symbol["name"]]),"data signature size mismatch")
        if "layout" in out.sections:
            keys(out.sections["layout"], ["ptr_width","H","A_tab","S_cells","null_size","heap_base","heap_limit_max","globals","interface_regions"], ["block_image"], "layout")
        if "devices" in out.sections: keys(out.sections["devices"], ["models","services"], context="devices")
        return out

    def symbol(self, name):
        matches = [s for s in self.sections["symbols"].values() if s["name"] == name]
        require(len(matches) == 1, f"unknown/ambiguous symbol {name}")
        return matches[0]

    def identities(self, closure=False):
        records = {s["name"]:s for s in self.sections["symbols"].values()}
        imports = self.sections.get("imports", {})
        computed = {}
        for name, record in imports.items():
            computed[name] = record.get("pinned_closure_hash") if closure else digest(name + "\0" + jcs(record["signature"]))
            require(computed[name], f"unresolved closure import {name}")
        def leaves(name):
            kind = records[name]["kind"]
            layout = self.sections.get("layout", {})
            raw = self.functions[name].raw if name in self.functions else ""
            result = []
            for key,val in layout.items():
                if key in ["globals", "interface_regions"]:
                    for sub,v in val.items():
                        if key == "interface_regions":
                            if kind == "oracle" and sub == name or kind in ["cc","r"]:
                                result.extend(([key,sub,r], x) for r,x in v.items())
                        elif kind in ["oracle","cc","r"] or kind == "lproc" and "@"+sub in re.findall("@"+NAME,raw):
                            result.append(([key,sub],v))
                elif kind in ["oracle","cc","r"]: result.append(([key],val))
            return sorted(result, key=lambda p:(".".join(p[0]) if self.versions["isa"]=="0.8" else jcs(p[0])).encode())
        def source(name):
            if records[name]["kind"] == "data": return name+" "+self.sections["data"][name]
            return self.functions[name].raw
        leaf_map = {n:leaves(n) for n in records}
        images = {n:sorted({v["image"] for p,v in leaf_map[n] if isinstance(v,dict) and "image" in v} | ({self.sections["layout"]["block_image"]} if any(p == ["block_image"] for p,v in leaf_map[n]) else set())) for n in records}
        references = {}
        for name in records:
            raw = source(name)
            # Remove the header's definition token before collecting references.
            scan = raw.split("\n",1)[1] if name in self.functions and "\n" in raw else ""
            refs = re.findall("@("+NAME+")", scan)
            references[name] = list(dict.fromkeys(r for r in refs if r in records or r in imports))
        # Tarjan SCCs, then recursively evaluate the component DAG.
        counter, indices, low, stack, on, components = 0, {}, {}, [], set(), []
        def visit(v):
            nonlocal counter
            indices[v] = low[v] = counter; counter += 1
            stack.append(v); on.add(v)
            for w in references[v]:
                if w not in records: continue
                if w not in indices: visit(w); low[v] = min(low[v],low[w])
                elif w in on: low[v] = min(low[v],indices[w])
            if low[v] == indices[v]:
                component = []
                while True:
                    w = stack.pop(); on.remove(w); component.append(w)
                    if w == v: break
                components.append(sorted(component))
        for v in records:
            if v not in indices: visit(v)
        for component in components:
            cyclic = len(component)>1 or component[0] in references[component[0]]
            def envelope(name):
                refs = references[name]
                def replace(m):
                    r = m[1]
                    if cyclic and r in component: return "@$"+str(component.index(r))
                    return "@"+computed[r] if r in computed else m[0]
                raw = source(name)
                if name in self.functions:
                    head, tail = raw.split("\n",1)
                    raw = head+"\n"+re.sub("@("+NAME+")",replace,tail)
                parts = ["isa="+self.versions["isa"], "ptr_width="+str(self.ptr), jcs(records[name]["signature"]), raw]
                parts += ["data "+n+" "+self.sections["data"][n] for n in images[name]]
                parts += ["layout "+(".".join(path) if self.versions["isa"]=="0.8" else jcs(path))+" "+jcs(value) for path,value in leaf_map[name]]
                if records[name]["kind"] in ["cc","r"]:
                    dev = self.sections.get("devices", {})
                    used = set()
                    for inst in self.functions[name].code:
                        if inst.op == "effect": used.add(inst.args[0].split(".")[0])
                        if inst.op == "hostcall": used.add(inst.args[0])
                    for n in sorted(used):
                        value = dev.get("models",{}).get(n,dev.get("services",{}).get(n))
                        if value is not None: parts.append("device "+n+" "+jcs(value))
                parts += [computed[r] for r in refs if r not in component or not cyclic]
                return "\n".join(parts)+"\n"
            if cyclic:
                scc = digest("".join(envelope(n) for n in component))
                for i,n in enumerate(component): computed[n] = digest(scc+":"+str(i))
            else: computed[component[0]] = digest(envelope(component[0]))
        return {n:computed[n] for n in records}


def validate_budget(budget, obj):
    require(isinstance(budget,list) and len(budget) == 4, "§5.4/K13: budget requires four components")
    values = [unsigned(v) for v in budget]
    layout = obj.sections.get("layout")
    if layout is None:
        require(values[1:] == [0,0,0], "§5.4: memoryless budget requires heap=stack=depth=0")
    else:
        require(values[1] <= integer(layout["heap_limit_max"],0) and values[2] <= 1 << integer(layout["S_cells"],0), "§5.4: budget exceeds layout")
        # Dc is derived from depth_limit, not from S_cells (§3.7).
    return values


def resolved_arguments(types, values, obj):
    require(isinstance(values,list) and len(types) == len(values), "E_ARG: missing/extra resolved arguments")
    out = []
    for ty, value in zip(types, values):
        if ty == "token": validate_budget(value,obj); out.append(value)
        elif ty == "f64":
            require(isinstance(value,str) and re.fullmatch(r"0x[0-9a-f]{16}",value), "K13: f64 needs exact binary64 bits")
            out.append(int(value[2:],16))
        else:
            width = type_width(ty,obj.ptr)
            n = unsigned(value)
            require(n < 1 << width, f"E_ARG: {ty} argument out of range")
            out.append(n)
    return out


class Source:
    def __init__(self, obj, target, catalog):
        self.obj, self.target, self.catalog = obj, target, catalog
        self.cls = catalog.default_class
        self.serial = 0
        self.calls = []

    def fresh(self, name, width, cls=None, state="clean"):
        self.serial += 1
        return Bundle(f"source:{self.serial}:{name}", width, cls or self.cls, state=state)

    def region(self, name, args, budget, interface=None, controls=(), adjoint=False):
        require(name not in self.calls, "§5.1: recursive region call graph")
        self.calls.append(name)
        try:
            fn = self.obj.functions[name]
            sig = self.obj.symbol(name)["signature"]
            parsed = resolved_arguments(sig.get("args",sig.get("params",[])), args, self.obj)
            env = dict(interface or {})
            wire_groups = fn.groups[:4] if fn.kind == "oracle" else fn.groups[:3]
            for group in wire_groups:
                for n,ty,role in group:
                    if n not in env: env[n] = self.fresh(n,type_width(ty,self.obj.ptr))
            arg_group = fn.groups[4] if fn.kind == "oracle" else fn.groups[3]
            env.update({n:v for (n,ty,r),v in zip(arg_group,parsed)})
            if fn.kind in ["action","perm_action"]:
                nodes = [i for _,code in fn.blocks.values() for i in code]
                # Function-local regions are allocated at entry regardless of
                # their source declaration's position or enclosing predicate.
                regions, prefix, suffix = {}, Profile(), Profile()
                for n,ty,role in fn.groups[2]:
                    m=re.fullmatch(r"region\[([0-9]+),([0-9]+)\]",ty)
                    regions[n]=(int(m[1]),int(m[2]),env[n])
                for inst in fn.code:
                    if inst.op != "qregion": continue
                    n,A,W,*image = inst.args
                    A,W = integer(A,0),integer(W,1)
                    b = self.fresh(n,(1<<A)*W)
                    regions[n] = (A,W,b)
                    env[n] = b
                    prefix = prefix.then(space_profile(b.cls,"clean",b.width))
                    if image:
                        data = self.obj.sections.get("data",{}).get(image[0].removeprefix("@"))
                        require(data is not None,"unbound qregion image")
                        prep = self.catalog.body([{"image":"I","wires":"cells"}],{"I":data,"cells":b})
                        prefix = prefix.then(prep)
                        suffix = prep.then(space_profile(b.cls,"clean",-b.width)).then(suffix)
                    else: suffix = space_profile(b.cls,"clean",-b.width).then(suffix)
                p = prefix.then(self.action(nodes,env,regions,controls,adjoint)).then(suffix)
                require(all(v == 0 for v in p.delta.values()),"§5.1: unmatched allocation/release in action")
                return p
            require(fn.kind == "oracle", "root region must be action, oracle, CC or R")
            return self.oracle(fn,env,budget,controls)
        finally:
            self.calls.pop()

    def action(self, nodes, env, regions, controls=(), inverse=False):
        out = Profile()
        # Source adjoints require instruction replacements before expansion.
        # The environment tracks forward allocation names during lowering.
        if inverse:
            forward = self.action_nodes(nodes,dict(env),regions,controls)
            return self.catalog.body(forward,env,controls,True)
        nodes = self.action_nodes(nodes,env,regions,controls)
        return self.catalog.body(nodes,env,controls)

    def oracle(self, fn, env, budget, controls=()):
        require(self.obj.versions["isa"] == "0.9", "0.8 has no published complete expansion library; exact padded cost requires 0.9")
        require("layout" not in self.obj.sections and not fn.groups[3], "layout/activation source binding is pending; no padded cost fabricated")
        require(not fn.groups[4], "resolved pseudo-location source binding is pending; no parameter substitution fabricated")
        B = unsigned(budget[0])
        rows = fn.code
        N = len(rows)
        P = max(1,N.bit_length())
        sig = self.obj.symbol(fn.name)["signature"]
        Fwidth,T = sig["fault"],sig["tgt"]
        for n,ty,_ in fn.regs: env[n] = self.fresh(n,type_width(ty,self.obj.ptr))
        widths = {n:b.width for n,b in env.items() if isinstance(b,Bundle)}
        slot_widths = []
        for row in rows:
            ws = [widths[n] for n in row.lhs]
            for j,w in enumerate(ws):
                if j == len(slot_widths): slot_widths.append(w)
                else: slot_widths[j] = max(slot_widths[j],w)
        Q = 2*P + sum(slot_widths) + 1
        pc,nextpc = self.fresh("pc",P), self.fresh("pc_prime",P)
        faulted,code,result = self.fresh("faulted",1),self.fresh("code",Fwidth),self.fresh("result_val",T)
        frame = self.fresh("frame",Q)
        flag = {"range":"frame","from":P+sum(slot_widths),"to":P+sum(slot_widths)+1}
        successor = {"range":"frame","from":Q-P,"to":Q}
        labels={}
        offset=0
        for block,(_,instructions) in fn.blocks.items(): labels[block]=offset;offset+=len(instructions)
        row_templates,next_templates=[],[]
        template_formal=[{"name":"frame","type":"wire","width":Q}]
        def invoke(name, actuals): return {"invoke":name,"args":actuals}
        def lit(value): return invoke("successor.literal",[P,value,"next"])
        for index,row in enumerate(rows):
            op = re.sub(r"\.i[1-9][0-9]*$","",row.op)
            a = row.args
            body=[]
            written=row.lhs
            if written:
                require(len(written)==1 or op=="lift.parmov","unsupported multi-result lifted row")
                w=written[0];width=widths[w]
                slot={"range":"frame","from":P,"to":P+width}
            if op in ["lift.const","lift.label","lift.addr"]:
                require(op!="lift.addr","lift.addr needs layout")
                value=int(a[0]) if op=="lift.const" else labels[a[0].removeprefix("^")]
                require(0<=value<1<<width,"lifted literal out of range")
                body=[invoke(op,[width,value,slot,w])]
            elif op in ["lift.add","lift.sub","lift.mul","lift.and","lift.or","lift.xor","lift.shl","lift.lshr","lift.ashr"]:
                body=[invoke(op,[width,*a,slot,w])]
            elif op.startswith("lift.icmp."):
                body=[invoke(op,[widths[a[0]],*a,slot,w])]
            elif op=="lift.select": body=[invoke(op,[width,a[1],a[2],a[0],slot,w])]
            elif op in ["lift.zext","lift.sext","lift.trunc"]: body=[invoke(op,[widths[a[0]],width,a[0],slot,w])]
            elif op=="lift.mov": body=[invoke(op,[width,a[0],slot,w])]
            elif op in ["lift.udiv","lift.urem","lift.sdiv","lift.srem"]:
                body=[invoke(op,[width,Fwidth,*a,slot,w,flag,faulted,code])]
            elif op=="lift.parmov":
                sources=list_operand(a[0]);require(len(sources)==len(written),"parmov arity")
                cursor=P
                # All captures/computes precede all exchanges (§3.6).
                for dest,src in zip(written,sources):
                    n=widths[dest];s={"range":"frame","from":cursor,"to":cursor+n};cursor+=slot_widths[len(body)]
                    body.append(invoke("bind.qxor",[n,src,s]))
                cursor=P
                for j,dest in enumerate(written):
                    n=widths[dest];s={"range":"frame","from":cursor,"to":cursor+n};cursor+=slot_widths[j]
                    body.append(invoke("bind.qexch",[n,s,dest]))
            elif op=="lift.retval": body=[invoke(op,[T,a[0],result])]
            elif op=="lift.faultif": body=[invoke(op,[Fwidth,int(a[1]) or 4,a[0],flag,faulted,code])]
            elif op=="fault": body=[invoke("fault",[Fwidth,int(a[0]) or 4,faulted,code])]
            elif op=="qjump": body=[]
            elif op=="qbranch": body=[invoke(op,[P,labels[a[1][1:]],labels[a[2][1:]],a[0],successor])]
            elif op=="qjumpr": body=[invoke(op,[P,Fwidth,0,N,a[0],successor,flag,faulted,code])]
            else: raise ContractError(f"oracle source binding not implemented: {row.op}; no row omitted")
            if op in ["lift.retval","fault"]: nxt=[lit(N)]
            elif op=="qjump": nxt=[lit(labels[a[0][1:]])]
            elif op=="qbranch": nxt=[invoke("bind.qxor",[P,successor,"next"])]
            elif op=="qjumpr": nxt=[invoke("successor.dynamic",[P,N,flag,successor,"next"])]
            elif op in ["lift.faultif","lift.udiv","lift.urem","lift.sdiv","lift.srem"]: nxt=[invoke("successor.flagged",[P,index+1,N,flag,"next"])]
            else: nxt=[lit(index+1)]
            row_templates.append({"parameters":template_formal,"body":body})
            next_templates.append({"parameters":template_formal+[{"name":"next","type":"wire","width":P}],"body":nxt})
        step=self.catalog.recipe("step",[P,N,Q,pc,nextpc,frame,row_templates,next_templates],env,controls)
        require(all(v==0 for v in step.delta.values()),"unbalanced step workspace")
        target=env[fn.groups[1][0][0]];fault=env[fn.groups[2][0][0]]
        # Exactly the published commit segment, with the source-bound state.
        commit_nodes=self.catalog.recipes["oracle.construct"]["body"][2:-2]
        commit_env=dict(env,P=P,N=N,F=Fwidth,T=T,pc=pc,next=nextpc,faulted=faulted,code=code,result=result,tgt=target,fr=fault)
        commit=self.catalog.body(commit_nodes,commit_env,controls)
        state_width=2*P+1+Fwidth+T+sum(widths[n] for n,ty,r in fn.regs)+B*Q
        work=step.repeat(B).then(commit).then(step.repeat(B))
        return space_profile(self.cls,"clean",state_width).then(work).then(space_profile(self.cls,"clean",-state_width))

    def classical(self, fn, args):
        """Count a resolved classical control path; quantum inputs stay abstract.

        Values are used only for classical control. There is no choice of a
        quantum basis tuple, and no oracle is executed on such a tuple.
        """
        parsed = resolved_arguments([ty for n,ty,r in fn.groups[0]],args,self.obj)
        initial = {n:(v,type_width(ty,self.obj.ptr) if ty != "token" else 0) for (n,ty,r),v in zip(fn.groups[0],parsed)}
        memory, allocations = {}, {}
        clock=0
        layout = self.obj.sections.get("layout",{})
        bump = integer(layout.get("heap_base",0),0)
        for n,g in layout.get("globals",{}).items():
            base = integer(g["base"],0)
            image = bytes.fromhex(self.obj.sections["data"][g["image"]])
            allocations[base] = (len(image),True)
            memory.update({base+i:b for i,b in enumerate(image)})
        def execute(function, values):
            nonlocal bump,clock
            env = dict(values)
            block = next(iter(function.blocks))
            p,steps = Profile(),0
            def get(n):
                if n in env: return env[n]
                if re.fullmatch(r"-?(0|[1-9][0-9]*)",n): return (int(n),self.obj.ptr)
                raise ContractError(f"classical value has no current instance: {n}")
            def jump(label):
                m = re.fullmatch(r"\^([^ (]+)\((.*?)\)",label)
                require(m and m[1] in function.blocks,"invalid branch label")
                formals = function.blocks[m[1]][0]
                actuals = m[2].split(", ") if m[2] else []
                require(len(formals)==len(actuals),"branch argument arity")
                resolved = [get(a) for a in actuals]
                env.update({n:v for (n,ty,r),v in zip(formals,resolved)})
                return m[1]
            while True:
                code = function.blocks[block][1]
                jumped = False
                for inst in code:
                    op,a = inst.op,inst.args
                    p = p.then(Profile(time=rational(self.target.doc["capabilities"]["classical_step_time"])))
                    steps += 1
                    result = None
                    if op.startswith("const.i"):
                        width=integer(op[7:],1); result=(integer(a[0]) % (1<<width),width)
                    elif op in ["add","sub","mul","and","or","xor","shl","lshr","ashr","udiv","urem","sdiv","srem"] or op.startswith("icmp."):
                        (x,w),(y,v) = get(a[0]),get(a[1]); require(w==v,"classical operand width mismatch")
                        def signed(x): return x-(1<<w) if x & (1<<(w-1)) else x
                        if op.startswith("icmp."):
                            pred=op[5:]
                            if pred.startswith("s"): x,y=signed(x),signed(y)
                            value={"eq":lambda:x==y,"ne":lambda:x!=y,"ult":lambda:x<y,"ule":lambda:x<=y,"slt":lambda:x<y,"sle":lambda:x<=y}[pred]()
                            result=(int(value),1)
                        else:
                            if op in ["udiv","urem","sdiv","srem"] and (y==0 or op.startswith("s") and signed(x)==-(1<<(w-1)) and signed(y)==-1): return p,steps,[],True
                            if op in ["sdiv","srem"]:
                                sx,sy=signed(x),signed(y)
                                q=(abs(sx)//abs(sy))*(-1 if (sx<0)!=(sy<0) else 1)
                                value=q if op=="sdiv" else sx-q*sy
                            else:
                                value={"add":lambda:x+y,"sub":lambda:x-y,"mul":lambda:x*y,"and":lambda:x&y,"or":lambda:x|y,"xor":lambda:x^y,
                                       "shl":lambda:x<<y if y<w else 0,"lshr":lambda:x>>y if y<w else 0,"ashr":lambda:signed(x)>>y if y<w else 0,
                                       "udiv":lambda:x//y,"urem":lambda:x%y}[op]()
                            result=(value % (1<<w),w)
                    elif op.startswith(("zext.i","sext.i","trunc.i","ptrtoint.i")) or op=="inttoptr":
                        x,w=get(a[0]); width=self.obj.ptr if op=="inttoptr" else int(op.split(".i")[-1])
                        if op.startswith("sext") and x & (1<<(w-1)): x-=1<<w
                        result=(x % (1<<width),width)
                    elif op=="select": result=get(a[1] if get(a[0])[0] else a[2])
                    elif op=="br":
                        block=jump(a[0] if len(a)==1 else a[1] if get(a[0])[0] else a[2]); jumped=True;break
                    elif op=="ret": return p,steps,[get(n) for n in a],False
                    elif op in ["trap","fault"]: return p,steps,[],True
                    elif op=="call":
                        callee=self.obj.functions[a[0].removeprefix("@")]
                        params=callee.groups[0]
                        require(len(params)==len(a)-1,"call argument arity")
                        cp,cs,results,failed=execute(callee,{n:get(actual) for (n,ty,r),actual in zip(params,a[1:])})
                        p=p.then(cp);steps+=cs
                        if failed: return p,steps,[],True
                        require(len(results)==len(inst.lhs),"call result arity")
                        env.update(zip(inst.lhs,results));continue
                    elif op=="alloc":
                        n=get(a[0])[0];base=bump;bump+=max(1,n)
                        if bump > integer(layout.get("heap_base",0))+integer(layout.get("heap_limit_max",0)) or len(allocations)>=(1<<integer(layout.get("A_tab",0))): return p,steps,[],True
                        allocations[base]=(max(1,n),False);result=(base,self.obj.ptr)
                    elif op=="free":
                        base=get(a[0])[0]
                        if base not in allocations or allocations[base][1]: return p,steps,[],True
                        del allocations[base]
                    elif op.startswith(("load.i","store.i")):
                        width=int(op.split(".i")[-1]);address=get(a[0])[0];size=width//8
                        if not any(base<=address and address+size<=base+n for base,(n,pinned) in allocations.items()): return p,steps,[],True
                        if op.startswith("load"):
                            require(all(memory.get(address+i,0) is not None for i in range(size)),"cost control depends on unresolved effect/measurement data; a path bound is required")
                            result=(sum(memory.get(address+i,0)<<(8*i) for i in range(size)),width)
                        else:
                            value=get(a[1])[0]
                            memory.update({address+i:(value>>(8*i))&255 for i in range(size)})
                    elif op=="effect":
                        dev=a[0]
                        if dev not in ["clock.read","entropy.read","console.write","block.read","block.write"]: return p,steps,[],True
                        ptr=get(a[2] if dev.startswith("block.") else a[1])[0]
                        size=8 if dev=="clock.read" else get(a[2])[0] if dev in ["entropy.read","console.write"] else 512
                        if not any(base<=ptr and ptr+size<=base+n for base,(n,_) in allocations.items()): return p,steps,[],True
                        if dev=="console.write": continue
                        if dev=="clock.read":
                            memory.update({ptr+i:(clock>>(8*i))&255 for i in range(8)})
                            clock=(clock+1)%(1<<64)
                        else:
                            raise ContractError(f"exact classical effect-state binding pending: {dev}; use an explicit conditional step bound")
                    else: raise ContractError(f"classical source binding not implemented: {op}; no exact estimate emitted")
                    if result is not None:
                        require(len(inst.lhs)==1,"classical result arity")
                        env[inst.lhs[0]]=result
                require(jumped,"classical block has no terminator")
        p,steps,_,_=execute(fn,initial)
        return p,steps

    def action_nodes(self, source_nodes, env, regions, controls=()):
        out = []
        predicates = []
        def emit(node):
            if predicates:
                node = {"under": list(predicates), "body":[node]}
            out.append(node)
        for inst in source_nodes:
            op,a = inst.op,inst.args
            if op in GATES or op == "mcx":
                params = []
                if op in ["rx","ry","rz"]:
                    theta,*a = a
                    require(math.isfinite(float(theta)),"§4.4: nonfinite angle")
                    params = [theta]
                a = [list_operand(x) if x.startswith("(") else x for x in a]
                emit({"gate":op,"wires":a,**({"params":params} if params else {})})
            elif op in ["qalloc","qborrow","qcopy","qload"]:
                require(len(inst.lhs)==1,"missing allocation result")
                name = inst.lhs[0]
                require(name not in env,"allocation shadows a live binding")
                if op in ["qalloc","qborrow"]:
                    cls,n = a
                    n = env.get(n,integer(n,1) if re.fullmatch(r"[0-9]+",n) else None)
                    require(isinstance(n,int) and n>0,"invalid allocation width")
                    cls = self.cls if cls == "any" else cls
                    state = "borrowed" if op == "qborrow" else "clean"
                elif op == "qcopy":
                    n = sum(b.width for b in wire(a[0],env)); cls,state = self.cls,"clean"
                else:
                    require(a[0] in regions,"unknown region")
                    A,n,_ = regions[a[0]]; cls,state=self.cls,"clean"
                b = self.fresh(name,n,cls,state)
                env[name] = b
                # Bind allocation result outside captured loops; acquire/release
                # retain its source identity. No wire-sized array is created.
                out.append({"acquire":name})
                if op == "qcopy":
                    emit({"invoke":"bind.qxor","args":[n,a[0],name]})
                elif op == "qload":
                    A,W,cells = regions[a[0]]
                    addr = [] if a[1] == "()" else a[1]
                    emit({"invoke":"dispatch.copy","args":[A,1<<A,W,addr,cells,name]})
            elif op in ["qfree","qreturn","quncopy","qunload"]:
                name = a[-1]
                require(name in env and isinstance(env[name],Bundle),"release of unknown bundle")
                b = env[name]
                if op == "quncopy": emit({"invoke":"bind.qxor","args":[b.width,a[0],name]})
                if op == "qunload":
                    A,W,cells=regions[a[0]]
                    emit({"invoke":"dispatch.copy","args":[A,1<<A,W,[] if a[1]=="()" else a[1],cells,name]})
                out.append({"relinquish":name})
                # env retains the immutable descriptor for catalog traversal;
                # liveness is checked separately by the source lowering.
            elif op in ["qxor","qexch"]:
                n = sum(b.width for b in wire(a[0],env))
                emit({"invoke":"bind.qxor" if op=="qxor" else "bind.qexch","args":[n,*a]})
            elif op == "qpred":
                require(len(a)==1,"qpred arity"); predicates.append(a[0])
            elif op == "qunpred":
                require(predicates and predicates.pop()==a[0],"predicate stack mismatch")
            elif op == "qloop":
                n=env.get(a[0],int(a[0]) if a[0].isdigit() else None)
                require(isinstance(n,int) and n>=0,"invalid qloop bound")
                body = self.action_nodes(inst.body,env,regions,controls)
                if len(a)==1: emit({"for":"$iteration","from":0,"to":n,"body":body})
                else:
                    require(a[1]=="while" and len(a)==3,"qloop while syntax")
                    # Captured body holds immutable source bundle descriptors.
                    captured = Captured(body,dict(env),controls)
                    body_name = f"$body{self.serial}";env[body_name]=captured
                    emit({"invoke":"qloop.while","args":[n,a[2],body_name]})
            elif op == "qif":
                then = self.action_nodes(inst.body,env,regions,controls)
                otherwise = self.action_nodes(inst.otherwise,env,regions,controls)
                emit({"under":a[0],"body":then})
                emit({"gate":"x","wires":[a[0]]})
                emit({"under":a[0],"body":otherwise})
                emit({"gate":"x","wires":[a[0]]})
            elif op in ["qstore","qexchm"]:
                A,W,cells=regions[a[0]]
                emit({"invoke":"dispatch.store" if op=="qstore" else "dispatch.exchange","args":[A,1<<A,W,[] if a[1]=="()" else a[1],cells,a[2]]})
            elif op=="ctl":
                require(len(a)>=3,"ctl requires control and region call")
                nested=Instruction(a[1],a[2:],[],block=inst.block,ordinal=inst.ordinal)
                emit({"under":a[0],"body":self.action_nodes([nested],env,regions,controls)})
            elif op=="adj":
                require(len(a)>=2,"adj requires region call")
                nested=Instruction(a[0],a[1:],[],block=inst.block,ordinal=inst.ordinal)
                emit({"inverse":True,"body":self.action_nodes([nested],env,regions,controls)})
            elif op=="action_call":
                require(len(a)==5,"action_call requires four complete argument groups")
                name=a[0].removeprefix("@")
                require(name in self.obj.functions and name not in self.calls,"unknown/cyclic action call")
                fn=self.obj.functions[name]
                require(fn.kind in ["action","perm_action"],"action_call requires action")
                require(not any(i.op=="qregion" for i in fn.code),"callee local-region constructor binding remains pending")
                actual_groups=[list_operand(x) for x in a[1:]]
                require(all(len(g)==len(v) for g,v in zip(fn.groups[:4],actual_groups)),"action call argument arity")
                child,child_regions={},{}
                all_wires=[]
                for group,actuals in zip(fn.groups[:2],actual_groups[:2]):
                    for (n,ty,role),actual in zip(group,actuals):
                        ws=wire(actual,env)
                        require(sum(b.width for b in ws)==type_width(ty,self.obj.ptr),"action call wire width mismatch")
                        child[n]=ws;all_wires+=ws
                for (n,ty,role),actual in zip(fn.groups[2],actual_groups[2]):
                    require(actual in regions,"unknown memory argument")
                    A,W,b=regions[actual]
                    require(ty==f"region[{A},{W}]","action call region shape mismatch")
                    child[n]=b;child_regions[n]=(A,W,b)
                    all_wires+=wire(b,env)
                for i,b in enumerate(all_wires):
                    for other in all_wires[:i]: require(b.identity!=other.identity or b.offset+b.width<=other.offset or other.offset+other.width<=b.offset,"overlapping action call arguments")
                caller=self.obj.functions[self.calls[-1]]
                caller_types={n:ty for n,ty,r in caller.groups[3]}
                for (n,ty,r),actual in zip(fn.groups[3],actual_groups[3]):
                    require(caller_types.get(actual)==ty,"action call classical argument type mismatch")
                    child[n]=env[actual]
                self.calls.append(name)
                try:
                    body=self.action_nodes([i for _,code in fn.blocks.values() for i in code],child,child_regions,controls)
                finally:
                    self.calls.pop()
                self.serial+=1
                capture=f"$call:{self.serial}"
                env[capture]=Captured(body,child,controls)
                # Only aggregate default costs here. Captured bodies are an
                # internal summary composition, not exchanged leaf ordinals;
                # explicit schedule/context binding remains a separate task.
                emit({"splice":capture})
            elif op == "qregion": pass
            else:
                raise ContractError(f"source binding not implemented: {op}; no estimate or exactness claim emitted")
        require(not predicates,"nonempty predicate stack at scope exit")
        return out


def estimate(obj,target,region,args,budget,variant="forward",inherited_controls=0,step_bound=None):
    require(region in obj.functions,"unknown entry region")
    require(obj.ptr in target.doc["ptr_widths_supported"],"E_PTR_WIDTH: target does not support object pointer width")
    require(isinstance(variant,str) and variant,"empty variant")
    inherited_controls=integer(inherited_controls,0)
    validate_budget(budget,obj)
    catalog = Catalog(globals().get("CATALOG_TEXT") or (Path(__file__).resolve().parents[1]/"data/ref-0.9.json").read_text(),target)
    require("topology" not in target.doc,"topology source placement is pending; no feasibility/exactness claim emitted")
    identities=obj.identities()
    for symbol in obj.sections["symbols"].values():
        require(identities[symbol["name"]]==symbol["interface_hash"],f"§9.2: incorrect interface_hash for {symbol['name']}")
    closure=obj.identities(closure=True)[region]
    bindings={"closure_hash":closure,"target_hash":target.hash,"region":region,"variant":variant,
              "inherited_controls":inherited_controls,"budget":budget,"params_hash":digest(jcs(args)),"epsilon":0,
              "expansion":{"name":"ref","version":"0.9","hash":catalog.hash},
              "scheduler":{"name":"bennett-estimate-default","version":"0.1.0"}}
    effective_schedule={"bindings":bindings,"entries":[]}
    if "schedule" in obj.sections:
        schedule=obj.sections["schedule"]
        keys(schedule,["bindings","entries"],["interface_vertices"],"schedule")
        def binding_equal(key,value):
            supplied=schedule["bindings"].get(key)
            if key=="budget":
                return isinstance(supplied,list) and len(supplied)==4 and [rational(n) for n in supplied]==[rational(n) for n in value]
            if key=="epsilon": return supplied is not None and rational(supplied)==rational(value)
            return supplied==value
        selected=all(binding_equal(k,v) for k,v in bindings.items() if k!="scheduler")
        if selected:
            require(not schedule["entries"],"explicit schedule selectors are pending; matching schedule was not ignored")
            effective_schedule=schedule
    source = Source(obj,target,catalog)
    fn = obj.functions[region]
    if fn.kind in ["cc","r"]:
        if step_bound is None:
            p,steps = source.classical(fn,args)
        else:
            # A caller-supplied termination assumption is explicit evidence,
            # never a proof that an unbounded classical program terminates.
            resolved_arguments([ty for n,ty,r in fn.groups[0]],args,obj)
            classical_ops={"add","sub","mul","and","or","xor","shl","lshr","ashr","udiv","urem","sdiv","srem","select","alloc","free","br","call","uncall","ret","trap","fault","effect","hostcall","inttoptr"}
            for f in obj.functions.values():
                require(f.kind in ["cc","r"],"step-only classical bound cannot omit quantum regions")
                require(all(i.op in classical_ops or i.op.startswith(("const.i","icmp.","load.i","store.i","zext.i","sext.i","trunc.i","ptrtoint.i")) for i in f.code),"step-only bound cannot omit quantum/register operations")
            steps=integer(step_bound,0)
            p=Profile(time=rational(target.doc["capabilities"]["classical_step_time"])*steps)
        interface = {}
    else:
        controls = tuple(("inherited",i,source.cls) for i in range(inherited_controls))
        p = source.region(region,args,budget,controls=controls)
        sig = obj.symbol(region)["signature"]
        widths = list(sig.get("in",[]))+list(sig.get("mut",[]))+([sig["tgt"],sig["fault"]] if fn.kind=="oracle" else [])
        widths += [(1<<integer(m["A"],0))*integer(m["W"],1) for m in sig.get("mem",[])]
        interface = {source.cls:sum(widths)+inherited_controls}
        steps = None
    rows = p.resources(target,interface)
    for cls,desc in target.doc["classes"].items():
        peak = rows.get("peak_qubits["+escape(cls)+"]",0)
        require(desc["capacity"]=="unbounded" or peak <= desc["capacity"], f"E_SCHEDULE_INFEASIBLE: capacity exceeded for {cls}")
    result={"schema":"bennett-estimate/0.1", "label":"bound" if step_bound is not None else "exact", "scope":"sequential reference realisation", "object_hash":obj.hash,
            "interface_hash":identities[region],"closure_hash":closure,"effective_schedule":effective_schedule,"schedule_hash":digest(jcs(effective_schedule)),
            "target_hash":target.hash,"region":region,"variant":variant,"inherited_controls":inherited_controls,
            "invocation":{"args":args,"budget":budget},"params_hash":digest(jcs(args)),
            "resources":{n:decimal_up(q) for n,q in rows.items()},
            "exact_resources":{n:{"numerator":str(q.numerator),"denominator":str(q.denominator)} for n,q in rows.items()},
            "gates":{n:str(v) for n,v in sorted(p.gates.items())},"classical_steps":str(steps) if steps is not None else None,
            "error_bound":str(p.error),"summary_operations":catalog.visits}
    if step_bound is not None:
        result["bound_assumptions"]=[f"classical execution terminates within {steps} source instructions, including callees and reversal"]
        result["rational_upper_bounds"]=result.pop("exact_resources")
    return result


class Certificate:
    """Schema reader, distinct from a proof or numerical/channel checker."""
    def __init__(self,doc): self.doc=doc

    @staticmethod
    def exact_rows(rows):
        require(isinstance(rows,dict),"K12: exact_resources must be object")
        result={}
        for name,value in rows.items():
            keys(value,["numerator","denominator"],context="exact resource")
            n,d=unsigned(value["numerator"]),unsigned(value["denominator"])
            require(d>0 and math.gcd(n,d)==1,"K12: resource fraction must be reduced; zero is 0/1")
            result[name]=F(n,d)
        return result

    @staticmethod
    def frame(doc):
        keys(doc,["slots","scratch","history","borrow","ancillae"],["live_ranges"],"frame")
        seen=set()
        for group in ["slots","scratch","history","borrow","ancillae"]:
            require(isinstance(doc[group],list),"frame group must be array")
            for record in doc[group]:
                extra={"slots":["role"],"scratch":["state"],"history":[],"borrow":[],"ancillae":["scheme","state"]}[group]
                keys(record,["id","class","width",*extra],context="frame record")
                require(isinstance(record["id"],str) and record["id"] and record["id"] not in seen,"duplicate/empty frame identity")
                seen.add(record["id"])
                if "state" in record: require(record["state"] in ["clean","dirty"],"invalid frame state")
                if "role" in record: require(record["role"] in ["in","tgt","fault","mut","mem_in","mem_mut"],"invalid frame role")
                Target.validate_expr(record["width"],{"c"},{})
        intervals={}
        for live in doc.get("live_ranges",[]):
            keys(live,["frame","start","end"],context="live range")
            require(live["frame"] in seen and not any(r["id"]==live["frame"] for r in doc["slots"]),"live range needs non-slot identity")
            lo,hi=integer(live["start"],0),integer(live["end"],0)
            require(lo<hi,"empty/reversed live range")
            for a,b in intervals.get(live["frame"],[]): require(hi<=a or lo>=b,"overlapping shared frame intervals")
            intervals.setdefault(live["frame"],[]).append((lo,hi))

    @classmethod
    def read(cls,text):
        doc=loads(text)
        require(jcs(doc)==text,"§12: certificate must be JCS")
        keys(doc,["versions","bindings","producer","regions","composition"],context="certificate")
        keys(doc["versions"],["isa","object","launch","sched","cert","coverage","target"],context="versions")
        require(set(doc["versions"].values())=={"0.9"},"unsupported certificate versions")
        b=doc["bindings"]
        keys(b,["object_hash","interface_hash","closure_hash","reference_program_hash","dialect_mapping_version","target_hash"],["schedule_hash","invocation"],"certificate bindings")
        for key,value in b.items():
            if key.endswith("_hash"): require(isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value),f"invalid {key}")
        if "schedule_hash" in b:
            require("invocation" in b,"K13: scheduled certificate lacks invocation")
        if "invocation" in b:
            keys(b["invocation"],["args","budget"],context="invocation")
            require(isinstance(b["invocation"]["args"],list) and len(b["invocation"]["budget"])==4,"invalid invocation shape")
            for n in b["invocation"]["budget"]: unsigned(n)
        keys(doc["producer"],["name","version","materialisation"],context="producer")
        keys(doc["producer"]["materialisation"],["llvm_version","pipeline","normaliser_version"],context="materialisation")
        for hash_,region in doc["regions"].items():
            require(re.fullmatch(r"[0-9a-f]{64}",hash_),"invalid region hash")
            keys(region,["kind","signature","bounds","frame","resources","gates_used","claims","verification","cleanup","error","definedness_assumptions"],["estimate"],"certificate region")
            cls.frame(region["frame"])
            if "estimate" in region:
                est=region["estimate"]
                keys(est,["precision_digits","exact_resources"],context="estimate")
                require(est["precision_digits"]==34,"K12: precision must be 34")
                exact=cls.exact_rows(est["exact_resources"])
                require(region["resources"]=={n:decimal_up(q) for n,q in exact.items()},"K12: rational/display/key mismatch")
            else:
                for q in region["resources"].values(): require(rational(q)>=0,"negative resource")
            for gate in region["gates_used"].values():
                keys(gate,["count"],["scheme","epsilon"],"gates_used")
                integer(gate["count"],0)
            claims=region["claims"]
            require(isinstance(claims,list),"claims must be array")
            for claim in claims:
                kind=claim.get("kind")
                required={"exhaustive":["domain","expected","subject"],"sampled":["domain","expected","subject","sampler"],"structural":["rule","subclaims","witness"],"numerical":["subject","metric","precision_bits","bound"],"channel":["subject","metric","precision_bits","bound","dual"]}
                require(kind in required,"unknown claim kind")
                keys(claim,["kind",*required[kind]],["label","invocation"],"claim")
                if kind=="sampled":
                    require(claim.get("label","evidence")=="evidence","§12.1: sampled claim is always evidence")
                    keys(claim["sampler"],["algorithm","seed","count"],context="sampler")
                    require(claim["sampler"]["algorithm"]=="xoshiro256**" and len(claim["sampler"]["seed"])==4,"invalid sampler")
                    require(any(unsigned(n) for n in claim["sampler"]["seed"]),"all-zero sampler seed")
                if "subject" in claim:
                    keys(claim["subject"],["closure_hash","variant","inherited_controls"],["schedule_hash"],"subject")
                    if kind in ["numerical","channel"] or claim.get("expected")=="oracle": require("schedule_hash" in claim["subject"],"K13: realised claim lacks schedule hash")
                if kind in ["numerical","channel"]: require(rational(claim["bound"])>=0,"negative error bound")
            verification=region["verification"]
            keys(verification,["oracle","borrow_frames","inverse_pairs","unitary","channel","fault_rate"],context="verification")
            indices=[verification["oracle"]] if verification["oracle"] is not None else []
            for group in ["borrow_frames","unitary","channel"]: indices+=verification[group]
            for pair in verification["inverse_pairs"]:
                keys(pair,["g","ginv","claim","budget"],["arg_tokens"],"inverse pair")
                indices.append(pair["claim"])
            for i in indices: require(isinstance(i,int) and 0<=i<len(claims),"claim index outside claims array")
        keys(doc["composition"],["multiplicities","epsilon_total","method"],context="composition")
        require(doc["composition"]["method"]=="sum_over_multiplicities","unknown composition method")
        for n in doc["composition"]["multiplicities"].values(): integer(n,0)
        return cls(doc)

    def check_resource_rows(self,result):
        b=self.doc["bindings"]
        for name in ["object_hash","interface_hash","closure_hash","target_hash","schedule_hash"]:
            require(b.get(name)==result[name],f"certificate {name} mismatch")
        require(b.get("invocation")==result["invocation"],"certificate invocation mismatch")
        region=self.doc["regions"].get(result["closure_hash"])
        require(region is not None and "estimate" in region,"certificate has no bound K12 estimate")
        require(region["resources"]==result["resources"] and region["estimate"]["exact_resources"]==result["exact_resources"],"certificate resources differ from independently reconstructed cost")
        return "resource_rows_verified; correctness_claims_not_checked"


def main(argv=None):
    parser=argparse.ArgumentParser(prog="bennett-estimate",description="ISA 0.9 resource estimator, exact rational arithmetic; JSON on stdout")
    parser.add_argument("object",type=Path)
    parser.add_argument("--target",type=Path,required=True)
    parser.add_argument("--region",help="required for objects with multiple executable definitions")
    parser.add_argument("--params",default="[]",help="complete K13 JSON array, or @file")
    parser.add_argument("--budget",default="0,0,0,0",help="B,heap,stack,depth (default is the explicit zero tuple)")
    parser.add_argument("--variant",default="forward")
    parser.add_argument("--inherited-controls",type=int,default=0)
    parser.add_argument("--certificate",type=Path,help="read certificate and cross-check K12 resources; does not verify correctness claims")
    parser.add_argument("--classical-step-bound",type=int,help="conditional upper bound for purely classical objects; termination assumption is reported")
    a=parser.parse_args(argv)
    try:
        obj=Object.read(a.object.read_text())
        target=Target.read(a.target.read_text())
        candidates=[f.name for f in obj.functions.values() if f.kind!="lproc"]
        region=a.region or (candidates[0] if len(candidates)==1 else None)
        require(region is not None,"multiple entry regions: supply --region")
        params=loads(Path(a.params[1:]).read_text() if a.params.startswith("@") else a.params)
        budget=a.budget.split(",")
        result=estimate(obj,target,region,params,budget,a.variant,a.inherited_controls,a.classical_step_bound)
        if a.certificate:
            result["certificate_status"]=Certificate.read(a.certificate.read_text()).check_resource_rows(result)
        print(jcs(result))
        return 0
    except (ContractError,OSError,ValueError,KeyError,TypeError,RecursionError) as ex:
        print(f"bennett-estimate: {ex}",file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
