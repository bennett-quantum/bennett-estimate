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
from enum import Enum, auto
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

if hasattr(sys,"set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)


class ContractError(ValueError):
    pass


class BudgetConstraintError(ContractError):
    """A well-formed tuple exceeds the reversible machine's budget bounds."""


class _IndexFoldDeclined(Exception):
    """A valid construction needs literal traversal instead of index folding."""


def require(condition, message):
    if not condition:
        raise ContractError(message)


def keys(value, required, optional=(), context="record"):
    require(isinstance(value, dict), f"{context}: expected object")
    expected=set(required)
    if not expected <= value.keys():
        raise ContractError(f"{context}: missing {expected - value.keys()}")
    allowed=expected | set(optional)
    if not value.keys() <= allowed:
        raise ContractError(f"{context}: unknown {value.keys() - allowed}")


def rational(value):
    if type(value) is int:return value
    if type(value) is F:return value.numerator if value.denominator==1 else value
    require(not isinstance(value, bool), "boolean is not a number")
    require(isinstance(value, (int, Decimal, F, str)), "expected exact rational")
    try:
        result=F(value)
        return result.numerator if result.denominator==1 else result
    except (ValueError, ZeroDivisionError, OverflowError) as ex:
        raise ContractError(f"invalid rational: {value}") from ex


def integer(value, minimum=None):
    if type(value) is int:
        if minimum is not None and value<minimum:
            raise ContractError(f"integer below {minimum}: {value}")
        return value
    q = rational(value)
    if q.denominator != 1:raise ContractError(f"expected integer, got {value}")
    n = q.numerator
    if minimum is not None and n<minimum:raise ContractError(f"integer below {minimum}: {n}")
    return n


def decimal_value(value):
    require(isinstance(value,(str,int,Decimal)) and not isinstance(value,bool),"expected decimal number/text")
    if isinstance(value,str):
        require(re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?",value),"expected decimal text, not a rational fraction")
        value=Decimal(value)
    return rational(value)


def exact_decimal(value):
    q=rational(value);denominator=q.denominator;twos=fives=0
    while denominator%2==0:denominator//=2;twos+=1
    while denominator%5==0:denominator//=5;fives+=1
    require(denominator==1,"request accuracy must have a finite decimal encoding")
    digits=max(twos,fives)
    coefficient=q.numerator*2**(digits-twos)*5**(digits-fives)
    if not digits:return str(coefficient)
    sign="-" if coefficient<0 else "";s=str(abs(coefficient)).rjust(digits+1,"0")
    return sign+(s[:-digits]+"."+s[-digits:]).rstrip("0").rstrip(".")


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


def width_expression(value):
    """B5 widths stay exact without JSON integer literals at/above 2^53."""
    value=integer(value,0)
    if value<2**53:return value
    high,low=divmod(value,2**26)
    product={"op":"*","args":[width_expression(high),2**26]}
    return {"op":"+","args":[product,low]} if low else product


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


def is_image(value):
    return isinstance(value,str) and len(value)%2==0 and re.fullmatch(r"[0-9a-f]*",value) is not None


@lru_cache(maxsize=4096)
def jcs_string(value):
    require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "JCS: lone surrogate")
    return json.dumps(value,ensure_ascii=False,separators=(",",":"))


def jcs(value):
    """RFC 8785 key order and ECMAScript finite number spelling.

    Decimal values retain their input rational for calculations. Conversion to
    binary64 here is exclusively for checking canonical interchange bytes.
    """
    if value is None: return "null"
    if value is True: return "true"
    if value is False: return "false"
    if isinstance(value,str):return jcs_string(value)
    if isinstance(value,int):
        return str(value) if abs(value)<2**53 else jcs(Decimal(value))
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


def metadata_counts(value):
    """Generated metadata uses decimal strings before JCS loses integer bits."""
    if type(value) is int and abs(value)>=2**53:return str(value)
    if isinstance(value,(tuple,list)):return [metadata_counts(v) for v in value]
    if isinstance(value,dict):return {k:metadata_counts(v) for k,v in value.items()}
    return value


_BYTE_POPCOUNTS=bytes(value.bit_count() for value in range(256))


def image_ones(image,start,end):
    """Count a bit interval in input-sized chunks, never an emitted gate list."""
    if start==end:return 0
    first,low=divmod(start,8);last,high=divmod(end,8)
    if first==last:return ((int(image[2*first:2*first+2],16)>>low)&((1<<(end-start))-1)).bit_count()
    total=0
    if low:
        total+=(int(image[2*first:2*first+2],16)>>low).bit_count();first+=1
    if high:total+=(int(image[2*last:2*last+2],16)&((1<<high)-1)).bit_count()
    for offset in range(2*first,2*last,8192):
        total+=sum(bytes.fromhex(image[offset:min(offset+8192,2*last)]).translate(_BYTE_POPCOUNTS))
    return total


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
        return rational(F(a) / b)
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
    inexact_operations: int = 0

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
                       add_maps(self.gates, other.gates), self.error + other.error,self.inexact_operations+other.inexact_operations)

    def repeat(self, n):
        n = integer(n, 0)
        if n == 0: return Profile()
        return Profile(self.time*n, {k: v*n for k,v in self.counts.items()},
                       {k: v*n for k,v in self.delta.items()},
                       {k: v + max(0, (n-1)*self.delta.get(k, 0)) for k,v in self.peak.items()},
                       {k: self.area.get(k, 0)*n + v*self.time*(n*(n-1)//2) for k,v in self.delta.items()},
                       {k: v*n for k,v in self.gates.items()}, self.error*n,self.inexact_operations*n)

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

    @staticmethod
    def number(value):
        require(isinstance(value,(int,Decimal)) and not isinstance(value,bool),"§8.1: target field requires a JSON number")
        return rational(value)

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
                require(c in d["classes"] and cls.number(n) >= 0, "invalid resource class/rate")
        for name, kind in [("time", "time"), ("qubit_second", "occupancy"), ("peak_qubits", "peak")]:
            require(d["resources"].get(name, {}).get("kind") == kind, f"missing mandatory {name}")
        for c in d["classes"].values():
            keys(c, ["qubit_second", "dirty_rate", "capacity"], context="class")
            require(cls.number(c["qubit_second"]) >= 0 and cls.number(c["dirty_rate"]) >= 0, "negative class rate")
            if c["capacity"] != "unbounded": integer(cls.number(c["capacity"]), 0)
        for width in d["ptr_widths_supported"]: integer(cls.number(width), 1)
        caps = d["capabilities"]
        keys(caps, ["measurement", "mbu", "max_parallel", "max_predicate_depth", "classical_step_time"], context="capabilities")
        keys(caps["measurement"], ["mid_circuit", "feedforward_latency"], context="measurement")
        require(caps["mbu"] is False, "§6.4: mbu is reserved false")
        require(isinstance(caps["measurement"]["mid_circuit"], bool), "invalid measurement capability")
        require(cls.number(caps["classical_step_time"]) >= 0 and cls.number(caps["measurement"]["feedforward_latency"]) >= 0, "negative latency")
        for k in ["max_parallel", "max_predicate_depth"]:
            if caps[k] != "unbounded": integer(cls.number(caps[k]), 0)
        for name, values in d["tables"].items():
            require(isinstance(values, list), "table must be array")
            for n in values: require(cls.number(n) >= 0, "negative table value")
        for gate in d["gates"]:
            keys(gate, ["op", "classes", "controls", "epsilon", "cost"], ["params", "realisation_model"], "gate")
            if "realisation_model" in gate:
                model = gate["realisation_model"]
                require(isinstance(model, dict) and isinstance(model.get("version"), str), "K86: native model needs a version")
                if model["version"] == "bennett.native-model/1":
                    keys(model, ["version", "kind", "arity", "basis", "parameter_bindings", "control_models", "data", "operand_map"], context="native model")
                    require(model["kind"] == "unitary", "K86: native model must identify a phase-bearing unitary")
                # Model bytes bind target_hash. Resource estimation consumes
                # costs, not matrices; numerical model obligations belong to
                # the independent checker and are never claimed here.
            require(gate["op"] in GATES or gate["op"] == "mcx", "unknown gate")
            require(gate.get("params", []) == (["theta"] if gate["op"] in ["rx", "ry", "rz"] else []), "gate parameter arity")
            require(gate["classes"] and all(c == "*" or c in d["classes"] for c in gate["classes"]), "unknown gate class")
            keys(gate["controls"], ["min", "max"], context="controls")
            low = integer(cls.number(gate["controls"]["min"]), 0)
            if gate["controls"]["max"] != "unbounded": integer(cls.number(gate["controls"]["max"]), low)
            require("time" in gate["cost"], "gate cost needs time")
            require(set(gate["cost"]) <= d["resources"].keys(), "undeclared resource cost")
            # Expression syntax/bindings are checked even for unreachable entries.
            cls.validate_expr(gate["epsilon"], {"k", "c", "eps"}, d["tables"])
            exact = gate["epsilon"] == 0
            for expr in [gate["epsilon"], *gate["cost"].values()]:
                cls.validate_expr(expr, {"k", "c", "eps"}, d["tables"])
                if exact: require(not cls.epsilon_dependent(expr), "§8.1/K9: exact entry depends on epsilon")
                if not isinstance(expr, dict): require(rational(expr) >= 0, "negative cost/epsilon")
        scheme_names=set()
        for scheme in d["schemes"]:
            keys(scheme, ["name", "realises", "ancillae", "template"], context="scheme")
            require(isinstance(scheme["name"],str) and scheme["name"] and scheme["name"] not in scheme_names,"duplicate/empty scheme name")
            scheme_names.add(scheme["name"])
            keys(scheme["realises"], ["op", "controls"], ["params"], "realises")
            realises=scheme["realises"]
            require(realises["op"] in GATES or realises["op"]=="mcx","unknown scheme operation")
            parametric=realises["op"] in ["rx","ry","rz"]
            require(realises.get("params",[])==(["theta"] if parametric else []),"scheme parameter arity")
            keys(realises["controls"],["min","max"],context="scheme controls")
            low=integer(cls.number(realises["controls"]["min"]),0)
            if realises["controls"]["max"]!="unbounded":integer(cls.number(realises["controls"]["max"]),low)
            scheme_bound={"k","c"}|({"theta"} if parametric else set())
            keys(scheme["ancillae"], ["count", "state", "class"], context="ancillae")
            require(scheme["ancillae"]["state"] in ["clean", "dirty"] and scheme["ancillae"]["class"] in d["classes"], "invalid ancillae")
            cls.validate_expr(scheme["ancillae"]["count"], scheme_bound, d["tables"])
            for leaf in scheme["template"]:
                keys(leaf, ["gate", "wires"], ["params", "repeat"], "scheme leaf")
                op=leaf["gate"]
                require(op in GATES and len(leaf["wires"])==GATES[op] or op=="mcx" and len(leaf["wires"])>=1,"scheme leaf gate arity/opcode")
                require(len(leaf.get("params",[]))==(1 if op in ["rx","ry","rz"] else 0),"scheme leaf parameter arity")
                bound=scheme_bound|({"i"} if "repeat" in leaf else set())
                for w in leaf["wires"]:
                    if w in ["t","t2"]:continue
                    match=re.fullmatch(r"[ca]\[(.*)\]",w);require(match,"invalid scheme wire")
                    cls.validate_expr(loads(match[1]),bound,d["tables"])
                for parameter in leaf.get("params",[]):
                    cls.validate_expr(parameter,({"theta"} if parametric else set())|({"i"} if "repeat" in leaf else set()),d["tables"])
                if "repeat" in leaf:
                    keys(leaf["repeat"], ["var", "from", "to"], context="repeat")
                    require(leaf["repeat"]["var"] == "i", "invalid repeat variable")
                    for k in ["from","to"]:cls.validate_expr(leaf["repeat"][k],scheme_bound,d["tables"])
        if "topology" in d:
            top = d["topology"]
            keys(top, ["vertices", "edges"], context="topology")
            for v in top["vertices"]:
                keys(v, ["class"], context="vertex")
                require(v["class"] in d["classes"], "unknown vertex class")
            previous = [-1, -1]
            for edge in top["edges"]:
                require(len(edge) == 2, "invalid edge")
                u, v = (integer(cls.number(n), 0) for n in edge)
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
            require(isinstance(names,dict),"weighted objective must be object")
            for n in names.values(): require(cls.number(n) >= 0, "negative objective weight")
        else:require(isinstance(names,list),"lexicographic objective must be array")
        require(isinstance(d["imports"],dict),"target imports must be object")
        for model,record in d["imports"].items():
            keys(record,["version","map"],context="target import")
            require(isinstance(record["version"],str) and isinstance(record["map"],dict),"invalid target import version/map")
            for value in record["map"].values():
                require(isinstance(value,list) and len(value)==2 and value[0] in d["resources"],"invalid imported quantity mapping")
                require(cls.number(value[1])>=0,"negative imported quantity factor")
        return cls(d, digest(text if canonical else jcs(d)))

    @staticmethod
    def epsilon_dependent(expr):
        if not isinstance(expr, dict): return False
        return expr.get("var") == "eps" or expr.get("op") == "log2inv_eps" or expr.get("index") == "eps_decade" or any(Target.epsilon_dependent(x) for x in expr.get("args", []))

    def native_model_obligations(self):
        """Cost reconstruction never establishes a realised-unitary claim."""
        return [{"gate_entry": index, "version": gate["realisation_model"]["version"],
                 "status": "unchecked" if gate["realisation_model"]["version"] == "bennett.native-model/1" else "unsupported-model"}
                for index, gate in enumerate(self.doc["gates"]) if "realisation_model" in gate]

    @staticmethod
    def validate_expr(expr, bound, tables):
        if not isinstance(expr, dict):
            Target.number(expr)
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

    def native_gate(self,op,classes,controls,eps,own):
        values=self._native_values(op,tuple(classes),controls,rational(eps),own)
        if values is None:return None
        duration,counts,achieved=values
        return Profile(time=duration,counts=dict(counts),gates={op:1},error=achieved)

    @lru_cache(maxsize=4096)
    def _native_values(self,op,classes,controls,eps,own):
        # The target is validated/hash-bound and immutable during an estimate.
        # Cache scalar values, not mutable Profile maps returned to callers.
        env={"k":F(own),"c":F(controls),"eps":rational(eps)}
        for g in self.doc["gates"]:
            if not self.covers(g,op,controls):continue
            pattern=g["classes"]
            if not (len(pattern)==1 and all(pattern[0] in ["*",c] for c in classes) or len(pattern)==len(classes) and all(p in ["*",c] for p,c in zip(pattern,classes))):continue
            achieved=expression(g["epsilon"],env,self.doc["tables"])
            require(achieved>=0,"negative achieved epsilon")
            if achieved>eps:continue
            costs={n:expression(x,env,self.doc["tables"]) for n,x in g["cost"].items()}
            require(all(v>=0 for v in costs.values()),"§8.1: negative evaluated cost")
            return costs["time"],tuple((n,v) for n,v in costs.items() if self.doc["resources"][n]["kind"]=="count"),achieved
        return None

    @staticmethod
    def covers(entry,op,controls):
        r=entry["controls"]
        return entry["op"]==op and controls>=integer(r["min"],0) and (r["max"]=="unbounded" or controls<=integer(r["max"],0))

    def exact_native(self,op,classes,controls,own):
        return self._exact_native(op,tuple(classes),controls,own)

    @lru_cache(maxsize=4096)
    def _exact_native(self,op,classes,controls,own):
        for g in self.doc["gates"]:
            if not self.covers(g,op,controls) or self.epsilon_dependent(g["epsilon"]):continue
            pattern=g["classes"]
            if not (len(pattern)==1 and all(pattern[0] in ["*",c] for c in classes) or len(pattern)==len(classes) and all(p in ["*",c] for p,c in zip(pattern,classes))):continue
            if expression(g["epsilon"],{"k":F(own),"c":F(controls)},self.doc["tables"])==0:return True
        return False

    def gate(self, op, classes, controls, eps=F(0), own=None, theta=None, native_only=False):
        own = {"cx": 1, "ccx": 2, "mcx": len(classes)-1}.get(op, 0) if own is None else own
        env = {"k": F(own), "c": F(controls), "eps": rational(eps)}
        if theta is not None:env["theta"]=angle(theta)
        def covers(entry):
            r = entry["controls"]
            return entry["op"] == op and controls >= r["min"] and (r["max"] == "unbounded" or controls <= r["max"])
        native=self.native_gate(op,classes,controls,eps,own)
        if native is not None:return native
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
                    parameters=[expression(x,context,self.doc["tables"]) for x in leaf.get("params",[])]
                    for parameter in parameters:angle(parameter)
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
                    out = out.then(self.gate(leaf_op, wire_classes, c, eps, theta=parameters[0] if parameters else None,native_only=True))
            return out.then(space_profile(anc["class"], state, -n))
        raise ContractError(f"E_GATE_UNSUPPORTED: {op}, c={controls}, classes={classes}, eps={eps}")


def space_profile(cls, state, n):
    p = Profile.allocation(cls, state, n)
    p.delta[(cls, "total")] = n
    p.peak[(cls, "total")] = max(n, 0)
    return p


def angle(value):
    """The exact rational value of a finite binary64 source angle."""
    if isinstance(value,str) and re.fullmatch(r"0x[0-9a-f]{16}",value):
        import struct
        value=struct.unpack(">d",bytes.fromhex(value[2:]))[0]
    number=float(value)
    require(math.isfinite(number),"nonfinite rotation angle")
    return F(value) if isinstance(value,F) else F(number)


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

    def slice(self,start,end):
        require(0<=start<=end<=self.width,"invalid bundle slice")
        return Bundle(self.identity,end-start,self.cls,self.offset+start,self.state)


class WireVersions:
    """Immutable interval values for source versions, without wire arrays."""
    def __init__(self):self.ranges={}

    def acquire(self,b):
        require(b.width>0 and b.identity not in self.ranges,"version lifetime is already live or empty")
        self.ranges[b.identity]=((b.offset,b.offset+b.width,0,True),)

    def capture(self,parts):
        requests={}
        for b in parts:
            if b.width:requests.setdefault(b.identity,[]).append((b.offset,b.offset+b.width))
        result=[]
        for identity,intervals in sorted(requests.items()):
            merged=[]
            for lo,hi in sorted(intervals):
                if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
                else:merged.append((lo,hi))
            for lo,hi in merged:
                covered=0
                for begin,end,version,clean in self.ranges.get(identity,()):
                    a,b=max(lo,begin),min(hi,end)
                    if a<b:result.append((identity,a,b,version,clean));covered+=b-a
                require(covered==hi-lo,"source version references an inactive wire range")
        return tuple(result)

    def restore(self,snapshot):
        for identity,lo,hi,version,clean in snapshot:
            parts=[];covered=0
            for begin,end,old_version,old_clean in self.ranges.get(identity,()):
                a,b=max(lo,begin),min(hi,end)
                if a>=b:parts.append((begin,end,old_version,old_clean));continue
                if begin<a:parts.append((begin,a,old_version,old_clean))
                parts.append((a,b,version,clean));covered+=b-a
                if b<end:parts.append((b,end,old_version,old_clean))
            require(covered==hi-lo,"restored version references an inactive wire range")
            merged=[]
            for part in parts:
                if merged and merged[-1][1]==part[0] and merged[-1][2:]==part[2:]:merged[-1]=(merged[-1][0],part[1],*part[2:])
                else:merged.append(part)
            self.ranges[identity]=tuple(merged)

    def assign(self,parts,version,clean=None):
        self.restore((identity,lo,hi,version,old_clean if clean is None else clean) for identity,lo,hi,old_version,old_clean in self.capture(parts))


@dataclass(frozen=True)
class RecordField(Bundle):
    """Logical field array over packed records; owns no additional wires."""
    element_width: int = 1
    record_width: int = 1
    logical_from: int = 0

    def positions(self):
        for index in range(self.logical_from,self.logical_from+self.width):
            entry,bit=divmod(index,self.element_width)
            yield self.offset+entry*self.record_width+bit

    def bit(self,index):
        require(0<=index<self.width,"record field index outside width")
        entry,bit=divmod(self.logical_from+index,self.element_width)
        return Bundle(self.identity,1,self.cls,self.offset+entry*self.record_width+bit,self.state)

    def slice(self,start,end):
        require(0<=start<=end<=self.width,"invalid record field slice")
        return RecordField(self.identity,end-start,self.cls,self.offset,self.state,self.element_width,self.record_width,self.logical_from+start)


@dataclass
class Captured:
    body: list
    env: dict
    controls: tuple
    cleanup: bool = False
    recompute: object = None
    builder: object = None
    loop_plan: object = None
    owned_points: tuple = ()


@dataclass(frozen=True)
class CapturedRecords:
    schema: str
    shape: tuple
    records: tuple
    summaries: dict = field(default_factory=dict,compare=False)

    def __iter__(self):return iter(self.records)
    def __len__(self):return len(self.records)
    def __getitem__(self,index):return self.records[index]


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


@lru_cache(maxsize=2048)
def wire_index(text):
    # Subscript ASTs are read-only interpreter input, never environment maps.
    return loads(text)


def wire(x, env):
    if isinstance(x, Bundle): return [x]
    if isinstance(x, (list,tuple)): return [w for part in x for w in wire(part, env)]
    if isinstance(x, dict):
        if set(x) == {"range", "from", "to"}:
            bundle = wire(x["range"], env)
            require(len(bundle) == 1, "K19: range needs one contiguous bundle")
            b = bundle[0]
            lo, hi = scalar(x["from"], env), scalar(x["to"], env)
            require(0 <= lo <= hi <= b.width, "K19: invalid wire range")
            return [b.slice(lo,hi)]
        if "cells" in x: return wire(x["cells"], env)
    require(isinstance(x, str), "K19: invalid wire actual")
    match = re.fullmatch(r"([^\[]+)\[(.*)\]", x)
    if match:
        b = wire(match[1], env)
        index = scalar(wire_index(match[2]), env)
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
    return tuple((b.identity, i, b.cls) for b in wires for i in (b.positions() if isinstance(b,RecordField) else range(b.offset,b.offset+b.width)))


_BINDING_SCOPE=object()


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
        self.text=text
        self.stack = []
        self.symbols = {}
        self.eps = F(0)
        self.count_only=False
        self.require_exact=False
        self.closed_form = True
        self.ledger=None
        self.source_metadata={}
        self.source_context=None
        self.call_edges=()
        self.call_domains={}
        self.prebound_interfaces=False
        self.loop_coordinates=[]
        self.source_ordinals={}
        self.address_cache=None
        self.reverse_limits=None
        self.raw_limits=None;self.raw_cursors={}
        self.region_raw=False;self.region_oracle=False
        self.root_step=None;self.root_phase=None
        self.binding_serial=0
        self.allocation_scopes={}
        self.used_allocations=set()
        self.inverse_declarations=set()
        self.named_interfaces={}
        self.record_schemas={}
        self.default_class=next(iter(sorted(target.doc["classes"],key=lambda name:name.encode("utf-16-be"))))

    def bind(self, formals, actuals, caller, controls):
        require(len(formals) == len(actuals), "K19: recipe argument arity")
        env = {}
        seen = set()
        for formal, actual in zip(formals, actuals):
            name = formal if isinstance(formal, str) else formal["name"]
            require(name not in seen, "duplicate formal")
            seen.add(name)
            kind = "integer" if isinstance(formal, str) else formal["type"]
            if kind == "integer": value = integer(scalar(actual, caller))
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
            elif kind=="records":
                keys(formal,["name","type","fields","order"],context="K25 records formal")
                fields=formal["fields"];order=formal["order"]
                require(isinstance(fields,list) and isinstance(order,list),"K25: invalid records schema")
                names=[f if isinstance(f,str) else f["name"] for f in fields]
                types={n:("integer" if isinstance(f,str) else f["type"]) for n,f in zip(names,fields)}
                require(len(set(names))==len(names) and len(set(order))==len(order) and all(types.get(n)=="integer" for n in order),"K25: invalid record field/order names")
                require(all(t in ["integer","wire","region","class","allocation","image"] for t in types.values()),"K25: invalid record field type")
                reusable=all(t in ["integer","wire"] for t in types.values())
                schema,dependencies=self.record_schema(formal) if reusable else (None,())
                captured_shape=tuple((n,scalar(n,env)) for n in dependencies)
                records=caller[actual] if isinstance(actual,str) else actual
                if isinstance(records,CapturedRecords):
                    if reusable and (records.schema,records.shape)==(schema,captured_shape):
                        env[name]=records;continue
                    records=[dict(record) for record in records]
                require(isinstance(records,list),"K25: records actual must be array")
                value=[];previous=None
                for record in records:
                    keys(record,names,context="K25 record")
                    resolved={};integers={}
                    for field,n in zip(fields,names):
                        shape=dict(env,**integers);lexical=dict(caller,**integers)
                        receiving=field
                        if isinstance(field,dict):
                            receiving=dict(field)
                            for parameter in ["width","address","cell"]:
                                if parameter in receiving:receiving[parameter]=integer(scalar(receiving[parameter],shape),0)
                        captured,_=self.bind([receiving],[record[n]],lexical,())
                        resolved[n]=captured[n]
                        if types[n]=="integer":integers[n]=resolved[n]
                    key=tuple(resolved[n] for n in order)
                    require(not order or previous is None or previous<key,"K25: record order must be strictly increasing")
                    previous=key;value.append(resolved)
                if reusable:
                    value=CapturedRecords(schema,captured_shape,tuple(MappingProxyType({n:tuple(v) if types[n]=="wire" else v for n,v in record.items()}) for record in value))
            elif kind in ["angle", "image", "symbol", "class", "event", "allocation", "value", "arguments", "region"]:
                value = caller.get(actual, actual) if isinstance(actual, str) else actual
                if kind == "allocation": require(isinstance(value, Bundle), "K27: invalid allocation handle")
                if kind == "image": require(is_image(value), "K21: invalid image")
                if kind == "angle": require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-f]{16}", value) and (int(value[2:],16)>>52)&2047 != 2047, "K20: invalid angle")
                if kind == "region":
                    require(isinstance(value, dict), "K26: invalid region")
                    keys(value, ["address", "cell", "role", "origin", "cells"], context="region actual")
                    require(value["address"] == scalar(formal["address"],env) and value["cell"] == scalar(formal["cell"],env) and value["role"] == formal["role"], "K26: region shape/role mismatch")
                    require(value["origin"].startswith(("local:","interface:")) and value["origin"].split(":",1)[1], "K26: invalid origin")
                    require(sum(b.width for b in wire(value["cells"], caller)) == (1 << value["address"])*value["cell"], "K26: cells width mismatch")
                    value={**value,"cells":wire(value["cells"],caller)}
            else: raise ContractError(f"unknown formal type {kind}")
            env[name] = value
        return env, controls

    def record_schema(self,formal):
        schema=jcs({k:v for k,v in formal.items() if k!="name"})
        if schema not in self.record_schemas:
            variables=set();integers=set()
            def collect(expr):
                if isinstance(expr,str):
                    if expr not in integers:variables.add(expr)
                elif isinstance(expr,list):
                    for item in expr[1:]:collect(item)
            for field in formal["fields"]:
                if isinstance(field,str):integers.add(field)
                elif field["type"]=="integer":integers.add(field["name"])
                else:
                    for key in ["width","address","cell"]:
                        if key in field:collect(field[key])
            self.record_schemas[schema]=tuple(sorted(variables))
        return schema,self.record_schemas[schema]

    def named_interface(self,name):
        """K82 free wire names, ordered by lexical use (not caller contents)."""
        identity=(name,id(self.recipes[name]["body"]))
        if identity in self.named_interfaces:return self.named_interfaces[identity]
        result=[]
        def use(value,bound):
            if isinstance(value,list):
                for item in value:use(item,bound)
            elif isinstance(value,dict):
                if "range" in value:use(value["range"],bound)
            elif isinstance(value,str):
                base=value.split("[",1)[0]
                if base not in bound and base not in result:result.append(base)
        def walk(nodes,bound):
            bound=set(bound)|{node["alloc"] for node in nodes if "alloc" in node}
            for node in nodes:
                for key in ["wires","under","release","acquire","relinquish","in"]:
                    if key in node:use(node[key],bound)
                if "invoke" in node:
                    callee=self.recipes[node["invoke"]]
                    if all(isinstance(f,str) for f in callee["parameters"]):
                        for n in self.named_interface(node["invoke"]):use(n,bound)
                    else:
                        for formal,actual in zip(callee["parameters"],node["args"]):
                            if isinstance(formal,dict) and formal["type"] in ["wire","environment","allocation"]:use(actual,bound)
                if "body" in node:walk(node["body"],bound|{node[k] for k in ["for","each","declare"] if k in node})
        walk(self.recipes[name]["body"],set(self.recipes[name]["parameters"]))
        self.named_interfaces[identity]=result
        return result

    def recipe(self, name, args, env=None, controls=(), inverse=False,invoked=False):
        require(name in self.recipes, f"unknown reference recipe {name}")
        # The pinned recipe dependency graph is acyclic. A finite captured
        # body may invoke the same higher-order recipe again (K19), e.g.
        # qloop(7,qloop(3,B)); recipe-name re-entry alone is not recursion.
        self.stack.append(name)
        try:
            r = self.recipes[name]
            bound, controls = self.bind(r["parameters"], args, env or {}, controls)
            if all(isinstance(f,str) for f in r["parameters"]):
                interface=self.named_interface(name)
                require(invoked or set(env or {})==set(interface),"K82: direct named-interface recipe needs exactly its wire-name map")
                for n in interface:bound[n]=wire(n,env or {})
            self.binding_serial+=1
            bound[_BINDING_SCOPE]=self.binding_serial
            if self.ledger is None and self.closed_form and name=="value.literal":
                p=self.literal_summary(bound,controls)
                if p is not None:return p
            if self.ledger is None and self.closed_form and name in ["dispatch.copy","dispatch.store","dispatch.exchange","stack.copy","stack.store","stack.exchange"] and not self.target.doc.get("topology"):
                p=self.dispatch_summary(name,bound,controls)
                if p is not None: return p
            return self.body(r["body"], bound, controls, inverse)
        finally:
            self.stack.pop()

    def literal_summary(self,env,controls):
        n=integer(env["N"],0);value=env["C"];targets=wire(env["t"],env)
        if not n:return Profile()
        require(value>=0,"K23: negative bit operand")
        if any(control[0]==b.identity for control in controls for b in targets):return None
        out=Profile();offset=0;size=value.bit_length()
        for b in targets:
            selected=value>>offset if offset<size else 0
            if selected.bit_length()>b.width:selected&=(1<<b.width)-1
            count=selected.bit_count()
            if count:out=out.then(self.gate_event("x",[b.bit(0)],controls).repeat(count))
            offset+=b.width
        return out

    def dispatch_summary(self,name,env,controls):
        stack=name.startswith("stack.")
        A,C,W=(env["S"],env["C"],env["N"]) if stack else (env["A"],env["C"],env["W"])
        stride=env["K"] if stack else W
        require(C>=0 and (C==0 or (C-1).bit_length()<=A) and (0<=W<=stride if stack else W>0),"invalid address dispatch shape")
        cells=wire(env["stack" if stack else "cells"],env)
        value=wire(env["v"],env)
        if len(cells)!=1 or len(value)!=1 or isinstance(cells[0],RecordField) or isinstance(value[0],RecordField):return None
        if C==0: return Profile()
        cell,value=cells[0],value[0]
        # Index renaming must preserve effective control multiplicities and
        # operand distinctness, including an alias in a later physical cell.
        if any(identity==b.identity and b.offset<=index<b.offset+b.width for identity,index,_ in controls for b in [cell,value]):return None
        if cell.identity==value.identity and max(cell.offset,value.offset)<min(cell.offset+cell.width,value.offset+value.width):return None
        # Literal equality inputs vary by address; their total X count has an
        # exact binary digit sum. The comparator and each cell operation are
        # invariant under renaming homogeneous cell wires.
        self.serial+=1
        counter=Bundle(f"dispatch:{self.serial}:counter",A,self.default_class)
        eq=Bundle(f"dispatch:{self.serial}:eq",1,self.default_class)
        address=env["address" if stack else "a"]
        compare=self.recipe("bind.value.icmp.eq",[A,address,counter,eq],env,controls)
        uncompare=self.recipe("bind.value.icmp.eq",[A,address,counter,eq],env,controls,True)
        leaf="swap" if name.endswith(".exchange") else "cx"
        joined=tuple(dict.fromkeys(controls+bits([eq])))
        data=Profile()
        if W:
            ws=[value.bit(0),cell.bit(0)] if name.endswith(".store") else [cell.bit(0),value.bit(0)]
            data=self.body([{"gate":leaf,"wires":ws}],env,joined).repeat(W)
        base=space_profile(counter.cls,"clean",A).then(space_profile(eq.cls,"clean",1)).then(compare).then(data).then(uncompare).then(space_profile(eq.cls,"clean",-1)).then(space_profile(counter.cls,"clean",-A))
        p=base.repeat(C)
        ones=sum((C>>(b+1))*(1<<b)+max(0,C% (1<<(b+1))-(1<<b)) for b in range(min(A,C.bit_length())))
        if ones:
            literal=space_profile(counter.cls,"clean",A).then(self.gate_event("x",[counter.bit(0)],controls,own=0)).then(space_profile(counter.cls,"clean",-A))
            p=p.then(literal.repeat(2*ones))
        return p

    def table_entry_summary(self,node,env,controls,inverse):
        """Exact affine cost in the address literal's binary digit count.

        These pinned scan bodies use entry only as a homogeneous field index
        or as value.literal(T,entry). All entry-local storage is balanced;
        no allocation width, gate parameter or control class depends on entry.
        Repeated literal Xs add duration/count/area while reusing workspace.
        """
        if not self.stack or self.stack[-1] not in ["scan.inrange","scan.free.flag","lift.free"]:return None
        if node["for"]!="entry" or node["from"]!=0 or node["to"]!="C":return None
        moving=[part for name in ["base","size","live","pinned"] for part in wire(env[name],env)]
        if any(len(wire(env[name],env))!=1 for name in ["base","size","live","pinned"]):return None
        if any(identity==part.identity for identity,_,_ in controls for part in moving):return None
        C=integer(env["C"],0)
        if not C:return Profile()
        zero=self.body(node["body"],dict(env,entry=0),controls,inverse)
        if C==1:return zero
        one=self.body(node["body"],dict(env,entry=1),controls,inverse)
        ones=sum((C>>(bit+1))*(1<<bit)+max(0,C%(1<<(bit+1))-(1<<bit)) for bit in range(min(integer(env["T"],0),C.bit_length())))
        return self.literal_population(zero,one,C,ones)

    @staticmethod
    def literal_population(zero,one,C,ones):
        require(all(v==0 for p in [zero,one] for v in p.delta.values()),"literal population summary needs balanced storage")
        if not ones:return zero.repeat(C)
        def total(a,b):return a*C+(b-a)*ones
        def maps(a,b):return {key:total(a.get(key,0),b.get(key,0)) for key in a.keys()|b.keys()}
        return Profile(time=total(zero.time,one.time),counts=maps(zero.counts,one.counts),
                       delta=maps(zero.delta,one.delta),peak={key:max(zero.peak.get(key,0),one.peak.get(key,0)) for key in zero.peak.keys()|one.peak.keys()},
                       area=maps(zero.area,one.area),gates=maps(zero.gates,one.gates),error=total(zero.error,one.error),
                       inexact_operations=total(zero.inexact_operations,one.inexact_operations))

    def global_delivery_summary(self,node,env,controls,inverse):
        if not self.stack or self.stack[-1]!="lift.ret" or node["visit"]!="Globals":return None
        records=env["Globals"]
        if not isinstance(records,CapturedRecords):return None
        Did=integer(env["Did"],0)
        group_key=("delivery-groups",Did)
        if group_key not in records.summaries:
            groups={};identities=set()
            for record in records:
                parts=wire(record["location"],env)
                if len(parts)!=1 or isinstance(parts[0],RecordField):return None
                location=parts[0];identities.add(location.identity)
                key=(record["width"],location.cls)
                group=groups.setdefault(key,[record,0,0]);group[1]+=1
                value=integer(record["id"],0)
                if value.bit_length()>Did:value&=(1<<Did)-1
                group[2]+=value.bit_count()
            records.summaries[group_key]=(tuple(tuple(group) for group in groups.values()),frozenset(identities))
        groups,identities=records.summaries[group_key]
        delivery=wire(env["delivery"],env);destination=wire(env["destination"],env)
        if len(delivery)!=1 or len(destination)!=1 or isinstance(delivery[0],RecordField) or isinstance(destination[0],RecordField):return None
        delivery,destination=delivery[0],destination[0]
        if delivery.identity in identities or any(identity in identities for identity,_,_ in controls):return None
        if any(record["width"]>delivery.width for record,count,ones in groups):return None
        used_width=max((record["width"] for record,count,ones in groups),default=0)
        if any(identity==delivery.identity and delivery.offset<=index<delivery.offset+used_width for identity,index,_ in controls):return None
        control_shape=tuple((cls,index-destination.offset if identity==destination.identity else None) for identity,index,cls in controls)
        profile_key=("delivery-profile",Did,self.target.hash,self.default_class,self.eps,self.count_only,self.require_exact,inverse,delivery.width,delivery.cls,destination.cls,control_shape)
        if profile_key not in records.summaries:
            out=Profile()
            for record,count,ones in groups:
                zero=self.body(node["body"],dict(env,**{**record,"id":0}),controls,inverse)
                one=self.body(node["body"],dict(env,**{**record,"id":1}),controls,inverse) if ones else zero
                out=out.then(self.literal_population(zero,one,count,ones))
            records.summaries[profile_key]=out
        return records.summaries[profile_key]

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
                raise _IndexFoldDeclined("unknown affine parameter")
            op,*args=expr
            if len(args)!=2: raise _IndexFoldDeclined("arity")
            a,b=affine(args[0]),affine(args[1])
            if op=="+": return a[0]+b[0],a[1]+b[1]
            if op=="-": return a[0]-b[0],a[1]-b[1]
            if op=="*" and not a[0]: return b[0]*a[1],b[1]*a[1]
            if op=="*" and not b[0]: return a[0]*b[1],a[1]*b[1]
            if a[0]==b[0]==0: return 0,scalar(expr,env)
            raise _IndexFoldDeclined("non-affine index")
        def mentions(x):
            if isinstance(x,str): return x==variable or '"'+variable+'"' in x
            if isinstance(x,list): return any(mentions(v) for v in x)
            if isinstance(x,dict): return any(mentions(v) for v in x.values())
            return False
        control_ids={c[0] for c in controls}
        def descriptors(actual):
            if isinstance(actual,list): return [v for a in actual for v in descriptors(a)]
            if isinstance(actual,Bundle):
                if actual.width!=1: raise _IndexFoldDeclined("bundle operand")
                return [(actual.identity,0,actual.offset)]
            if not isinstance(actual,str): raise _IndexFoldDeclined("complex wire")
            m=re.fullmatch(r"([^\[]+)\[(.*)\]",actual)
            if not m:
                bundles=wire(actual,env)
                if sum(b.width for b in bundles)>3: raise _IndexFoldDeclined("wide control bundle")
                return [(b.identity,0,b.offset+i) for b in bundles for i in range(b.width)]
            coefficient,constant=affine(loads(m[2]))
            if m[1] not in env:
                if coefficient: raise _IndexFoldDeclined("local indexed width")
                return [("local:"+m[1],0,constant)]
            bundles=wire(m[1],env)
            if len(bundles)!=1: raise _IndexFoldDeclined("nonhomogeneous bundle")
            b=bundles[0]
            low,high=sorted([coefficient*lo+constant,coefficient*(hi-1)+constant])
            if not 0<=low<=high<b.width: raise _IndexFoldDeclined("index range")
            if coefficient and b.identity in control_ids: raise _IndexFoldDeclined("control intersection varies")
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
        except _IndexFoldDeclined:
            return False

    def leaf_address(self,carrier=False):
        meta=self.source_context
        coordinates=tuple(self.loop_coordinates[:meta["depth"]]) if meta is not None else ()
        cached=self.address_cache
        if cached is not None and cached[0] is meta and cached[1] is self.call_edges and cached[2]==coordinates:
            chain,canonical=cached[3:]
        else:
            chain=metadata_counts(list(self.call_edges))
            if meta is not None:
                chain.append(metadata_counts({"symbol":meta["symbol"],"point":meta["point"],"iteration":list(coordinates),"instance":meta.get("instance",[])}))
            canonical=jcs(chain)
            self.address_cache=(meta,self.call_edges,coordinates,chain,canonical)
        if carrier:return {"chain":chain,"ordinal":0,"step":self.root_step,"phase":self.root_phase}
        key=(canonical,self.root_step,self.root_phase)
        previous,count=self.source_ordinals.get(id(meta),(None,0))
        if previous!=key:count=0
        self.source_ordinals[id(meta)]=(key,count+1)
        if self.raw_limits is not None:
            require(key in self.raw_limits,"raw inverse emitted a point outside its forward domain")
            size,sign=self.raw_limits[key]
            position=self.raw_cursors.get(key,0);self.raw_cursors[key]=position+1
            require(position<size,"raw inverse exceeded its forward point domain")
            ordinal=position if sign>0 else size-1-position
        else:ordinal=count if self.reverse_limits is None else self.reverse_limits[id(meta)]-1-count
        require(ordinal>=0,"inverse exceeded its forward ordinal space")
        return {"chain":chain,"ordinal":ordinal,"step":self.root_step,"phase":self.root_phase}

    def address_key(self,chain,step,phase):
        cached=self.address_cache
        canonical=cached[4] if cached is not None and chain is cached[3] else jcs(metadata_counts(list(chain)))
        return canonical,integer(step,0) if step is not None else None,phase

    def ordinal_sign(self):
        phase=self.root_phase
        for edge in self.call_edges:
            if "entered_invocation" in edge:phase=edge["entered_invocation"][1]
        return (-1 if self.region_raw else 1)*(-1 if self.region_oracle and phase=="rev" else 1)

    def space_event(self,b,acquire):
        if acquire:self.used_allocations.add(b.identity)
        if self.ledger is None:return space_profile(b.cls,b.state,b.width if acquire else -b.width)
        address=self.leaf_address()
        return self.ledger.allocate(b,**address) if acquire else self.ledger.release(b,**address)

    def gate_event(self,op,operands,controls=(),own=None,params=None):
        if self.ledger is not None:
            required=self.ledger.require_exact
            self.ledger.require_exact=required or bool(self.source_context and self.source_context.get("exact"))
            try:return self.ledger.gate(op,operands,controls,params=params,**self.leaf_address())
            finally:self.ledger.require_exact=required
        actual=bits(operands)
        depth=self.target.doc["capabilities"]["max_predicate_depth"]
        require(depth=="unbounded" or len({(identity,index) for identity,index,_ in controls})<=depth,"E_SCHEDULE_INFEASIBLE: max_predicate_depth exceeded")
        k={"cx":1,"ccx":2,"mcx":len(actual)-1}.get(op,0) if own is None else own
        effective=tuple(dict.fromkeys(actual[:k]+controls))
        classes=[w[2] for w in effective+actual[k:]]
        exact=self.target.exact_native(op,classes,len(effective),k)
        if self.count_only:return Profile(inexact_operations=0 if exact else 1)
        p=self.target.gate(op,classes,len(effective),0 if exact else self.eps,own=k,theta=params[0] if params else None)
        require(not self.require_exact or p.error==0,"E_GATE_UNSUPPORTED: permutation region requires exact gates")
        p.inexact_operations=0 if exact else 1
        return p

    def body(self, nodes, env, controls=(), inverse=False):
        previous=self.inverse_declarations
        try:return self._body(nodes,env,controls,inverse)
        finally:self.inverse_declarations=previous

    def _body(self, nodes, env, controls=(), inverse=False):
        require(isinstance(nodes, list), "K19: constructor body must be array")
        env = dict(env)
        # Declarations must also be available during inverse traversal. No wire
        # arrays are allocated: each bundle is one interval descriptor.
        for node in nodes:
            if "alloc" in node:
                n = integer(scalar(node["width"], env), 0)
                cls = node["class"]
                if isinstance(cls, dict): cls = cls["class"]
                if node["alloc"] in env and isinstance(env[node["alloc"]],Bundle) and self.allocation_scopes.get(env[node["alloc"]].identity)==env.get(_BINDING_SCOPE) and (inverse or env[node["alloc"]].identity not in self.used_allocations or env[node["alloc"]].identity in self.inverse_declarations):continue
                if cls == "any" and self.ledger is None: cls = self.default_class
                require(cls=="any" or cls in self.target.doc["classes"], "unknown allocation class")
                self.serial += 1
                env[node["alloc"]] = Bundle(f"{self.serial}:{node['alloc']}", n, cls, state="borrowed" if node["state"] in ["dirty","borrowed"] else "clean")
                self.allocation_scopes[env[node["alloc"]].identity]=env.get(_BINDING_SCOPE)
        if inverse:self.inverse_declarations=self.inverse_declarations | {env[node["alloc"]].identity for node in nodes if "alloc" in node}
        out = Profile()
        for node in reversed(nodes) if inverse else nodes:
            prior_context=self.source_context
            marked=self.source_metadata.get(id(node))
            if marked is not None:self.source_context=marked[1]
            self.visits += 1
            require(isinstance(node, dict), "invalid constructor")
            if "gate" in node:
                keys(node, ["gate", "wires"], ["params"], "gate constructor")
                op = ADJOINT.get(node["gate"], node["gate"]) if inverse else node["gate"]
                resolved=wire(node["wires"],env)
                operands = bits(resolved)
                require(len(operands) == len(set(operands)), "K19: coincident gate operands")
                require(op in GATES and len(operands) == GATES[op] or op == "mcx" and len(operands) >= 1, "K19: gate arity/opcode")
                own = {"cx": 1, "ccx": 2, "mcx": len(operands)-1}.get(op, 0)
                require(not set(operands[own:]) & set(controls), "K19: effective control is a target")
                effective = tuple(dict.fromkeys(operands[:own] + controls))
                classes = [w[2] for w in effective + operands[own:]]
                params=[]
                for parameter in node.get("params",[]):
                    value=env.get(parameter,parameter) if isinstance(parameter,str) else parameter
                    if inverse:
                        if isinstance(value,str) and value.startswith("0x"):value="0x"+format(int(value[2:],16)^(1<<63),"016x")
                        else:value=-float(value)
                    params.append(value)
                p=self.gate_event(op,resolved,controls,own,params)
            elif "alloc" in node or "release" in node or "acquire" in node or "relinquish" in node:
                key = next(k for k in ["alloc", "release", "acquire", "relinquish"] if k in node)
                if key == "alloc": keys(node, ["alloc", "width", "class", "state"], context="allocation")
                else: keys(node, [key], context=key)
                b = env.get(node[key])
                require(isinstance(b, Bundle), f"K27: missing allocation {node[key]}")
                sign = 1 if key in ["alloc", "acquire"] else -1
                p=self.space_event(b,(sign>0)!=inverse)
            elif "for" in node:
                keys(node, ["for", "from", "to", "body"], context="loop")
                lo, hi = scalar(node["from"], env), scalar(node["to"], env)
                require(hi >= lo, "K19: reversed loop bounds")
                summary=self.table_entry_summary(node,env,controls,inverse) if self.ledger is None and self.closed_form and not self.target.doc.get("topology") else None
                if summary is not None:p=summary
                elif lo == hi: p = Profile()
                elif self.ledger is None and self.closed_form and self.invariant(node["body"], node["for"]) and self.safe_index_fold(node["body"],node["for"],lo,hi,env,controls) and not self.target.doc.get("topology") and all(not isinstance(v,(list,tuple)) or not v or not isinstance(v[0],Bundle) or len({b.cls for b in v}) == 1 for v in env.values()):
                    bound = dict(env, **{node["for"]: lo})
                    p = self.body(node["body"], bound, controls, inverse).repeat(hi-lo)
                else:
                    p = Profile()
                    for i in range(hi-1,lo-1,-1) if inverse else range(lo,hi):
                        coordinates=self.loop_coordinates
                        source_loop=bool(self.source_context and self.source_context.get("kind")=="qloop" and node.get("for")=="$iteration")
                        source_loop=source_loop or bool(self.source_context and self.source_context.get("kind")=="qloop" and node.get("for")=="i" and any(node is n for n in self.recipes["qloop.while"]["body"]))
                        if source_loop:self.loop_coordinates=coordinates+[i-lo]
                        p = p.then(self.body(node["body"], dict(env, **{node["for"]: i}), controls, inverse))
                        self.loop_coordinates=coordinates
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
                p = self.recipe(node["invoke"], node["args"], env, controls, inverse,invoked=True)
            elif "splice" in node:
                keys(node, ["splice"], context="splice")
                captured = env[node["splice"]]
                require(isinstance(captured, Captured), "unbound body")
                if captured.cleanup and self.ledger is not None:
                    address=self.leaf_address(carrier=True)
                    choice=self.ledger.schedule.pick("cleanup",**address) or {"realisation":"reverse"}
                    self.ledger.cleanup_decisions.append({**address,**choice,**({"owned_points":list(captured.owned_points)} if captured.owned_points else {})})
                    if choice["realisation"]=="recompute":
                        require(captured.recompute is not None,"source cleanup-pair recompute binding remains pending for this carrier")
                        captured=captured.recompute
                joined = tuple(dict.fromkeys(controls + captured.controls))
                edges,coordinates=self.call_edges,self.loop_coordinates
                if marked is not None and marked[1].get("call"):
                    address=self.leaf_address(carrier=True)
                    key=jcs(address["chain"])
                    count=marked[1].get("call_index",0)+1
                    self.call_domains[key]=(address["chain"],max(count,self.call_domains.get(key,(None,0))[1]))
                    edge=metadata_counts({"symbol":marked[1]["symbol"],"point":marked[1]["point"],"iteration":list(coordinates[:marked[1]["depth"]]),"instance":marked[1].get("instance",[]),"call_index":marked[1].get("call_index",0)})
                    if marked[1].get("oracle_call"):edge["entered_invocation"]=[None,None]
                    self.call_edges=edges+(edge,);self.loop_coordinates=[]
                p = captured.builder(joined,inverse,env) if captured.builder is not None else self.body(captured.body, captured.env, joined, inverse)
                self.call_edges,self.loop_coordinates=edges,coordinates
            elif "image" in node:
                keys(node, ["image", "wires"], context="image")
                image = env.get(node["image"], node["image"])
                require(is_image(image), "K21: malformed image")
                bundle = wire(node["wires"], env)
                require(not image or sum(b.width for b in bundle) == len(image)*4, "K21: image width mismatch")
                p = Profile()
                if self.ledger is None and self.closed_form:
                    offset=0
                    for b in bundle:
                        count=image_ones(image,offset,offset+b.width) if image else 0
                        if count:p=p.then(self.gate_event("x",[b.bit(0)]).repeat(count))
                        offset+=b.width
                else:
                    data=bytes.fromhex(image)
                    for index in range(len(data)-1,-1,-1) if inverse else range(len(data)):
                        for bit in range(7,-1,-1) if inverse else range(8):
                            if data[index] & (1<<bit):
                                cursor=index*8+bit
                                for b in bundle:
                                    if cursor<b.width:
                                        p=p.then(self.gate_event("x",[b.bit(cursor)]));break
                                    cursor-=b.width
            elif "declare" in node:
                keys(node, ["declare", "width", "class", "state", "body"], context="declare")
                cls = env.get(node["class"], node["class"]) if isinstance(node["class"],str) else node["class"]
                cls = cls.get("class") if isinstance(cls,dict) else cls
                if cls == "any" and self.ledger is None: cls = self.default_class
                self.serial += 1
                b = Bundle(str(self.serial), integer(scalar(node["width"], env),0), cls, state=node["state"])
                p = self.body(node["body"], dict(env, **{node["declare"]: b}), controls, inverse)
                require(all(v == 0 for v in p.delta.values()), "K27: live declaration at scope exit")
            elif "visit" in node:
                keys(node, ["visit", "body"], context="visit")
                p=self.global_delivery_summary(node,env,controls,inverse) if self.ledger is None and self.closed_form and not self.target.doc.get("topology") else None
                if p is None:
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
            self.source_context=prior_context
        return out


NAME = r"[A-Za-z_][A-Za-z0-9_.]*"
_SOURCE_INACTIVE=object()
_SOURCE_LIFETIMES=object()
_SOURCE_TOKEN_IDENTITIES=object()
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


class ClassicalKind(Enum):
    ARITHMETIC = auto()
    REGISTER = auto()
    QUANTUM = auto()
    BRANCH = auto()
    RETURN = auto()
    FAULT = auto()
    CALL = auto()
    UNCALL = auto()
    ALLOCATE = auto()
    FREE = auto()
    MEMORY = auto()
    MINT = auto()
    MEASURE = auto()
    EFFECT = auto()
    OTHER = auto()


# ISA §3.3/§7 classical operation families. Widths remain in the raw opcode;
# source construction and canonical object hashes retain the original spelling.
CLASSICAL_KINDS = {
    **dict.fromkeys(["add", "sub", "mul", "and", "or", "xor", "shl", "lshr", "ashr",
                     "udiv", "urem", "sdiv", "srem", "inttoptr", "select"], ClassicalKind.ARITHMETIC),
    **dict.fromkeys(["qreg.new", "qreg.free", "qreg.slice", "qreg.concat", "qreg.width",
                     "qreg.id", "qreg.from_id"], ClassicalKind.REGISTER),
    **dict.fromkeys(["action_call", "oracle_call", "adj", "ctl"], ClassicalKind.QUANTUM),
    "br": ClassicalKind.BRANCH, "ret": ClassicalKind.RETURN,
    "trap": ClassicalKind.FAULT, "fault": ClassicalKind.FAULT,
    "call": ClassicalKind.CALL, "uncall": ClassicalKind.UNCALL,
    "alloc": ClassicalKind.ALLOCATE, "free": ClassicalKind.FREE,
    "budget.mint": ClassicalKind.MINT, "measure": ClassicalKind.MEASURE,
    "effect": ClassicalKind.EFFECT,
}


@dataclass
class Instruction:
    op: str
    args: list
    lhs: list
    body: list = field(default_factory=list)
    otherwise: list = field(default_factory=list)
    block: str = ""
    ordinal: int = 0
    classical_kind: ClassicalKind = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.op.startswith(("const.i", "icmp.", "zext.i", "sext.i", "trunc.i", "ptrtoint.i")):
            self.classical_kind = ClassicalKind.ARITHMETIC
        elif self.op.startswith(("load.i", "store.i")):
            self.classical_kind = ClassicalKind.MEMORY
        elif self.op.startswith("measure.i"):
            self.classical_kind = ClassicalKind.MEASURE
        else:
            # OTHER is still a source opcode; the classical executor rejects it
            # explicitly if it is reached, rather than emitting an exact cost.
            self.classical_kind = CLASSICAL_KINDS.get(self.op, ClassicalKind.OTHER)


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
            require(current,"§16.2: a structured scope requires at least one instruction")
            current = stack[-1][1].otherwise
        elif line == "}":
            require(stack, "unmatched scope end")
            require(current,"§16.2: a structured scope requires at least one instruction")
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
    require(all(code for params,code in blocks.values()),"§16.2: every block requires at least one instruction")
    action_ops={"qalloc","qborrow","qfree","qreturn","qcopy","quncopy","qxor","qexch","qinplace","qregion","qload","qunload","qstore","qexchm","qpred","qunpred","qif","qloop","mcx"}
    region_calls={"oracle_call","action_call","adj","ctl"}
    for inst in root:
        op=inst.op
        if op=="measure" or op.startswith("measure.i"):
            require(len(inst.lhs)==len(inst.args)==1,"§3.3: measurement result/operand arity mismatch")
            if op!="measure":require(1<=integer(op[9:],1)<=128,"§3.3: measurement width must be in 1..128")
        if op.startswith("qreg."):
            expected={"new":2,"free":1,"slice":3,"concat":2,"width":1,"id":1,"from_id":1}[op[5:]]
            require(len(inst.lhs)==(0 if op=="qreg.free" else 1),"§4.8: register result arity mismatch")
            require(len(inst.args)==expected,"§3.3: register operand arity mismatch")
            literal=inst.args[-1] if op in ["qreg.new","qreg.slice"] else None
            if literal is not None and re.fullmatch(r"-?[0-9]+",literal):integer(literal,1)
        if kind in ["oracle","lproc"]:
            require(op.startswith("lift.") or op in ["qjump","qbranch","qjumpr","fault"],"§4.8: instruction outside lifted tier")
            require(not (op=="lift.ret" and kind=="oracle" or op=="lift.retval" and kind=="lproc"),"§4.2: wrong lifted return kind")
        elif kind in ["action","perm_action"]:
            require(op in action_ops|region_calls|GATES.keys(),"§4.8: instruction outside action tier")
        else:
            require(not op.startswith("lift.") and op not in action_ops|GATES.keys()|{"qjump","qbranch","qjumpr"},"§4.8: instruction outside classical tier")
            require(kind=="cc" or op not in ["hostcall","measure"] and not op.startswith("measure.i"),"§4.8: CC-only instruction in R")
            require(kind=="r" or op!="effect","§4.8: effect requires R")
    if kind in ["oracle","lproc","cc","r"]:
        terminators={"qjump","qbranch","qjumpr","lift.retval" if kind=="oracle" else "lift.ret","fault"} if kind in ["oracle","lproc"] else {"br","ret","trap","fault"}
        for params,code in blocks.values():require(code and code[-1].op in terminators,"§3.6/§4.1: block has no valid terminator")
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
            keys(sig, ["tier","kind","abi",*required[kind]], context=f"ISA {versions['isa']} {kind} signature")
            require(sig["kind"] == kind and sig["abi"] == versions["isa"], "signature version/kind mismatch")
            require(sig["tier"]=={"cc":"cc","r":"r","oracle":"q","action":"q","perm_action":"q","lproc":"q","data":"-"}[kind],"signature kind/tier mismatch")
            if kind != "data":
                require(symbol["name"] in out.functions and out.functions[symbol["name"]].kind == kind, "symbol/header mismatch")
                fn=out.functions[symbol["name"]];g=fn.groups
                all_names=[n for group in g for n,ty,role in group]+[n for n,ty,role in fn.regs]
                require(len(all_names)==len(set(all_names)),"duplicate function interface/location name")
                if kind in ["oracle","lproc"]:
                    require(all(re.fullmatch(r"reg\[[1-9][0-9]*\]",ty) and role is None for n,ty,role in fn.regs),"§3.7/K32: locations require reg[N]")
                else:require(not fn.regs,"§3.7/K32: only oracle/lproc may declare locations")
                def wire_group(group,role=None):
                    require(all(re.fullmatch(r"wire(?:\[[1-9][0-9]*\])?",ty) and r in ([None,role] if role else [None]) for n,ty,r in group),"invalid wire interface type/role")
                def arg_group(group,suffix=None,tokens=False):
                    require(all((ty=="token" if tokens else ty in ["ptr","f64","token"] or re.fullmatch(r"i[1-9][0-9]*",ty)) and r in [None,suffix] for n,ty,r in group),"invalid classical/token argument type/role")
                if kind=="oracle":
                    wire_group(g[0],"in");wire_group(g[1]);wire_group(g[2]);arg_group(g[4])
                    require(all(r=="in" for n,ty,r in g[3]),"oracle memory must be read-only")
                elif kind in ["action","perm_action"]:
                    wire_group(g[0],"mut");wire_group(g[1],"in");arg_group(g[3])
                    match=re.search(r"^regs \{.*?\} bounds \{([^}]*)\}$",fn.raw,re.M)
                    declared=[integer(n,0) for n in match[1].split(", ")] if match else []
                    loops=[i for i in fn.code if i.op=="qloop"]
                    require(declared==sig["bounds"] and len(loops)==len(declared),"§5.3: action bounds list/header/body mismatch")
                    for i,n in zip(loops,declared):
                        if re.fullmatch(r"0|[1-9][0-9]*",i.args[0]):require(int(i.args[0])==n,"§5.3: action bounds differ from loop trip count")
                elif kind=="lproc":
                    require(all(re.fullmatch(r"reg\[[1-9][0-9]*\]",ty) and r is None for group in g[:2] for n,ty,r in group),"lproc locations require reg[N]")
                    arg_group(g[2],"token",True);arg_group(g[3],"classical")
                    require(all(ty!="token" for n,ty,r in g[3]) and all(r=="in" for n,ty,r in g[4]),"lproc token/classical/memory group mismatch")
                def widths(group): return [type_width(ty,out.ptr) for n,ty,role in group]
                def width_value(value):return unsigned(value) if isinstance(value,str) else integer(value,1)
                def width_values(values):return [width_value(v) for v in values]
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
                    require(len(g[1])==len(g[2])==1 and width_values(sig["in"])==widths(g[0]) and width_value(sig["tgt"])==widths(g[1])[0] and width_value(sig["fault"])==widths(g[2])[0] and sig["mem"]==mem(g[3]) and sig["args"]==[ty for n,ty,r in g[4]],"§9.1: oracle signature/header mismatch")
                    require(width_value(sig["fault"])>=4,"§5.4: oracle fault width must be at least four")
                elif kind in ["action","perm_action"]:
                    require(width_values(sig["mut"])==widths(g[0]) and width_values(sig["in"])==widths(g[1]) and sig["mem"]==mem(g[2]) and sig["args"]==[ty for n,ty,r in g[3]] and not g[4],"§9.1: action signature/header mismatch")
                else:
                    require(len(g[1])==1 and width_values(sig["params"])==widths(g[0]) and width_value(sig["result"])==widths(g[1])[0] and sig["tokens"]==[ty for n,ty,r in g[2]] and sig["args"]==[ty for n,ty,r in g[3]] and sig["mem"]==mem(g[4]),"§9.1: lproc signature/header mismatch")
                for n,ty,r in fn.regs: type_width(ty,out.ptr)
            else:
                require(symbol["name"] in out.sections.get("data",{}) and integer(sig["size"],0)*2==len(out.sections["data"][symbol["name"]]),"data signature size mismatch")
        if "layout" in out.sections:
            keys(out.sections["layout"], ["ptr_width","H","A_tab","S_cells","null_size","heap_base","heap_limit_max","globals","interface_regions"], ["block_image"], "layout")
            if "block_image" in out.sections["layout"]:
                image=out.sections.get("data",{}).get(out.sections["layout"]["block_image"])
                require(image is not None and len(image)%1024==0,"K10: block image must name data containing whole 512-byte sectors")
        devices=out.sections.get("devices",{"models":{},"services":{}})
        keys(devices,["models","services"],context="devices")
        require(isinstance(devices["models"],dict) and isinstance(devices["services"],dict),"§9.1: device model/service maps required")
        require(set(devices["models"])<={"console","clock","entropy","block"},"§9.1: unknown device model")
        for declarations in [devices["models"],devices["services"]]:
            for name,value in declarations.items():
                keys(value,["version"],context="device declaration")
                require(isinstance(value["version"],str) and value["version"],"§9.1: device version must be nonempty text")
        for fn in out.functions.values():
            for row in fn.code:
                if row.op=="effect":
                    device=row.args[0].split(".")[0]
                    require(device not in {"console","clock","entropy","block"} or device in devices["models"],"§9.1: used device model is not declared")
                elif row.op=="hostcall":require(row.args[0] in devices["services"],"§9.1: used host service is not declared")
        names=[s["name"] for s in symbols.values()]
        require(len(names)==len(set(names)),"duplicate symbol name")
        require(set(out.functions)=={s["name"] for s in symbols.values() if s["kind"]!="data"},"function definitions and symbols differ")
        require(set(out.sections.get("data",{}))=={s["name"] for s in symbols.values() if s["kind"]=="data"},"data definitions and symbols differ")
        for fn in out.functions.values():
            for inst in fn.code:
                if inst.op!="call":continue
                require(inst.args and re.fullmatch("@"+NAME,inst.args[0]),"§4.1: call requires a bare symbol operand")
                target=out.functions.get(inst.args[0][1:])
                require(target is not None or inst.args[0][1:] in out.sections.get("imports",{}),"call names no function or declared import")
                if target is None:continue  # declared imports are checked at link
                allowed=["cc","r"] if fn.kind=="cc" else ["r"]
                require(target.kind in allowed,"§3.1: classical call tier violation (R may call only R)")
                require(len(inst.args)-1==len(target.groups[0]) and len(inst.lhs)==len(target.groups[1]),"§4.1: call argument/result arity mismatch")
        out.validate_region_graph()
        out.validate_measurement_types()
        out.validate_register_views()
        return out

    def validate_measurement_types(self):
        """Check declared/block-local measurement widths; linking stays separate."""
        def fixed(ty):
            m=re.fullmatch(r"qreg\[([1-9][0-9]*)\]",ty or "")
            return int(m[1]) if m else None
        for fn in self.functions.values():
            if not any(i.op=="measure" or i.op.startswith("measure.i") for i in fn.code):continue
            for params,code in fn.blocks.values():
                types={n:ty for n,ty,r in fn.groups[0]+params}
                for row in code:
                    op,a=row.op,row.args;produced=None
                    if op in ["qreg.new","qreg.slice"]:
                        size=a[-1];produced="qreg["+(size if size.isdigit() else "*")+"]"
                    elif op=="qreg.concat":
                        operands=[types.get(n) for n in a];sizes=[fixed(ty) for ty in operands]
                        if all(n is not None for n in sizes):produced=f"qreg[{sum(sizes)}]"
                        elif all(ty is not None for ty in operands):produced="qreg[*]"
                    elif op=="qreg.from_id":produced="qreg[*]"
                    elif op in ["qreg.width","qreg.id"]:produced="i64"
                    elif op.startswith("const.i"):produced="i"+op[7:]
                    elif op=="call" and a[0][1:] in self.functions:
                        types.update({name:ty for name,(n,ty,r) in zip(row.lhs,self.functions[a[0][1:]].groups[1])})
                        continue
                    elif op=="measure" or op.startswith("measure.i"):
                        ty=types.get(a[0]);width=fixed(ty)
                        if ty is not None:
                            require(ty=="qreg[*]" or width is not None,"§3.3: measure requires a register")
                            if width is not None:
                                require(width<=128,"§3.3: measure result width exceeds 128")
                                require(op=="measure" or integer(op[9:],1)==width,"§3.3: measure fixed width mismatch")
                            else:require(op!="measure","§3.3: measure of qreg[*] requires measure.iN")
                        produced="i"+str(width) if op=="measure" and width is not None else "i"+op[9:] if op!="measure" else None
                    for name in row.lhs:
                        if produced is None:types.pop(name,None)
                        else:types[name]=produced

    def validate_register_views(self):
        """§3.3's lexical view rule on every CFG path, without executing it."""
        def operands(inst):
            op,args=inst.op,list(inst.args);controls=[]
            while op in ["ctl","adj"]:
                index=1 if op=="ctl" else 0
                if index:controls.append(args[0])
                op,args=args[index],args[index+1:]
            if op=="action_call":
                require(len(args)==5,"§4.7: incomplete action argument groups")
                slots=[n for group in args[1:4] for n in list_operand(group)]
                return controls+slots+list_operand(args[4]),controls+slots
            if op=="oracle_call":
                require(len(args)==7,"§4.7: incomplete oracle argument groups")
                slots=list_operand(args[2])+args[3:5]+list_operand(args[5])
                return controls+slots+[args[1]]+list_operand(args[6]),controls+slots
            if op=="br":
                values=[args[0]] if len(args)>1 else []
                for label in args if len(args)==1 else args[1:]:
                    match=re.fullmatch(r"\^([^ (]+)\((.*?)\)",label)
                    require(match,"§4.1: malformed branch label")
                    values+=list_operand("("+match[2]+")")
                return values,[]
            if op=="uncall":return list_operand(args[1])+list_operand(args[2]),[]
            if op=="qreg.new":args=args[1:]
            elif op in ["call","budget.mint","hostcall","effect"]:args=args[1:]
            elif op.startswith("const."):args=[]
            return args,[]
        for fn in self.functions.values():
            if fn.kind not in ["cc","r"]:continue
            decoded={id(row):operands(row) for row in fn.code}
            for row in fn.code:
                _,slots=decoded[id(row)]
                if row.op=="qreg.concat":slots=row.args
                require(len(slots)==len(set(slots)),"§3.3: duplicate register operand name")
            for block,(_,code) in fn.blocks.items():
                for index,row in enumerate(code):
                    if row.op!="qreg.slice":continue
                    view,parent=row.lhs[0],row.args[0]
                    pending=[(block,index+1,False)];visited=set()
                    while pending:
                        label,position,consumed=pending.pop()
                        key=(label,position,consumed)
                        if key in visited:continue
                        visited.add(key)
                        require(label in fn.blocks,"§4.1: branch names no block")
                        params,body=fn.blocks[label]
                        if position==0 and view in [n for n,ty,r in params]:
                            require(consumed,"§3.3: live view overwritten at block entry")
                            continue
                        if position==len(body):
                            require(consumed,"§3.3: view reaches function end unconsumed")
                            continue
                        current=body[position];uses,slots=decoded[id(current)]
                        if view in current.lhs:
                            require(consumed,"§3.3: live view overwritten before its call")
                            continue
                        if view in uses:
                            require(not consumed and view in slots,"§3.3: view must be used by exactly one region call")
                            consumed=True
                        else:require(consumed or parent not in uses,"§3.3: view parent used before its region call")
                        if current.op=="ret":
                            require(consumed,"§3.3: view reaches ret unconsumed")
                        elif current.op=="br":
                            for target in current.args if len(current.args)==1 else current.args[1:]:pending.append((target[1:target.index("(")],0,consumed))
                        elif current.op not in ["trap","fault"]:pending.append((label,position+1,consumed))

    def validate_region_graph(self):
        """§5.1 includes semantic calls in the complete lifted closure."""
        imports=self.sections.get("imports",{})
        def linked(name,kinds):
            require(re.fullmatch("@"+NAME,name),"region/lifted call needs a symbol operand")
            name=name[1:]
            require(name in self.functions or name in imports,"call names no definition or declared import")
            kind=self.functions[name].kind if name in self.functions else imports[name].get("signature",{}).get("kind")
            require(kind in kinds,"§3.1/§4.7: incompatible callee kind")
            return name
        calls={};lifted={}
        for name,fn in self.functions.items():
            calls[name]=set();lifted[name]=set()
            for inst in fn.code:
                op,args=inst.op,inst.args
                while op in ["adj","ctl"]:
                    index=1 if op=="ctl" else 0
                    require(len(args)>index,"incomplete controlled/adjoint region call")
                    op,args=args[index],args[index+1:]
                if op in ["oracle_call","lift.oracle_call","lift.oracle_uncall","budget.mint"]:
                    require(args,"missing oracle call target")
                    child=linked(args[0],["oracle"])
                    if op!="budget.mint":calls[name].add(child)
                elif op in ["action_call","lift.perm_call"]:
                    require(args,"missing action call target")
                    calls[name].add(linked(args[0],["action","perm_action"]))
                elif op=="qinplace":
                    require(len(args)>=2,"missing qinplace pair")
                    calls[name].update(linked(a,["oracle"]) for a in args[:2])
                elif op=="lift.call":
                    require(args,"missing lifted call target")
                    lifted[name].add(linked(args[0],["lproc"]))
        graph={}
        for name,fn in self.functions.items():
            if fn.kind not in ["oracle","action","perm_action"]:continue
            graph[name]=set();pending=[name];seen=set()
            while pending:
                function=pending.pop()
                if function in seen or function not in self.functions:continue
                seen.add(function);graph[name].update(calls[function]);pending.extend(lifted[function])
        visiting=set();finished=set()
        def visit(name):
            if name in finished or name not in graph:return
            require(name not in visiting,"§5.1: region call graph must be acyclic (cycle found)")
            visiting.add(name)
            for child in graph[name]:visit(child)
            visiting.remove(name);finished.add(name)
        for name in graph:visit(name)

    def symbol(self, name):
        matches = [s for s in self.sections["symbols"].values() if s["name"] == name]
        require(len(matches) == 1, f"unknown/ambiguous symbol {name}")
        return matches[0]

    def procedure_instances(self,root):
        """§3.7 finite binding closure, keyed by entry positions, not values."""
        require(root in self.functions and self.functions[root].kind=="oracle","procedure closure requires an oracle")
        fn=self.functions[root]
        first={"function":fn,"key":(),"arguments":{n:i for i,(n,ty,r) in enumerate(fn.groups[4])},"regions":{n:i for i,(n,ty,r) in enumerate(fn.groups[3])},"calls":{}}
        instances={(root,()):first};pending=[first]
        while pending:
            caller=pending.pop();function=caller["function"]
            fixed=function.groups[4] if function.kind=="oracle" else function.groups[2]+function.groups[3]
            fixed_types={n:ty for n,ty,r in fixed}
            mem=function.groups[3] if function.kind=="oracle" else function.groups[4]
            region_types={n:ty for n,ty,r in mem}
            locations=function.regs if function.kind=="oracle" else function.groups[0]+function.groups[1]+function.regs
            writes={n:type_width(ty,self.ptr) for n,ty,r in locations}
            readable=function.groups[0]+[v for v in function.groups[4] if v[1]!="token"] if function.kind=="oracle" else function.groups[3]
            reads={**writes,**{n:type_width(ty,self.ptr) for n,ty,r in readable}}
            for row in function.code:
                if row.op!="lift.call":continue
                a=row.args;callee=self.functions.get(a[0].removeprefix("@"))
                require(callee is not None and callee.kind=="lproc","lift.call requires a linked lproc")
                require(len(a) in [2,5],"lift.call needs its complete fixed binding lists")
                require(len(a)==5 or not any(callee.groups[2:]),"lift.call short form omits nonempty fixed bindings")
                actuals=[list_operand(value) for value in a[1:]]
                if len(actuals)==1:actuals += [[],[],[]]
                require([len(v) for v in actuals]==[len(callee.groups[i]) for i in [0,2,3,4]],"lift.call argument arity mismatch")
                require(len(row.lhs)==1 and row.lhs[0] in writes and writes[row.lhs[0]]==type_width(callee.groups[1][0][1],self.ptr),"lift.call result location width mismatch")
                require(all(name in reads and reads[name]==type_width(ty,self.ptr) for (n,ty,r),name in zip(callee.groups[0],actuals[0])),"lift.call location argument width mismatch")
                arguments={};regions={}
                for formals,values in zip(callee.groups[2:4],actuals[1:3]):
                    for (name,ty,role),value in zip(formals,values):
                        require(value in caller["arguments"] and fixed_types.get(value)==ty,"lift.call fixed token/classical argument type mismatch")
                        arguments[name]=caller["arguments"][value]
                for (name,ty,role),value in zip(callee.groups[4],actuals[3]):
                    require(value in caller["regions"] and region_types.get(value)==ty,"lift.call fixed region binding mismatch")
                    regions[name]=caller["regions"][value]
                key=tuple(arguments[n] for n,ty,r in callee.groups[2]+callee.groups[3])+tuple(regions[n] for n,ty,r in callee.groups[4])
                identity=(callee.name,key);caller["calls"][id(row)]=identity
                if identity not in instances:
                    record={"function":callee,"key":key,"arguments":arguments,"regions":regions,"calls":{}}
                    instances[identity]=record;pending.append(record)
        ordered=[first]
        if len(instances)>1:
            self.identities(closure=True)
            for _,component in sorted(self.closure_components):
                for name in component:
                    if name!=root:ordered.extend(instances[(name,key)] for key in sorted(key for function,key in instances if function==name))
        position=0
        for record in ordered:
            record["first"]=position;record["labels"]={}
            for block,(_,rows) in record["function"].blocks.items():
                record["labels"][block]=position;position+=len(rows)
        return ordered

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
        component_order=[]
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
                component_order.append((scc,tuple(component)))
            else:
                computed[component[0]] = digest(envelope(component[0]))
                component_order.append((computed[component[0]],tuple(component)))
        if closure:self.closure_components=component_order
        return {n:computed[n] for n in records}


def validate_budget(budget, obj):
    require(isinstance(budget,list) and len(budget) == 4, "§5.4/K13: budget requires four components")
    values = [unsigned(v) for v in budget]
    require(all(v<1<<64 for v in values),"§5.4/§10: budget component exceeds uint64")
    layout = obj.sections.get("layout")
    if layout is None:
        if values[1:] != [0,0,0]:
            raise BudgetConstraintError("§5.4: memoryless budget requires heap=stack=depth=0")
    else:
        if not (values[1] <= integer(layout["heap_limit_max"],0) and values[2] <= 1 << integer(layout["S_cells"],0)):
            raise BudgetConstraintError("§5.4: budget exceeds layout")
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
            require(n.bit_length()<=width, f"E_ARG: {ty} argument out of range")
            out.append(n)
    return out


def validate_token_aliases(aliases,tuples):
    """K91 restricted-growth labels, in the invocation's token order."""
    require(isinstance(aliases,list) and len(aliases)==len(tuples),"E_ARG: token_aliases arity mismatch")
    seen={}
    for label,budget in zip(aliases,tuples):
        require(type(label) is int and label>=0,"E_ARG: token_aliases labels must be nonnegative JSON integers")
        value=tuple(integer(n,0) for n in budget) if budget is not None else None
        if label not in seen:
            require(label==len(seen),"E_ARG: token_aliases labels must follow first occurrence without gaps")
            seen[label]=value
        else:require(value is None or seen[label] is None or value==seen[label],"E_ARG: token_aliases equality conflicts with token tuples")
    return list(aliases)


def canonical_token_aliases(identities):
    labels={};result=[]
    for identity in identities:
        if identity not in labels:labels[identity]=len(labels)
        result.append(labels[identity])
    return result


class Schedule:
    """ISA-11 selectors; matching is independent for each decision kind."""
    def __init__(self,doc,obj=None,region=None):
        keys(doc,["bindings","entries"],["interface_vertices"],"schedule")
        self.doc=doc
        b=doc["bindings"]
        keys(b,["closure_hash","target_hash","region","variant","inherited_controls","budget","params_hash","epsilon","scheduler"],["expansion","token_aliases"],"schedule bindings")
        if "token_aliases" in b:
            require(isinstance(b["token_aliases"],list),"E_ARG: token_aliases must be an array")
            arity=len(b["token_aliases"])
            if obj is not None and b["region"] in obj.functions:
                fn=obj.functions[b["region"]]
                group=fn.groups[0] if fn.kind in ["cc","r"] else fn.groups[4] if fn.kind=="oracle" else fn.groups[3]
                arity=(fn.kind=="oracle")+sum(ty=="token" for n,ty,role in group)
            validate_token_aliases(b["token_aliases"],[None]*arity)
        for name in ["closure_hash","target_hash","params_hash"]:
            require(isinstance(b[name],str) and re.fullmatch(r"[0-9a-f]{64}",b[name]),f"invalid schedule {name}")
        require(isinstance(b["variant"],str) and b["variant"],"empty schedule variant")
        integer(b["inherited_controls"],0)
        require(isinstance(b["budget"],list) and len(b["budget"])==4,"schedule budget needs four components")
        for n in b["budget"]:integer(n,0)
        require(decimal_value(b["epsilon"])>=0,"negative schedule accuracy")
        keys(b["scheduler"],["name","version"],context="scheduler")
        if "expansion" in b:
            keys(b["expansion"],["name","version","hash"],context="expansion")
            require(b["expansion"]=={"name":"ref","version":"0.9","hash":"5de4e4995350313e50217880ba1b95de39cd043283b726337d4894efb005d197"},"E_SCHEDULE_INFEASIBLE: bound expansion library is unavailable")
        require(isinstance(doc["entries"],list),"schedule entries must be array")
        self.entries=doc["entries"]
        for entry in self.entries:
            kind=entry.get("kind")
            require(kind in ["gate","alloc","start","cleanup"],"unknown schedule entry kind")
            keys(entry,["path","step","phase","generated","kind",kind],context="schedule entry")
            require(isinstance(entry["path"],list),"schedule path must be array")
            for element in entry["path"]:
                keys(element,["symbol","point","iteration"],["instance","call_index"],"schedule path element")
                require(isinstance(element["symbol"],str) and re.fullmatch(r"[0-9a-f]{64}",element["symbol"]),"invalid path symbol")
                require(isinstance(element["point"],str),"invalid path point")
                for name in ["iteration","instance"]:
                    value=element.get(name,"*")
                    if value!="*":
                        require(isinstance(value,list),f"{name} must be integer array or wildcard")
                        for n in value:integer(n,0)
                if element.get("call_index","*")!="*":integer(element["call_index"],0)
            for name in ["step","generated"]:
                if entry[name]!="*":integer(entry[name],0)
            require(entry["phase"] in ["*","fwd","rev"],"invalid schedule phase")
            value=entry[kind]
            if kind=="gate":
                keys(value,[],["realisation","epsilon_share"],"gate decision")
                if "epsilon_share" in value:require(decimal_value(value["epsilon_share"])>=0,"negative epsilon share")
                if "realisation" in value:require(isinstance(value["realisation"],str) and value["realisation"],"empty gate realisation")
            elif kind=="alloc":
                keys(value,["class"],["vertices"],"allocation decision")
                require(isinstance(value["class"],str) and value["class"]!="any","allocation decision must resolve class")
            elif kind=="start":
                keys(value,["time"],context="start decision")
                require(decimal_value(value["time"])>=0,"negative start time")
            else:
                keys(value,["realisation"],context="cleanup decision")
                require(value["realisation"] in ["reverse","recompute"],"invalid cleanup realisation")
        if obj is not None:self.validate_paths(obj,region or b["region"])

    def validate_paths(self,obj,region):
        symbols={obj.symbol(name)["interface_hash"]:fn for name,fn in obj.functions.items()}
        domains={}
        def domain(name):
            if name not in domains:
                records=obj.procedure_instances(name) if obj.functions[name].kind=="oracle" else [{"function":obj.functions[name],"key":()}]
                resolved={}
                for record in records:resolved.setdefault(obj.symbol(record["function"].name)["interface_hash"],set()).add(record["key"])
                domains[name]=resolved
            return domains[name]
        depths={}
        def visit(fn,nodes,depth):
            for node in nodes:
                depths[(fn.name,f"{node.block}:{node.ordinal}")]=depth
                visit(fn,node.body,depth+(node.op=="qloop"))
                visit(fn,node.otherwise,depth)
        for fn in obj.functions.values():
            for _,nodes in fn.blocks.values():visit(fn,nodes,0)
        for entry in self.entries:
            path=entry["path"]
            context=domain(region) if path else {}
            for i,element in enumerate(path):
                require(element["symbol"] in context,"schedule path is not rooted in the current invocation closure")
                require(element["symbol"] in symbols,"schedule path has unknown symbol")
                fn=symbols[element["symbol"]]
                point=element["point"]
                if point.startswith("$"):
                    require(fn.kind=="oracle" and point in ["$construct","$step","$commit","$release"],"invalid support pseudo-point")
                    depth=0;inst=None
                else:
                    matches=[x for x in fn.code if f"{x.block}:{x.ordinal}"==point]
                    require(len(matches)==1,"schedule path has unknown source point")
                    inst=matches[0];depth=depths[(fn.name,point)]
                iteration=element["iteration"]
                require(iteration=="*" or len(iteration)==depth,"schedule iteration depth mismatch")
                instance=element.get("instance","*")
                if fn.kind!="lproc":require(instance in ["*",[]],"non-lproc point has a nonempty instance")
                elif instance!="*":require(tuple(integer(n,0) for n in instance) in context[element["symbol"]],"schedule path names an unreachable fixed-binding instance")
                if i+1<len(path) or element.get("call_index","*")!="*":
                    require(inst is not None,"support point is not an invocation edge")
                    op,args=inst.op,inst.args
                    while op in ["ctl","adj"]:
                        skip=1 if op=="adj" else 2
                        op,args=args[skip-1],args[skip:]
                    require(op in ["action_call","oracle_call","lift.oracle_call","lift.oracle_uncall","lift.perm_call","qinplace"],"path descends through a non-call point")
                    targets=[a.removeprefix("@") for a in args[:2 if op=="qinplace" else 1]]
                    if op=="lift.oracle_uncall" or op=="oracle_call" and fn.kind in ["action","perm_action"]:targets*=2
                    call_index=element.get("call_index","*")
                    require(call_index=="*" or integer(call_index,0)<len(targets),"semantic call occurrence outside expansion")
                    if i+1<len(path):
                        allowed=targets if call_index=="*" else [targets[integer(call_index,0)]]
                        context={}
                        for target in allowed:
                            for symbol,instances in domain(target).items():context.setdefault(symbol,set()).update(instances)
                        require(path[i+1]["symbol"] in context,"path callee does not match source call")

    def validate_call_domains(self,domains):
        """K63 actual occurrence counts, unioned across covered invocations.

        Unknown token-forwarded domains remain deferred by K55. A wildcard
        may cover both reverse and recompute contexts; one observed context
        with the selected occurrence is sufficient for path admission.
        """
        for entry in self.entries:
            for index,element in enumerate(entry["path"]):
                selected=element.get("call_index","*")
                if selected=="*":continue
                counts=[]
                for chain,count in domains.values():
                    if len(chain)!=index+1:continue
                    matches=True
                    for i,(selector,actual) in enumerate(zip(entry["path"],chain)):
                        if any(selector[k]!=actual[k] for k in ["symbol","point"]):matches=False;break
                        for k in ["iteration","instance","call_index"]:
                            if k=="call_index" and i==index:continue
                            expected=selector.get(k,"*")
                            if not self.coordinate_matches(k,expected,actual.get(k,[] if k!="call_index" else None)):matches=False;break
                        if not matches:break
                    if matches:counts.append(count)
                if counts:require(integer(selected,0)<max(counts),"semantic call occurrence outside expansion")

    @staticmethod
    def specificity(entry):
        return (len(entry["path"]),sum(p["iteration"]!="*" for p in entry["path"]),entry["step"]!="*",entry["phase"]!="*",entry["generated"]!="*")

    @staticmethod
    def coordinate_matches(name,expected,actual):
        if expected=="*":return True
        if actual is None:return False
        if name=="call_index":return integer(expected,0)==integer(actual,0)
        return len(expected)==len(actual) and all(integer(a,0)==integer(b,0) for a,b in zip(expected,actual))

    def pick(self,kind,chain,ordinal,step=None,phase=None):
        matches=[]
        for entry in self.entries:
            if entry["kind"]!=kind or len(entry["path"])>len(chain):continue
            if entry["generated"]!="*" and integer(entry["generated"],0)!=ordinal:continue
            selected_step,selected_phase=step,phase
            ok=True
            for i,(selector,actual) in enumerate(zip(entry["path"],chain)):
                if any(selector[k]!=actual[k] for k in ["symbol","point"]):ok=False;break
                for k in ["iteration","instance","call_index"]:
                    expected=selector.get(k,"*")
                    got=actual.get(k,[] if k in ["iteration","instance"] else None)
                    if not self.coordinate_matches(k,expected,got):ok=False;break
                if not ok:break
                if i+1<len(chain) and "entered_invocation" in actual:
                    selected_step,selected_phase=actual["entered_invocation"]
            if not ok:continue
            if entry["step"]!="*" and (selected_step is None or integer(entry["step"],0)!=integer(selected_step,0)):continue
            if entry["phase"]!="*" and entry["phase"]!=selected_phase:continue
            matches.append(entry)
        if not matches:return None
        score=max(self.specificity(e) for e in matches)
        maximal=[e for e in matches if self.specificity(e)==score]
        require(len(maximal)==1,"E_SCHEDULE_INFEASIBLE: §11: multiple maximal matching schedule entries")
        return maximal[0][kind]


class Ledger:
    """Resource endpoints and live allocations; no gate/circuit list is kept."""
    def __init__(self,target,schedule,default_share=F(0),exact=False,count_only=False):
        self.target,self.schedule=target,schedule
        self.default_share=rational(default_share);self.require_exact=exact
        self.count_only=count_only;self.nonexact_native_operations=0
        self.cursor=self.makespan=0
        self.counts={};self.gates={};self.error=0
        self.records=[];self.dependencies={};self.parallel_events={}
        self.live={}
        self.cleanup_decisions=[]
        self.interface_index=0;self.sequence=0
        self.order=0
        self.classes=sorted(target.doc["classes"],key=lambda n:n.encode("utf-16-be"))

    def _decision(self,kind,chain,ordinal,step,phase):
        return self.schedule.pick(kind,chain,ordinal,step,phase)

    def _start(self,chain,ordinal,step,phase,minimum=F(0)):
        chosen=self._decision("start",chain,ordinal,step,phase)
        if self.count_only:return 0
        start=rational(chosen["time"]) if chosen is not None else max(self.cursor,minimum)
        require(start>=minimum,"E_SCHEDULE_INFEASIBLE: start violates data or wire-lifetime dependency")
        return start

    def _find(self,b):
        for record in reversed(self.live.get(b.identity,[])):
            source=record["bundle"]
            if record["end"] is None and source.identity==b.identity and source.offset<=b.offset and b.offset+b.width<=source.offset+source.width:return record
        raise ContractError(f"E_SCHEDULE_INFEASIBLE: wire is not live: {b.identity}[{b.offset}]")

    def resolved_class(self,b):return self._find(b)["class"]

    @staticmethod
    def _bit_bundle(bit):return Bundle(bit[0],1,bit[2],bit[1])

    def _used(self,cls,start):
        return sum(r["bundle"].width for r in self.records if r["class"]==cls and r["start"]<=start and (r["end"] is None or start<r["end"]))

    def _class(self,requested,width,start,vertices):
        top=self.target.doc.get("topology")
        if vertices is not None:
            require(top is not None,"vertices are forbidden without topology")
            require(isinstance(vertices,list) and len(vertices)==width,"placement width mismatch")
            require(len(set(vertices))==len(vertices),"duplicate allocation vertex")
            for v in vertices:require(isinstance(v,int) and not isinstance(v,bool) and 0<=v<len(top["vertices"]),"vertex outside topology")
            classes={top["vertices"][v]["class"] for v in vertices}
            require(len(classes)<=1,"one frame slot/allocation must resolve to one class")
            if classes:
                cls=next(iter(classes))
                require(requested in ["any",cls],"vertex class differs from allocation class")
                requested=cls
        for cls in self.classes if requested=="any" else [requested]:
            require(cls in self.target.doc["classes"],"unknown allocation class")
            capacity=self.target.doc["classes"][cls]["capacity"]
            if top:
                physical=sum(v["class"]==cls for v in top["vertices"])
                capacity=physical if capacity=="unbounded" else min(capacity,physical)
            if capacity=="unbounded" or self._used(cls,start)+width<=capacity:return cls
        raise ContractError(f"E_SCHEDULE_INFEASIBLE: class capacity unavailable for {width} wires")

    def _register(self,b,start,requested,vertices=None,slot=None,category="scratch",scheme=None):
        cls=self._class(requested,b.width,start,vertices)
        top=self.target.doc.get("topology")
        placement=None
        if top:
            occupied={v for r in self.records if r["start"]<=start and (r["end"] is None or start<r["end"]) for v in r["vertices"]}
            if vertices is None:
                placement=[i for i,v in enumerate(top["vertices"]) if v["class"]==cls and i not in occupied][:b.width]
                require(len(placement)==b.width,"E_SCHEDULE_INFEASIBLE: no free topology vertices")
            else:
                require(not occupied.intersection(vertices),"E_SCHEDULE_INFEASIBLE: overlapping live vertex placements")
                placement=list(vertices)
        self.sequence+=1
        self.order+=1
        record={"bundle":b,"class":cls,"state":"clean" if slot is not None else b.state,"start":start,"end":None,"start_order":self.order,"end_order":None,"vertices":placement,"slot":slot,"category":category,"scheme":scheme,"id":f"{b.identity}@{self.sequence}"}
        self.records.append(record)
        record["latest_use_end"]=0
        self.live.setdefault(b.identity,[]).append(record)
        return record

    def interface(self,slot,b,vertices=None):
        specified=self.schedule.doc.get("interface_vertices")
        if specified is not None and vertices is None:
            require(self.interface_index<len(specified),"too few interface placement arrays")
            vertices=specified[self.interface_index]
        self.interface_index+=1
        self._register(b,0,"any",vertices,slot=slot)

    def allocate(self,b,chain=(),ordinal=0,step=None,phase=None,requested=None,category="scratch",scheme=None,start=None,vertices=None,select=True):
        # Resolve all selectors before applying any realisation to this leaf.
        selected=self._decision("alloc",chain,ordinal,step,phase) if select else None
        moment=self._start(chain,ordinal,step,phase) if start is None else start
        cls=selected["class"] if selected is not None else requested or b.cls
        placement=selected.get("vertices") if selected is not None else vertices
        for r in self.live.get(b.identity,[]):
            s=r["bundle"]
            require(r["end"] is not None or s.identity!=b.identity or b.offset+b.width<=s.offset or s.offset+s.width<=b.offset,"K27: double acquisition of a live allocation")
        r=self._register(b,moment,cls,placement,category=category,scheme=scheme)
        r["id"]="frame:"+digest(jcs(metadata_counts({"path":list(chain),"step":step,"phase":phase,"ordinal":ordinal,"scratch":b.identity,"occurrence":self.sequence})))
        self.cursor=moment;self.makespan=max(self.makespan,moment)
        return space_profile(r["class"],r["state"],b.width)

    def release(self,b,chain=(),ordinal=0,step=None,phase=None,start=None):
        r=self._find(b)
        require(r["bundle"].width==b.width and r["bundle"].offset==b.offset,"partial allocation release")
        minimum=max(r["start"],r["latest_use_end"])
        moment=self._start(chain,ordinal,step,phase,minimum) if start is None else start
        require(moment>=minimum,"E_SCHEDULE_INFEASIBLE: release violates dependency")
        self.order+=1;r["end_order"]=self.order
        r["end"]=moment;self.cursor=moment;self.makespan=max(self.makespan,moment)
        self.live[b.identity].remove(r)
        return space_profile(r["class"],r["state"],-b.width)

    def _wires(self,operands,controls):
        actual=bits(operands)
        require(len(actual)==len(set((w[0],w[1]) for w in actual)),"coincident gate operands")
        unique={}
        for bit in controls:unique.setdefault((bit[0],bit[1]),bit)
        return actual,tuple(unique.values())

    def _minimum(self,wires,records=None):
        minimum=0
        if records is None:records=[self._find(self._bit_bundle(bit)) for bit in wires]
        for bit,r in zip(wires,records):
            minimum=max(minimum,r["start"],self.dependencies.get((r["id"],bit[1]),0))
        return minimum

    def _native(self,op,wires,own,controls,eps,start,records=None,profile=None):
        if records is None:records=[self._find(self._bit_bundle(w)) for w in wires]
        p=profile if profile is not None else self.target.native_gate(op,[r["class"] for r in records],controls,eps,own)
        if p is None:raise ContractError(f"E_GATE_UNSUPPORTED: native scheme leaf {op}, c={controls}, classes={[r['class'] for r in records]}")
        require(not self.require_exact or p.error==0,"E_GATE_UNSUPPORTED: permutation region requires exact gates")
        require(start>=self._minimum(wires,records),"E_SCHEDULE_INFEASIBLE: native leaf violates dependency")
        top=self.target.doc.get("topology")
        if top:
            vertices=[r["vertices"][w[1]-r["bundle"].offset] for r,w in zip(records,wires)]
            edges={tuple(edge) for edge in top["edges"]}
            require(all(tuple(sorted((u,v))) in edges for i,u in enumerate(vertices) for v in vertices[:i]),"E_SCHEDULE_INFEASIBLE: §17 item 15: native leaf is not adjacent")
        end=start+p.time
        parallel=self.target.doc["capabilities"]["max_parallel"]
        if parallel!="unbounded" and p.time:
            self.parallel_events[start]=self.parallel_events.get(start,0)+1
            self.parallel_events[end]=self.parallel_events.get(end,0)-1
            active=0
            for time in sorted(self.parallel_events):
                active+=self.parallel_events[time]
                require(active<=parallel,"E_SCHEDULE_INFEASIBLE: max_parallel exceeded")
        for r,w in zip(records,wires):
            self.dependencies[(r["id"],w[1])]=end;r["latest_use_end"]=max(r["latest_use_end"],end)
        self.counts=add_maps(self.counts,p.counts);self.gates=add_maps(self.gates,p.gates);self.error+=p.error
        self.cursor=end;self.makespan=max(self.makespan,end)
        return p

    def gate(self,op,operands,controls=(),chain=(),ordinal=0,step=None,phase=None,params=None):
        require(len(params or [])==(1 if op in ["rx","ry","rz"] else 0),"gate parameter arity")
        for value in params or []:angle(value)
        actual,effective=self._wires(operands,controls)
        depth=self.target.doc["capabilities"]["max_predicate_depth"]
        require(depth=="unbounded" or len(effective)<=depth,"E_SCHEDULE_INFEASIBLE: max_predicate_depth exceeded")
        own={"cx":1,"ccx":2,"mcx":len(actual)-1}.get(op,0)
        targets=actual[own:]
        require(not {(b[0],b[1]) for b in targets}.intersection((b[0],b[1]) for b in effective),"effective control is a target")
        unique={}
        for bit in actual[:own]+effective:unique.setdefault((bit[0],bit[1]),bit)
        combined=tuple(unique.values())
        wires=combined+targets
        choice=self._decision("gate",chain,ordinal,step,phase) or {}
        # Resolve each physical lifetime once for this operation. No lifetime
        # reference is cached across a release/reacquire or scheme allocation.
        records=[self._find(self._bit_bundle(w)) for w in wires]
        classes=[r["class"] for r in records]
        is_exact=self.target.exact_native(op,classes,len(combined),own)
        eps=rational(choice.get("epsilon_share",0 if is_exact else self.default_share))
        start=self._start(chain,ordinal,step,phase,self._minimum(wires,records))
        realisation=choice.get("realisation")
        if not is_exact:self.nonexact_native_operations+=1
        if self.count_only:return Profile()
        native=self.target.native_gate(op,classes,len(combined),eps,own)
        if realisation in [None,"native"] and native is not None:return self._native(op,wires,own,len(combined),eps,start,records,native)
        require(realisation!="native",f"E_GATE_UNSUPPORTED: selected native {op} has no match")
        candidates=[s for s in self.target.doc["schemes"] if self.target.covers(s["realises"],op,len(combined)) and (realisation is None or s["name"]==realisation)]
        require(candidates,f"E_GATE_UNSUPPORTED: no selected realisation for {op}")
        scheme=candidates[0];environment={"k":F(own),"c":F(len(combined)),"eps":eps}
        if params:
            environment["theta"]=angle(params[0])
        anc=scheme["ancillae"]
        n=integer(expression(anc["count"],environment,self.target.doc["tables"]),0)
        b=Bundle(f"scheme:{len(self.records)}",n,anc["class"],state="borrowed" if anc["state"]=="dirty" else "clean")
        # A scheme has no ordinal/cost of its own. Its allocation and native
        # template are consequences of the one selected source operation.
        p=self.allocate(b,chain=chain,ordinal=ordinal,step=step,phase=phase,start=start,requested=b.cls,category="ancillae",scheme=scheme["name"],select=False)
        time=start
        for leaf in scheme["template"]:
            repeat=leaf.get("repeat")
            lo,hi=[integer(expression(repeat[k],environment,self.target.doc["tables"]),0) for k in ["from","to"]] if repeat else [0,1]
            require(hi>=lo,"reversed scheme repeat bounds")
            for i in range(lo,hi):
                bound=dict(environment,i=F(i));leaf_wires=[]
                leaf_params=[expression(x,bound,self.target.doc["tables"]) for x in leaf.get("params",[])]
                for parameter in leaf_params:angle(parameter)
                for w in leaf["wires"]:
                    if w in ["t","t2"]:
                        index=0 if w=="t" else 1
                        require(index<len(targets),"scheme references absent target")
                        leaf_wires.append(targets[index])
                    else:
                        m=re.fullmatch(r"([ca])\[(.*)\]",w);require(m,"invalid scheme wire")
                        index=integer(expression(loads(m[2]),bound,self.target.doc["tables"]),0)
                        if m[1]=="c":
                            require(index<len(combined),"scheme control outside bundle");leaf_wires.append(combined[index])
                        else:
                            require(index<n,"scheme ancilla outside bundle");leaf_wires.extend(bits([b.bit(index)]))
                require(len({(w[0],w[1]) for w in leaf_wires})==len(leaf_wires),"coincident scheme operands")
                leaf_op=leaf["gate"]
                leaf_own={"cx":1,"ccx":2,"mcx":len(leaf_wires)-1}.get(leaf_op,0)
                part=self._native(leaf_op,tuple(leaf_wires),leaf_own,leaf_own,eps,time)
                p=p.then(part);time+=part.time
        p=p.then(self.release(b,start=time))
        for w in wires:
            r=self._find(self._bit_bundle(w));self.dependencies[(r["id"],w[1])]=time;r["latest_use_end"]=max(r["latest_use_end"],time)
        self.cursor=time;self.makespan=max(self.makespan,time)
        return p

    def finish(self):
        specified=self.schedule.doc.get("interface_vertices")
        require(specified is None or self.interface_index==len(specified),"too many interface placement arrays")
        for r in self.records:
            if r["end"] is None:
                require(r["slot"] is not None,"K27: live allocation at region exit")
                r["end"]=self.makespan
                r["end_order"]=self.order+1
        peaks={};areas={}
        for cls in self.classes:
            changes={}
            for r in self.records:
                if r["class"]!=cls:continue
                width=r["bundle"].width;start,end=r["start"],r["end"]
                # Generated order breaks equal-time endpoint ties, including
                # zero-duration lifetimes. Later explicit releases may have
                # earlier times, so peak uses final intervals, not a prefix
                # snapshot taken when the allocation was encountered.
                lo,hi=(start,r["start_order"]),(end,r["end_order"])
                changes[lo]=changes.get(lo,0)+width;changes[hi]=changes.get(hi,0)-width
                key=(cls,r["state"])
                areas[key]=areas.get(key,F(0))+width*(end-start)
            active=peak=0
            for time in sorted(changes):active+=changes[time];peak=max(peak,active)
            peaks[cls]=peak
            cap=self.target.doc["classes"][cls]["capacity"]
            require(cap=="unbounded" or peak<=cap,f"E_SCHEDULE_INFEASIBLE: capacity exceeded for {cls}")
        top=self.target.doc.get("topology")
        if top:
            for i,r in enumerate(self.records):
                for other in self.records[:i]:
                    if max((r["start"],r["start_order"]),(other["start"],other["start_order"]))<min((r["end"],r["end_order"]),(other["end"],other["end_order"])):
                        require(not set(r["vertices"]).intersection(other["vertices"]),"E_SCHEDULE_INFEASIBLE: overlapping live vertex placements")
        rows={}
        for name,resource in self.target.doc["resources"].items():
            kind=resource["kind"]
            if kind in ["time","count"]:rows[escape(name)]=self.makespan if kind=="time" else self.counts.get(name,F(0))
            else:
                for cls in self.classes:
                    value=peaks[cls] if kind=="peak" else rational(resource.get("rate",{}).get(cls,1))*(areas.get((cls,"clean"),F(0))+areas.get((cls,"borrowed"),F(0))*rational(self.target.doc["classes"][cls]["dirty_rate"]))
                    rows[escape(name)+"["+escape(cls)+"]"]=F(value)
        return dict(sorted(rows.items()))

    def frame(self):
        """B5 descriptor in allocation order, with no storage sharing claim."""
        result={name:[] for name in ["slots","scratch","history","borrow","ancillae"]}
        for r in self.records:
            b=r["bundle"]
            if r["slot"] is not None:
                if r["slot"].startswith("control:"):continue
                group,role="slots",r["slot"].split(":")[0]
                role=r.get("role",role)
                record={"id":r["slot"],"role":role,"class":r["class"],"width":width_expression(b.width)}
            else:
                group=r["category"]
                if group=="scratch" and r["state"]=="borrowed":group="borrow"
                record={"id":r["id"],"class":r["class"],"width":width_expression(b.width)}
                if group in ["scratch","ancillae"]:record["state"]="dirty" if r["state"]=="borrowed" else "clean"
                if group=="ancillae":record["scheme"]=r["scheme"]
            result[group].append(record)
        return result


class OrdinalCounter:
    """Count source leaf domains before target expansion; never retain gates."""
    def __init__(self,catalog,schedule,admission=False):
        self.catalog,self.schedule=catalog,schedule
        self.admission=admission
        self.require_exact=False;self.count_only=False
        self.domains={};self.records=[{}];self.cleanup_decisions=[]

    def record(self,chain=(),ordinal=0,step=None,phase=None,**unused):
        key=self.catalog.address_key(chain,step,phase);sign=self.catalog.ordinal_sign()
        count,prior=self.domains.get(key,(0,sign))
        require(prior==sign,"one point domain has conflicting inverse orientations")
        self.domains[key]=(count+1,sign)
        return Profile()

    def gate(self,op,operands,controls=(),**address):return self.record(**address)
    def allocate(self,b,**address):return self.record(**address)
    def release(self,b,**address):return self.record(**address)
    def interface(self,slot,b,vertices=None):pass


class Admission:
    """K55 known-domain selector checks, before target realisation.

    Records no gates or costs. Unknown token-forwarded oracle invocations
    remain for the concrete ledger's prescribed operation-time checks.
    """
    def __init__(self,schedule):
        self.schedule=schedule;self.admission=True
        self.require_exact=False;self.count_only=False
        self.records=[{}];self.cleanup_decisions=[]

    def gate(self,op,wires,controls=(),params=None,**address):
        for kind in ["gate","start"]:self.schedule.pick(kind,**address)
        return Profile()

    def allocate(self,b,**address):
        for kind in ["alloc","start"]:self.schedule.pick(kind,**address)
        return Profile()

    def release(self,b,**address):
        self.schedule.pick("start",**address)
        return Profile()

    def interface(self,slot,b,vertices=None):pass


@dataclass(frozen=True)
class MintedToken:
    identity: int
    budget: tuple

@dataclass(frozen=True)
class HostToken:
    identity: int
    budget: tuple

@dataclass(frozen=True)
class RegisterRef:
    identity: int

@dataclass(frozen=True)
class RegisterId:
    identity: int

class ClassicalMachine:
    """Resolved classical execution with explicit lifetime and history state."""

    def __init__(self, source, fn, args, token_aliases=None):
        self.source = source
        self.function = fn
        parsed = resolved_arguments([ty for n, ty, r in fn.groups[0]], args, self.source.obj)
        self.token_types = (MintedToken, HostToken)
        self.registers = {}
        self.physical = {}
        self.placements = {}
        self.register_states = WireVersions()
        self.quantum_occurrences = []
        self.next_register = 0
        self.initial = {}
        labels = iter(token_aliases or [])
        for (n, ty, r), value in zip(fn.groups[0], parsed):
            self.initial[n] = (value, type_width(ty, self.source.obj.ptr)) if ty != 'token' else (HostToken(next(labels), tuple(value)) if token_aliases is not None else list(value), 0)
        self.memory, self.allocations = ({}, {})
        self.clock = 0
        self.layout = self.source.obj.sections.get('layout', {})
        image = bytes.fromhex(self.source.obj.sections.get('data', {}).get(self.layout.get('block_image'), ''))
        self.blocks = {sector: tuple(image[sector * 512:(sector + 1) * 512]) for sector in range(len(image) // 512)}
        self.bump = integer(self.layout.get('heap_base', 0), 0)
        for n, g in self.layout.get('globals', {}).items():
            base = integer(g['base'], 0)
            image = bytes.fromhex(self.source.obj.sections['data'][g['image']])
            self.allocations[base] = (len(image), True)
            self.memory.update({base + i: b for i, b in enumerate(image)})
        self.atop = len(self.allocations)
        self.history = []
        self.segments = []
        self.version_serial = 0
        self.reversed_steps = 0
        self.fault_reason = None

    def create(self, parts, parent=None):
        self.next_register += 1
        self.registers[self.next_register] = {'parts': tuple(parts), 'state': 'live', 'parent': parent}
        return (RegisterRef(self.next_register), 'qreg')

    def register_snapshot(self):
        return ({identity: dict(record) for identity, record in self.registers.items()}, dict(self.physical), dict(self.register_states.ranges), dict(self.placements))

    def restore_registers(self, snapshot):
        old_registers, old_physical, old_states, old_placements = snapshot
        profile = Profile()
        for identity in self.physical.keys() - old_physical.keys():
            b = self.physical[identity]
            profile = profile.then(space_profile(b.cls, 'clean', -b.width))
        for identity in old_physical.keys() - self.physical.keys():
            b = old_physical[identity]
            profile = profile.then(space_profile(b.cls, 'clean', b.width))
        self.registers.clear()
        self.registers.update({identity: dict(record) for identity, record in old_registers.items()})
        self.physical.clear()
        self.physical.update(old_physical)
        self.register_states.ranges.clear()
        self.register_states.ranges.update(old_states)
        self.placements.clear()
        self.placements.update(old_placements)
        return profile

    def register_width(self, record):
        return sum((part.width for part in record['parts']))

    def overlaps(self, a, b):
        return any((x.identity == y.identity and x.offset < y.offset + y.width and (y.offset < x.offset + x.width) for x in a for y in b))

    def transfer(self, ty, value):
        if ty.startswith('qreg['):
            if value[1] != 'qreg':
                return False
            record = self.registers.get(value[0].identity)
            if record is None:
                return False
            expected = ty[5:-1]
            return expected == '*' or self.register_width(record) == int(expected)
        return value[1] != 'qreg'

    def identity_body(self, function):
        if self.source.empty_cleanups(function) == {(i.block, i.ordinal) for i in function.code}:
            return True
        stack = []
        for row in function.code:
            op, actual = (row.op, tuple(row.args))
            inverse = False
            self_inverse = False
            if op == 'adj':
                op, actual = (actual[0], actual[1:])
                inverse = True
            if op in GATES and op not in ['rx', 'ry', 'rz']:
                opposite = ADJOINT.get(op, op)
                canonical = min(op, opposite)
                inverse ^= op != canonical
                self_inverse = op == opposite
                op = canonical
            elif op == 'action_call':
                child = self.source.obj.functions[actual[0].removeprefix('@')]
                if self.identity_body(child):
                    continue
            else:
                return False
            key = (op, actual)
            if stack and stack[-1][0] == key and (self_inverse or stack[-1][1] != inverse):
                stack.pop()
            else:
                stack.append((key, inverse))
        return not stack

    def equal_values(self, left, right):
        if len(left) != len(right):
            return False
        for (x, wx), (y, wy) in zip(left, right):
            if wx != wy:
                return False
            if wx == 0 and isinstance(x, list) and isinstance(y, list) and (x == y) and (x is not y):
                raise ContractError('EST-CONTEXT-03: token identity aliasing is absent from tuple-only root arguments; supply token_aliases (K91) or an explicit conditional step bound')
            if isinstance(x, RegisterId) != isinstance(y, RegisterId):
                require(x == 0 or y == 0, 'opaque register id boundary comparison needs explicit binding evidence')
            if x != y:
                return False
        return True

    def valid_token(self, value):
        return not isinstance(value, MintedToken) or self.history[value.identity]['active']

    def quantum_region(self, name, values, budget, bindings, controls, adjoint=False, raw_inverse=False, identities=None):
        if 'topology' not in self.source.target.doc:
            return self.source.region(name, values, budget, bindings, controls, adjoint, raw_inverse=raw_inverse, token_context=identities)
        prior = self.source.catalog
        catalog = Catalog(prior.text, self.source.target)
        request = {'closure_hash': self.source.obj.identities(closure=True)[name], 'target_hash': self.source.target.hash, 'region': name, 'variant': 'forward', 'inherited_controls': len(set(((b[0], b[1]) for b in controls))), 'budget': budget, 'params_hash': digest(jcs(values)), 'epsilon': 0, 'expansion': {'name': 'ref', 'version': '0.9', 'hash': catalog.hash}, 'scheduler': {'name': 'bennett-estimate-default', 'version': '0.1.0'}}
        if identities is not None:
            request['token_aliases'] = canonical_token_aliases(identities)
        ledger = Ledger(self.source.target, Schedule({'bindings': request, 'entries': []}, self.source.obj, name))
        catalog.ledger = ledger
        catalog.prebound_interfaces = True
        baseline = {}
        for b in self.physical.values():
            ledger._register(b, 0, b.cls, list(self.placements[b.identity]), slot='register:' + b.identity)
            baseline[b.cls] = baseline.get(b.cls, 0) + b.width
        self.source.catalog = catalog
        try:
            profile = self.source.region(name, values, budget, bindings, controls, adjoint, raw_inverse=raw_inverse, token_context=identities)
            require(ledger.finish() == profile.resources(self.source.target, baseline), 'CC/R default topology ledger/profile resource mismatch')
            return profile
        finally:
            prior.visits += catalog.visits
            self.source.catalog = prior

    def execute(self, function, values):
        env = dict(values)
        versions = {n: 0 for n in env}

        def put(n, value):
            self.version_serial += 1
            env[n] = value
            versions[n] = self.version_serial
        block = next(iter(function.blocks))
        p, steps = (Profile(), 0)

        def get(n):
            if n in env:
                return env[n]
            if re.fullmatch('-?(0|[1-9][0-9]*)', n):
                return (int(n), self.source.obj.ptr)
            raise ContractError(f'classical value has no current instance: {n}')

        def register(n, view=False):
            value = get(n)
            if value[1] != 'qreg':
                return None
            record = self.registers.get(value[0].identity)
            if record is None:
                return None
            if record['state'] != 'live' or (record['parent'] is not None and (not view)):
                return None
            return record

        def unsigned64(n, literal_minimum=0):
            if n.isdigit():
                return integer(n, literal_minimum)
            value, w = get(n)
            require(w == 64, '§3.3: register size/index operand requires i64')
            return value

        def jump(label):
            m = re.fullmatch('\\^([^ (]+)\\((.*?)\\)', label)
            require(m and m[1] in function.blocks, 'invalid branch label')
            formals = function.blocks[m[1]][0]
            actuals = m[2].split(', ') if m[2] else []
            require(len(formals) == len(actuals), 'branch argument arity')
            resolved = [get(a) for a in actuals]
            if not all((self.transfer(ty, value) for (n, ty, r), value in zip(formals, resolved))):
                return None
            for (n, ty, r), value in zip(formals, resolved):
                put(n, value)
            return m[1]
        while True:
            code = function.blocks[block][1]
            jumped = False
            for inst in code:
                op, a = (inst.op, inst.args)
                pure = inst.classical_kind in {ClassicalKind.BRANCH, ClassicalKind.ARITHMETIC} or op in ['qreg.width', 'qreg.id', 'qreg.from_id'] or op.startswith('load.i')
                frame_index = len(self.history)
                self.history.append({'active': True, 'pure': pure, 'marker': op == 'uncall'})
                if op in ['qreg.new', 'qreg.free', 'qreg.slice', 'qreg.concat', 'action_call', 'oracle_call', 'adj', 'ctl']:
                    self.history[frame_index]['registers'] = self.register_snapshot()
                p = p.then(Profile(time=rational(self.source.target.doc['capabilities']['classical_step_time'])))
                steps += 1
                result = None
                match inst.classical_kind:
                    case ClassicalKind.ARITHMETIC:
                        result, failed = self.arithmetic(inst, get)
                        if failed:
                            return (p, steps, [], True)
                    case ClassicalKind.BRANCH:
                        block = jump(a[0] if len(a) == 1 else a[1] if get(a[0])[0] else a[2])
                        jumped = True
                        break
                    case ClassicalKind.RETURN:
                        results = [get(n) for n in a]
                        if not all((self.transfer(ty, value) for (n, ty, r), value in zip(function.groups[1], results))):
                            return (p, steps, [], True)
                        return (p, steps, results, False)
                    case ClassicalKind.FAULT:
                        return (p, steps, [], True)
                    case ClassicalKind.CALL:
                        callee = self.source.obj.functions[a[0].removeprefix('@')]
                        params = callee.groups[0]
                        require(len(params) == len(a) - 1, 'call argument arity')
                        actuals = [get(actual) for actual in a[1:]]
                        if not all((self.transfer(ty, value) for (n, ty, r), value in zip(params, actuals))):
                            return (p, steps, [], True)
                        before = (dict(self.memory), dict(self.allocations), self.bump, self.clock, self.atop, dict(self.blocks))
                        before_registers = self.register_snapshot()
                        previous = {n: (env.get(n), versions.get(n)) for n in inst.lhs}
                        cp, cs, results, failed = self.execute(callee, {n: value for (n, ty, r), value in zip(params, actuals)})
                        p = p.then(cp)
                        steps += cs
                        if failed:
                            return (p, steps, [], True)
                        require(len(results) == len(inst.lhs), 'call result arity')
                        for n, value in zip(inst.lhs, results):
                            put(n, value)
                        self.segments.append({'name': callee.name, 'args': actuals, 'results': results, 'start': frame_index, 'end': len(self.history), 'active': True, 'before': before, 'before_registers': before_registers, 'env': env, 'versions': versions, 'previous': previous, 'produced': {n: versions[n] for n in inst.lhs}})
                        continue
                    case ClassicalKind.UNCALL:
                        require(len(a) == 3, 'uncall needs argument/result lists')
                        pending = [s for s in self.segments if s['active']]
                        if not pending:
                            return (p, steps, [], True)
                        segment = max(pending, key=lambda s: s['end'])
                        arguments = [get(n) for n in list_operand(a[1])]
                        results = [get(n) for n in list_operand(a[2])]
                        if segment['name'] != a[0].removeprefix('@') or any((f.get('measured', False) for f in self.history[segment['start']:segment['end']])) or any((f['active'] and (not f['pure']) and (not f['marker']) for f in self.history[segment['end']:frame_index])) or (not self.equal_values(segment['args'], arguments)) or (not self.equal_values(segment['results'], results)):
                            return (p, steps, [], True)
                        for frame in reversed(self.history[segment['start']:segment['end']]):
                            if not frame['active'] or frame['marker']:
                                continue
                            p = p.then(Profile(time=rational(self.source.target.doc['capabilities']['classical_step_time'])))
                            self.reversed_steps += 1
                            if 'inverse' in frame:
                                p = p.then(frame['inverse']())
                            if 'registers' in frame:
                                p = p.then(self.restore_registers(frame['registers']))
                            frame['active'] = False
                        p = p.then(self.restore_registers(segment['before_registers']))
                        old_memory, old_allocations, self.bump, self.clock, self.atop, old_blocks = segment['before']
                        self.memory.clear()
                        self.memory.update(old_memory)
                        self.allocations.clear()
                        self.allocations.update(old_allocations)
                        self.blocks.clear()
                        self.blocks.update(old_blocks)
                        for n, version in segment['produced'].items():
                            if segment['versions'].get(n) != version:
                                continue
                            value, prior_version = segment['previous'][n]
                            if prior_version is None:
                                segment['env'].pop(n, None)
                                segment['versions'].pop(n, None)
                            else:
                                segment['env'][n] = value
                                segment['versions'][n] = prior_version
                        for child in self.segments:
                            if segment['start'] <= child['start'] and child['end'] <= segment['end']:
                                child['active'] = False
                    case ClassicalKind.ALLOCATE:
                        n = get(a[0])[0]
                        base = self.bump
                        self.bump += max(1, n)
                        if self.bump > integer(self.layout.get('heap_base', 0)) + integer(self.layout.get('heap_limit_max', 0)) or self.atop >= 1 << integer(self.layout.get('A_tab', 0)):
                            return (p, steps, [], True)
                        self.allocations[base] = (n, False)
                        self.atop += 1
                        result = (base, self.source.obj.ptr)
                    case ClassicalKind.FREE:
                        base = get(a[0])[0]
                        if base not in self.allocations or self.allocations[base][1]:
                            return (p, steps, [], True)
                        del self.allocations[base]
                    case ClassicalKind.MEMORY:
                        width = int(op.split('.i')[-1])
                        address = get(a[0])[0]
                        size = width // 8
                        if not any((base <= address and address + size <= base + n for base, (n, pinned) in self.allocations.items())):
                            return (p, steps, [], True)
                        if op.startswith('load'):
                            require(all((self.memory.get(address + i, 0) is not None for i in range(size))), 'cost control depends on unresolved effect/measurement data; a path bound is required')
                            content = [self.memory.get(address + i, 0) for i in range(size)]
                            if any((isinstance(byte, tuple) for byte in content)):
                                require(size == 8 and all((byte == (content[0][0], i) for i, byte in enumerate(content))) and isinstance(content[0][0], RegisterId), 'opaque register id partial load needs explicit binding evidence')
                                result = (content[0][0], width)
                            else:
                                result = (sum((byte << 8 * i for i, byte in enumerate(content))), width)
                        else:
                            value = get(a[1])[0]
                            if isinstance(value, RegisterId):
                                require(size == 8, 'opaque register id partial store needs explicit binding evidence')
                                self.memory.update({address + i: (value, i) for i in range(size)})
                            else:
                                self.memory.update({address + i: value >> 8 * i & 255 for i in range(size)})
                    case ClassicalKind.MINT:
                        require(len(a) == 5 and a[0].startswith('@'), 'budget.mint needs oracle and four i64 components')
                        name = a[0][1:]
                        require(name in self.source.obj.functions and self.source.obj.functions[name].kind == 'oracle', 'budget.mint requires linked oracle')
                        components = [get(n) for n in a[1:]]
                        require(all((width == 64 for value, width in components)), 'budget.mint components must be i64')
                        token = [str(value) for value, width in components]
                        try:
                            validate_budget(token, self.source.obj)
                        except BudgetConstraintError as error:
                            self.fault_reason = str(error)
                            return (p, steps, [], True)
                        result = (MintedToken(frame_index, tuple(token)), 0)
                    case ClassicalKind.REGISTER:
                        change, result, failed = self.register_operation(inst, get, register, unsigned64)
                        p = p.then(change)
                        if failed:
                            return (p, steps, [], True)
                    case ClassicalKind.QUANTUM:
                        change, failed = self.quantum_call(inst, get, register, frame_index)
                        p = p.then(change)
                        if failed:
                            return (p, steps, [], True)
                    case ClassicalKind.MEASURE:
                        record = register(a[0])
                        if record is None:
                            return (p, steps, [], True)
                        width = self.register_width(record)
                        measured = width if op == 'measure' else integer(op[9:], 1)
                        require(1 <= measured <= 128, '§3.3: measurement width must be in 1..128')
                        if measured != width:
                            return (p, steps, [], True)
                        require(all((clean for identity, lo, hi, version, clean in self.register_states.capture(record['parts']))), 'measurement-dependent path/cleanliness evidence remains pending; no exact estimate emitted')
                        for b in record['parts']:
                            require(b.identity in self.physical, 'measured allocation identity is not live')
                            del self.physical[b.identity]
                            del self.register_states.ranges[b.identity]
                            self.placements.pop(b.identity, None)
                            p = p.then(space_profile(b.cls, 'clean', -b.width))
                        record['state'] = 'consumed'
                        self.history[frame_index]['measured'] = True
                        result = (0, measured)
                    case ClassicalKind.EFFECT:
                        dev = a[0]
                        if dev not in ['clock.read', 'entropy.read', 'console.write', 'block.read', 'block.write']:
                            return (p, steps, [], True)
                        ptr = get(a[2] if dev.startswith('block.') else a[1])[0]
                        size = 8 if dev == 'clock.read' else get(a[2])[0] if dev in ['entropy.read', 'console.write'] else 512
                        if not any((base <= ptr and ptr + size <= base + n for base, (n, _) in self.allocations.items())):
                            return (p, steps, [], True)
                        if dev == 'console.write':
                            continue
                        if dev == 'clock.read':
                            self.memory.update({ptr + i: self.clock >> 8 * i & 255 for i in range(8)})
                            self.clock = (self.clock + 1) % (1 << 64)
                        elif dev in ['block.read', 'block.write']:
                            sector, sector_width = get(a[1])
                            require(sector_width == 64, '§7.3: block sector requires i64')
                            require(isinstance(sector, int), 'opaque register id cannot resolve a block-sector address')
                            if dev == 'block.read':
                                self.memory.update({ptr + i: byte for i, byte in enumerate(self.blocks.get(sector, (0,) * 512))})
                            else:
                                self.blocks[sector] = tuple((self.memory.get(ptr + i, 0) for i in range(512)))
                        elif dev == 'entropy.read' and size == 0:
                            continue
                        else:
                            raise ContractError(f'exact classical effect-state binding pending: {dev}; use an explicit conditional step bound')
                    case _:
                        raise ContractError(f'classical source binding not implemented: {op}; no exact estimate emitted')
                if result is not None:
                    require(len(inst.lhs) == 1, 'classical result arity')
                    put(inst.lhs[0], result)
            require(jumped, 'classical block has no terminator')
            if block is None:
                return (p, steps, [], True)

    def arithmetic(self, inst, get):
        op, a = (inst.op, inst.args)
        result = None
        if op.startswith('const.i'):
            width = integer(op[7:], 1)
            result = (integer(a[0]) % (1 << width), width)
        elif op in ['add', 'sub', 'mul', 'and', 'or', 'xor', 'shl', 'lshr', 'ashr', 'udiv', 'urem', 'sdiv', 'srem'] or op.startswith('icmp.'):
            (x, w), (y, v) = (get(a[0]), get(a[1]))
            require(w == v, 'classical operand width mismatch')
            if isinstance(x, RegisterId) or isinstance(y, RegisterId):
                require(op in ['icmp.eq', 'icmp.ne'] and (isinstance(x, RegisterId) and isinstance(y, RegisterId) or x == 0 or y == 0), 'opaque register id bits cannot select an exact classical path')
                result = (int(x == y if op == 'icmp.eq' else x != y), 1)
                require(len(inst.lhs) == 1, 'classical result arity')
                return (result, False)

            def signed(x):
                return x - (1 << w) if x & 1 << w - 1 else x
            if op.startswith('icmp.'):
                pred = op[5:]
                if pred.startswith('s'):
                    x, y = (signed(x), signed(y))
                value = {'eq': lambda: x == y, 'ne': lambda: x != y, 'ult': lambda: x < y, 'ule': lambda: x <= y, 'slt': lambda: x < y, 'sle': lambda: x <= y}[pred]()
                result = (int(value), 1)
            else:
                if op in ['udiv', 'urem', 'sdiv', 'srem'] and (y == 0 or (op.startswith('s') and signed(x) == -(1 << w - 1) and (signed(y) == -1))):
                    return (None, True)
                if op in ['sdiv', 'srem']:
                    sx, sy = (signed(x), signed(y))
                    q = abs(sx) // abs(sy) * (-1 if (sx < 0) != (sy < 0) else 1)
                    value = q if op == 'sdiv' else sx - q * sy
                else:
                    value = {'add': lambda: x + y, 'sub': lambda: x - y, 'mul': lambda: x * y, 'and': lambda: x & y, 'or': lambda: x | y, 'xor': lambda: x ^ y, 'shl': lambda: x << y if y < w else 0, 'lshr': lambda: x >> y if y < w else 0, 'ashr': lambda: signed(x) >> y if y < w else 0, 'udiv': lambda: x // y, 'urem': lambda: x % y}[op]()
                result = (value % (1 << w), w)
        elif op.startswith(('zext.i', 'sext.i', 'trunc.i', 'ptrtoint.i')) or op == 'inttoptr':
            x, w = get(a[0])
            width = self.source.obj.ptr if op == 'inttoptr' else int(op.split('.i')[-1])
            require(not isinstance(x, RegisterId), 'opaque register id bit conversion needs explicit binding evidence')
            if op.startswith('sext') and x & 1 << w - 1:
                x -= 1 << w
            result = (x % (1 << width), width)
        elif op == 'select':
            result = get(a[1] if get(a[0])[0] else a[2])
        else:
            raise ContractError('unexpected arithmetic opcode: ' + op)
        return (result, False)

    def register_operation(self, inst, get, register, unsigned64):
        op, a = (inst.op, inst.args)
        result = None
        p = Profile()
        if op == 'qreg.new':
            cls, n = a
            size = unsigned64(n, 1)
            choices = sorted(self.source.target.doc['classes'], key=lambda name: name.encode('utf-16-be')) if cls == 'any' else [cls]
            require(all((c in self.source.target.doc['classes'] for c in choices)), 'unknown register class')

            def available(c):
                used = sum((b.width for b in self.physical.values() if b.cls == c))
                capacity = self.source.target.doc['classes'][c]['capacity']
                if 'topology' in self.source.target.doc:
                    vertices = sum((v['class'] == c for v in self.source.target.doc['topology']['vertices']))
                    capacity = vertices if capacity == 'unbounded' else min(capacity, vertices)
                return capacity == 'unbounded' or used + size <= capacity
            selected = next((c for c in choices if available(c)), None)
            if selected is None:
                return (p, None, True)
            parts = []
            if size:
                b = self.source.fresh('register', size, selected)
                parts = [b]
                self.physical[b.identity] = b
                if 'topology' in self.source.target.doc:
                    occupied = {v for vertices in self.placements.values() for v in vertices}
                    self.placements[b.identity] = tuple((i for i, v in enumerate(self.source.target.doc['topology']['vertices']) if v['class'] == selected and i not in occupied))[:size]
                    require(len(self.placements[b.identity]) == size, 'register topology capacity/placement mismatch')
                self.register_states.acquire(b)
                p = p.then(space_profile(selected, 'clean', size))
            result = self.create(parts)
        elif op in ['qreg.width', 'qreg.id', 'qreg.free', 'qreg.slice', 'qreg.concat']:
            record = register(a[0])
            if record is None:
                return (p, None, True)
            if op == 'qreg.width':
                result = (self.register_width(record), 64)
            elif op == 'qreg.id':
                result = (RegisterId(get(a[0])[0].identity), 64)
            elif op == 'qreg.free':
                require(all((clean for identity, lo, hi, version, clean in self.register_states.capture(record['parts']))), 'register cleanliness needs source history evidence; no exact estimate emitted')
                for b in record['parts']:
                    require(b.identity in self.physical, 'register allocation identity is not live')
                    del self.physical[b.identity]
                    self.placements.pop(b.identity, None)
                    del self.register_states.ranges[b.identity]
                    p = p.then(space_profile(b.cls, 'clean', -b.width))
                record['state'] = 'consumed'
            elif op == 'qreg.slice':
                lo, length = (unsigned64(a[1]), unsigned64(a[2], 1))
                if lo + length > self.register_width(record):
                    return (p, None, True)
                parts = []
                offset = 0
                for b in record['parts']:
                    begin, end = (max(lo, offset), min(lo + length, offset + b.width))
                    if begin < end:
                        parts.append(Bundle(b.identity, end - begin, b.cls, b.offset + begin - offset, b.state))
                    offset += b.width
                result = self.create(parts, get(a[0])[0].identity)
                record['state'] = 'viewed'
            else:
                other = register(a[1])
                if other is None or other is record:
                    return (p, None, True)
                result = self.create(record['parts'] + other['parts'])
                record['state'] = other['state'] = 'consumed'
        elif op == 'qreg.from_id':
            identity, w = get(a[0])
            require(w == 64, 'qreg.from_id requires i64')
            require(isinstance(identity, RegisterId) or identity == 0, 'opaque register id lookup needs explicit binding evidence')
            identity = identity.identity if isinstance(identity, RegisterId) else 0
            record = self.registers.get(identity)
            if record is None or record['state'] != 'live' or record['parent'] is not None:
                return (p, None, True)
            result = (RegisterRef(identity), 'qreg')
        else:
            raise ContractError('unexpected register_operation opcode: ' + op)
        return (p, result, False)

    def quantum_call(self, inst, get, register, frame_index):
        op, a = (inst.op, inst.args)
        p = Profile()
        if op in ['action_call', 'oracle_call', 'adj', 'ctl']:
            call_op, actual = (op, list(a))
            controlled = []
            control_records = []
            source_adjoint = False
            while call_op in ['ctl', 'adj']:
                index = 1 if call_op == 'ctl' else 0
                if index:
                    control = register(actual[0], True)
                    if control is None or self.register_width(control) != 1:
                        return (p, True)
                    controlled += control['parts']
                    control_records.append((control, True))
                else:
                    source_adjoint = not source_adjoint
                call_op, actual = (actual[index], actual[index + 1:])
            require(call_op in ['action_call', 'oracle_call'], 'invalid CC/R region call')
            child = self.source.obj.functions[actual[0].removeprefix('@')]
            if call_op == 'action_call':
                actual_groups = [list_operand(x) for x in actual[1:]]
                tuple_ = ['0'] * 4
            else:
                token, token_width = get(actual[1])
                require(token_width == 0, 'oracle invocation requires token')
                if not self.valid_token(token):
                    return (p, True)
                tuple_ = list(token.budget) if isinstance(token, self.token_types) else list(token)
                actual_groups = [list_operand(actual[2]), [actual[3]], [actual[4]], list_operand(actual[5]), list_operand(actual[6])]
            groups = child.groups[:5] if child.kind == 'oracle' else child.groups[:4]
            require(all((len(g) == len(v) for g, v in zip(groups, actual_groups))), 'region call argument arity')
            interface = {}
            records = list(control_records)
            slots = []
            encoded = []
            for index, (group, actuals) in enumerate(zip(groups[:-1], actual_groups[:-1])):
                group_readonly = index == 0 if child.kind == 'oracle' else index == 1
                for (name, ty, role), argument in zip(group, actuals):
                    record = register(argument, True)
                    if record is None or self.register_width(record) != type_width(ty, self.source.obj.ptr):
                        return (p, True)
                    readonly = group_readonly or (ty.startswith('region[') and role == 'in')
                    parts = record['parts']
                    if any((self.overlaps(parts, prior) and (not (readonly and read)) for prior, read in slots)) or (not readonly and self.overlaps(parts, controlled)):
                        return (p, True)
                    slots.append((parts, readonly))
                    records.append((record, readonly))
                    interface[name] = list(parts)
            for (name, ty, role), argument in zip(groups[-1], actual_groups[-1]):
                value, w = get(argument)
                if ty == 'token' and (w != 0 or not self.valid_token(value)):
                    return (p, True)
                encoded.append(list(value.budget) if isinstance(value, self.token_types) else value if ty in ['f64', 'token'] else str(value))
            call_arguments = [get(argument) for argument in actual_groups[-1]]
            if call_op == 'oracle_call':
                call_arguments.append((token, token_width))
            context_tokens = ([token] if call_op == 'oracle_call' else []) + [get(argument)[0] for (n, ty, r), argument in zip(groups[-1], actual_groups[-1]) if ty == 'token']
            identities = tuple((('host' if isinstance(value, HostToken) else 'mint', value.identity) for value in context_tokens)) if all((isinstance(value, self.token_types) for value in context_tokens)) else None
            controls = tuple((bit for b in controlled for bit in bits([b])))
            candidate = self.source.obj.sections.get('schedule', {})
            if candidate.get('entries') or 'interface_vertices' in candidate:
                bound = candidate['bindings']
                known = {'region': child.name, 'target_hash': self.source.target.hash, 'params_hash': digest(jcs(encoded)), 'inherited_controls': len(set(((bit[0], bit[1]) for bit in controls)))}
                matches = all((integer(bound[key], 0) == value if key == 'inherited_controls' else bound.get(key) == value for key, value in known.items()))
                matches = matches and [integer(n, 0) for n in bound['budget']] == [integer(n, 0) for n in tuple_] and (decimal_value(bound['epsilon']) == 0)
                if matches:
                    matches = bound['closure_hash'] == self.source.obj.identities(closure=True)[child.name]
                require(not matches, 'CC/R nested quantum schedule replay remains pending for these invocation bindings')
            cp = self.quantum_region(child.name, encoded, tuple_, interface, controls, source_adjoint, identities=identities)
            p = p.then(cp)

            def reverse_region(name=child.name, values=list(encoded), budget=list(tuple_), bindings=dict(interface), control_context=controls, adjoint=source_adjoint, identities=identities):
                return self.quantum_region(name, values, budget, bindings, control_context, adjoint, raw_inverse=True, identities=identities)
            self.history[frame_index]['inverse'] = reverse_region
            identity = child.kind in ['action', 'perm_action'] and self.identity_body(child)
            touched = [b for parts, _ in slots for b in parts] + controlled
            written = [b for parts, read in slots if not read for b in parts]
            if touched and (not identity):
                state = self.register_states.capture(touched)
                active_versions = {version for name, lo, hi, version, clean in state}
                key = (call_op, child.name, tuple((tuple(((b.identity, b.offset, b.width) for b in parts)) for parts, _ in slots)), controls)
                previous = self.quantum_occurrences[next(iter(active_versions)) - 1] if len(active_versions) == 1 and 0 not in active_versions else None
                if previous is not None and previous['key'] == key and (call_op == 'oracle_call' or previous['adjoint'] != source_adjoint) and self.equal_values(previous['arguments'], call_arguments):
                    self.register_states.restore(previous['states'])
                else:
                    self.quantum_occurrences.append({'key': key, 'arguments': call_arguments, 'adjoint': source_adjoint, 'states': state})
                    self.register_states.assign(touched, len(self.quantum_occurrences))
                    self.register_states.assign(written, len(self.quantum_occurrences), False)
            for record, readonly in records:
                if record['parent'] is not None:
                    record['state'] = 'consumed'
                    self.registers[record['parent']]['state'] = 'live'
        else:
            raise ContractError('unexpected quantum_call opcode: ' + op)
        return (p, False)

    def run(self):
        p, steps, _, failed = self.execute(self.function, self.initial)
        self.source.classical_status = 'FAILED' if failed else 'COMPLETED'
        self.source.reversed_classical_steps = self.reversed_steps
        self.source.classical_fault_reason = self.fault_reason
        return (p, steps)


class CleanupUnestablished(Exception):
    """An exact proof mechanism is unavailable; this is no source rejection."""


class CleanupKind(Enum):
    GATE=auto()
    ACQUIRE=auto()
    RELEASE=auto()
    OPAQUE=auto()


class CleanupGate(Enum):
    X="x"
    CX="cx"
    CCX="ccx"
    MCX="mcx"
    SWAP="swap"
    S="s"
    SDG="sdg"
    T="t"
    TDG="tdg"
    CZ="cz"
    H="h"

    def own_controls(self,width):
        return {CleanupGate.CX:1,CleanupGate.CCX:2,CleanupGate.MCX:width-1}.get(self,0)

    def bind(self,wires,controls):
        own=self.own_controls(len(wires))
        wires=tuple(sorted(wires[:own]))+wires[own:]
        return self,wires,tuple(sorted(set(controls)-set(wires[:own])))


@dataclass
class CleanupRow:
    node: dict
    meta: dict
    kind: CleanupKind
    gates: tuple = ()
    bundle: object = None
    capture: object = None

    def access(self):
        reads,writes=set(),set()
        for op,wires,controls in self.gates:
            own=op.own_controls(len(wires))
            if op in [CleanupGate.S,CleanupGate.SDG,CleanupGate.T,CleanupGate.TDG,CleanupGate.CZ]:reads.update(wires)
            elif op==CleanupGate.SWAP:writes.update(wires)
            else:reads.update(wires[:own]);writes.update(wires[own:])
            reads.update(controls)
        return reads,writes

    def permutation(self):
        return self.kind==CleanupKind.GATE and all(op in [CleanupGate.X,CleanupGate.CX,CleanupGate.CCX,CleanupGate.MCX,CleanupGate.SWAP] for op,_,_ in self.gates)


class CleanupVersions:
    """Occurrence matching is separate from the composed semantic proof."""
    def __init__(self,rows,labels=None):
        self.current={};self.entries={};self.before=[];self.entry_before=[];self.after=[];self.pairs={};history={}
        for index,row in enumerate(rows):
            version=index+1 if labels is None else labels[index]+1
            reads,writes=row.access()
            for bit in reads|writes:self.current.setdefault(bit,0);self.entries.setdefault(bit,0)
            if row.kind==CleanupKind.RELEASE:
                # An enclosing captured history may own the allocation. Its
                # entry binding is unestablished here, never an invented zero.
                for bit in bits([row.bundle]):self.current.setdefault(bit,None);self.entries.setdefault(bit,None)
            self.before.append(dict(self.current));self.entry_before.append(dict(self.entries))
            if row.kind==CleanupKind.ACQUIRE:
                # A clean allocation is a new lifetime, even if lowering can
                # reuse its storage descriptor after an earlier release.
                for bit in bits([row.bundle]):self.current[bit]=-version;self.entries[bit]=-version
            elif row.kind==CleanupKind.OPAQUE:
                history.clear()
                self.current={bit:version for bit in self.current}
            elif row.permutation():
                inputs=tuple((bit,self.current[bit]) for bit in sorted(reads))
                outputs=tuple((bit,self.current[bit]) for bit in sorted(writes))
                key=(row.meta["kind"],row.gates,inputs,outputs)
                previous=history.get(key)
                if previous is not None:
                    computing,entry=previous
                    self.pairs[index]=computing;self.current.update(entry)
                else:
                    entry=dict(outputs)
                    for bit in writes:self.current[bit]=version
                    outputs=tuple((bit,self.current[bit]) for bit in sorted(writes))
                    history[(row.meta["kind"],row.gates,inputs,outputs)]=(index,entry)
            elif writes:
                for bit in writes:self.current[bit]=version
            self.after.append(dict(self.current))


class CleanupSemantics:
    """Exact Boolean maps and eighth-turn phases on arbitrary input bits.

    Boolean functions use algebraic normal form. Phase functions use integer
    multilinear polynomials modulo eight, including their constant term.
    Equality therefore includes global phase, also under effective controls.
    The symbolic-work allowance defers a proof; it never changes a verdict.
    """
    MAX_TERMS=4096

    def __init__(self):
        self.values={};self.entries={};self.phase={};self.clean=True

    @staticmethod
    def product(left,right):
        result=set()
        for a in left:
            for b in right:
                term=a|b
                if term in result:result.remove(term)
                else:result.add(term)
        if len(result)>CleanupSemantics.MAX_TERMS:raise CleanupUnestablished("Boolean proof term allowance exceeded")
        return frozenset(result)

    def value(self,bit):
        if bit not in self.values:self.values[bit]=frozenset([frozenset([bit])])
        return self.values[bit]

    def predicate(self,controls):
        result=frozenset([frozenset()])
        for bit in controls:result=self.product(result,self.value(bit))
        return result

    def add_phase(self,predicate,coefficient):
        # XOR(a,b)=a+b-2ab over integer Boolean functions. Retain the
        # constant monomial: discarding it would lose controlled global phase.
        polynomial={}
        for term in sorted(predicate,key=lambda t:(len(t),sorted(t))):
            delta={term:1}
            for old,value in polynomial.items():delta[old|term]=delta.get(old|term,0)-2*value
            for key,value in delta.items():polynomial[key]=(polynomial.get(key,0)+value)%8
            polynomial={key:value for key,value in polynomial.items() if value}
            if len(polynomial)>self.MAX_TERMS:raise CleanupUnestablished("phase proof term allowance exceeded")
        for term,value in polynomial.items():self.phase[term]=(self.phase.get(term,0)+coefficient*value)%8
        self.phase={term:value for term,value in self.phase.items() if value}

    def gate(self,op,wires,controls):
        own=op.own_controls(len(wires))
        enabled=self.predicate(tuple(dict.fromkeys(controls+wires[:own])))
        match op:
            case CleanupGate.X|CleanupGate.CX|CleanupGate.CCX|CleanupGate.MCX:
                self.values[wires[-1]]=self.value(wires[-1])^enabled
            case CleanupGate.SWAP:
                a,b=wires;change=self.product(self.value(a)^self.value(b),enabled)
                self.values[a]=self.value(a)^change;self.values[b]=self.value(b)^change
            case CleanupGate.S|CleanupGate.SDG|CleanupGate.T|CleanupGate.TDG|CleanupGate.CZ:
                predicate=self.product(enabled,self.predicate(wires))
                self.add_phase(predicate,{CleanupGate.S:2,CleanupGate.SDG:-2,CleanupGate.T:1,CleanupGate.TDG:-1,CleanupGate.CZ:4}[op])
            case _:raise CleanupUnestablished(f"composed proof for {op.value} is unavailable")

    def execute(self,row):
        if row.kind==CleanupKind.OPAQUE:raise CleanupUnestablished(f"composed proof for source point {row.meta['point']} is unavailable")
        if row.kind==CleanupKind.ACQUIRE:
            for bit in bits([row.bundle]):
                entry=(f"borrow:{id(row)}:{bit[0]}",bit[1],bit[2])
                value=frozenset([frozenset([entry])]) if row.bundle.state=="borrowed" else frozenset()
                self.values[bit]=value;self.entries[bit]=value
        elif row.kind==CleanupKind.RELEASE:
            for bit in bits([row.bundle]):
                self.clean &= self.value(bit)==self.entries[bit]
                del self.values[bit]
        else:
            for op,wires,controls in row.gates:self.gate(op,wires,controls)


class TerminalCleanups:
    """K81 terminal owners, §6.2 replay bindings, and composed K80 proof.

    Transparent primitive constructors are proved symbolically. Opaque calls,
    cells and control-flow constructors retain their existing reverse path;
    requesting an unavailable proof reports unestablished mechanics explicitly.
    No semantic equality substitutes for source occurrence/version matching.
    """
    MAX_PROOF_WIRES=256
    MAX_PROOF_ROWS=4096

    def __init__(self,source,nodes,env,controls):
        self.source=source;self.nodes=nodes;self.env=env
        self.plans=[]
        # Bound symbolic proof work before expanding any storage-sized bundle.
        # Reverse and the estimator's existing storage summaries remain valid.
        width=sum(b.width for value in env.values() for b in ([value] if isinstance(value,Bundle) else value if isinstance(value,(list,tuple)) else []) if isinstance(b,Bundle))
        if width+len(controls)>self.MAX_PROOF_WIRES or len(nodes)>self.MAX_PROOF_ROWS:
            self.rows=[];self.versions=None;return
        self.rows=[self.decode(node,env,controls) for node in nodes]
        self.versions=CleanupVersions(self.rows)

    @property
    def catalog(self):return self.source.catalog

    def decode(self,node,env,controls,meta=None):
        marked=self.catalog.source_metadata.get(id(node))
        meta=marked[1] if marked is not None else meta
        if meta is None:return CleanupRow(node,{"point":"captured lifetime history"},CleanupKind.OPAQUE)
        if "under" in node and len(node["body"])==1:
            joined=tuple(sorted(set(controls+bits(wire(node["under"],env)))))
            row=self.decode(node["body"][0],env,joined,meta);row.node=node;return row
        if "splice" in node:
            captured=env[node["splice"]]
            if captured.cleanup and len(captured.body)==1 and "relinquish" in captured.body[0]:
                bundle=captured.env[captured.body[0]["relinquish"]]
                return CleanupRow(node,meta,CleanupKind.RELEASE,bundle=bundle,capture=captured)
            return CleanupRow(node,meta,CleanupKind.OPAQUE)
        for key,kind in [("acquire",CleanupKind.ACQUIRE),("relinquish",CleanupKind.RELEASE)]:
            if key in node:return CleanupRow(node,meta,kind,bundle=env[node[key]])
        if "gate" in node and not node.get("params"):
            wires=bits(wire(node["wires"],env))
            op=CleanupGate(node["gate"])
            return CleanupRow(node,meta,CleanupKind.GATE,(op.bind(wires,controls),))
        if node.get("invoke") in ["bind.qxor","bind.qexch"]:
            if meta["kind"] in ["qcopy","qload"]:return CleanupRow(node,meta,CleanupKind.OPAQUE)
            _,a,b=node["args"];left,right=bits(wire(a,env)),bits(wire(b,env))
            op=CleanupGate.CX if node["invoke"]=="bind.qxor" else CleanupGate.SWAP
            gates=tuple(op.bind((a,b),controls) for a,b in zip(left,right))
            return CleanupRow(node,meta,CleanupKind.GATE,gates)
        return CleanupRow(node,meta,CleanupKind.OPAQUE)

    def owner(self,index,claimed):
        row=self.rows[index];targets=set(bits([row.bundle]));owned=[]
        if any(self.versions.entry_before[index][bit] is None or self.versions.before[index][bit]!=self.versions.entry_before[index][bit] for bit in targets):return []
        for previous in range(index-1,-1,-1):
            candidate=self.rows[previous]
            if candidate.kind==CleanupKind.OPAQUE:break
            if candidate.kind==CleanupKind.RELEASE:
                if targets.intersection(bits([candidate.bundle])):break
                continue
            if candidate.kind==CleanupKind.ACQUIRE and targets.intersection(bits([candidate.bundle])):break
            _,writes=candidate.access()
            if not writes.intersection(targets):continue
            if previous not in self.versions.pairs or previous in claimed:break
            owned.append(previous);targets.update(writes)
        return sorted(owned)

    def choice(self,plan):
        previous=self.catalog.source_context;self.catalog.source_context=plan["meta"]
        try:return (self.catalog.ledger.schedule.pick("cleanup",**self.catalog.leaf_address(carrier=True)) or {"realisation":"reverse"})["realisation"]
        finally:self.catalog.source_context=previous

    def partition(self):
        claimed=set()
        for index,row in enumerate(self.rows):
            if row.kind!=CleanupKind.RELEASE or row.capture is None:continue
            owned=self.owner(index,claimed);claimed.update(owned)
            computes=sorted(self.versions.pairs[i] for i in owned)
            plan={"release":index,"owned":owned,"computes":computes,"meta":row.meta}
            row.capture.owned_points=tuple(self.rows[i].meta["point"] for i in owned+[index])
            # Empty clean lifetimes also have a K65 carrier. A missing match
            # for a nonempty lifetime is proof unavailability, not ill-formedness.
            plan["matched"]=bool(owned) or all(self.versions.entry_before[index][bit] is not None and self.versions.before[index][bit]==self.versions.entry_before[index][bit] for bit in bits([row.bundle]))
            row.capture.recompute=Captured([],{},(),builder=self.replacement(plan))
            try:plan["material"]=self.materialize(plan)
            except CleanupUnestablished as error:plan["material"]=error
            self.plans.append(plan)
            for inverse in owned:self.nodes[inverse]=self.retained_inverse(plan,inverse)
        return self.nodes

    def retained_inverse(self,plan,index):
        row=self.rows[index]
        def expand(joined,inverse,env):
            if self.choice(plan)=="recompute":return Profile()
            return self.catalog.body([row.node],self.env,joined,inverse)
        name=f"$terminal_inverse:{index}"
        self.env[name]=Captured([],{},(),builder=expand)
        wrapper={"splice":name};self.catalog.source_metadata[id(wrapper)]=(wrapper,row.meta)
        return wrapper

    def replay_gates(self,plan,mapping):
        result=[]
        for index in plan["computes"]:
            for op,wires,controls in self.rows[index].gates:
                result.append((op,tuple(mapping.get(bit,bit) for bit in wires),tuple(mapping.get(bit,bit) for bit in controls)))
        return result

    def target_bits(self,plan):
        targets=set().union(*(self.rows[i].access()[1] for i in plan["computes"])) if plan["computes"] else set(bits([self.rows[plan["release"]].bundle]))
        for row in self.rows:
            if row.kind==CleanupKind.ACQUIRE and targets.intersection(bits([row.bundle])):targets.update(bits([row.bundle]))
        return targets

    def replay_window(self,plan,selected):
        if not plan["matched"]:raise CleanupUnestablished("exact computing occurrences for the released lifetime are unestablished")
        targets=self.target_bits(plan);erased={i for p in selected for i in p["owned"]}
        labels=[i for i in range(plan["release"]) if i not in erased]
        candidate=CleanupVersions([self.rows[i] for i in labels],labels)
        for computing in plan["computes"]:
            row=self.rows[computing];reads,_=row.access();external=reads-targets
            protected=external|targets
            for index in range(computing+1,plan["release"]):
                changed=self.rows[index].access()[1]&external
                if not changed:continue
                paired=self.versions.pairs.get(index)
                if paired is not None and paired>computing:continue
                undo=next((j for j,i in self.versions.pairs.items() if i==index and j<plan["release"]),None)
                if undo is None:self.refuse(plan,index,"captured replay input version is not restored")
                for middle in range(index+1,undo):
                    if self.rows[middle].access()[1]&protected:self.refuse(plan,middle,"input undo interval changes a protected basis value")
            for bit in external:
                expected=self.versions.before[computing][bit]
                if candidate.current[bit]!=expected:
                    self.refuse(plan,plan["release"],"captured replay input version is unavailable")
            for index in range(computing+1,plan["release"]):
                event=self.rows[index]
                reads,writes=event.access()
                if event.kind==CleanupKind.OPAQUE:raise CleanupUnestablished(f"window proof at {event.meta['point']} is unavailable")
                if event.kind==CleanupKind.GATE and not event.permutation() and writes&protected:
                    self.refuse(plan,index,"non-permutation basis change closes the cleanup window")

    def refuse(self,plan,index,reason):
        raise ContractError(f"recompute at {plan['meta']['point']} refused: {reason}; conflicting source point {self.rows[index].meta['point']}")

    def composed(self,selected):
        source,candidate=CleanupSemantics(),CleanupSemantics();conflict=None
        erased={i for plan in selected for i in plan["owned"]}
        releases={plan["release"]:plan for plan in selected}
        for index,row in enumerate(self.rows):
            source.execute(row)
            if index in erased:continue
            if index in releases:
                plan=releases[index];targets=self.target_bits(plan)
                mapping={bit:(f"proof:{index}:{bit[0]}",bit[1],bit[2]) for bit in targets}
                for bit in mapping.values():candidate.values[bit]=frozenset()
                gates=self.replay_gates(plan,mapping)
                for gate in gates:candidate.gate(*gate)
                for bit,fresh in mapping.items():candidate.gate(CleanupGate.CX,(fresh,bit),())
                for gate in reversed(gates):candidate.gate(*gate)
                for fresh in mapping.values():
                    candidate.clean &= not candidate.value(fresh);del candidate.values[fresh]
            candidate.execute(row)
            _,writes=row.access()
            if conflict is None and (source.phase!=candidate.phase or any(source.value(bit)!=candidate.value(bit) for bit in writes)):
                conflict=index
        if not source.clean:raise CleanupUnestablished("source clean-release proof is unestablished")
        if not candidate.clean or source.values!=candidate.values or source.phase!=candidate.phase:
            self.refuse(selected[0],conflict if conflict is not None else selected[0]["release"],"composed state/phase equality or clean release fails")

    def replacement(self,plan):
        def expand(joined,inverse,env):
            try:
                selected=[p for p in self.plans if self.choice(p)=="recompute"]
                for chosen in selected:self.replay_window(chosen,selected)
                self.composed(selected)
                material=plan["material"]
                if isinstance(material,CleanupUnestablished):raise material
                nodes,local=material
            except CleanupUnestablished as error:
                raise ContractError(f"recompute at {plan['meta']['point']} pending/unestablished: {error}") from error
            return self.catalog.body(nodes,local,joined,inverse)
        return expand

    def materialize(self,plan):
        targets=self.target_bits(plan);local={};mapping={};prefix=[];suffix=[]
        for index,row in enumerate(self.rows):
            if row.kind!=CleanupKind.ACQUIRE or not targets.intersection(bits([row.bundle])):continue
            fresh=Bundle(f"recompute:{row.bundle.identity}:{plan['meta']['point']}",row.bundle.width,row.bundle.cls)
            name=f"$terminal_fresh:{index}";local[name]=fresh
            prefix.append({"acquire":name});suffix.insert(0,{"relinquish":name})
            mapping.update(zip(bits([row.bundle]),bits([fresh])))
        if not targets<=mapping.keys():raise CleanupUnestablished("joint replay outputs require locally allocated target bundles")
        gates=[]
        for op,wires,controls in self.replay_gates(plan,mapping):
            node={"gate":op.value,"wires":[Bundle(identity,1,cls,offset) for identity,offset,cls in wires]}
            if controls:node={"under":[Bundle(identity,1,cls,offset) for identity,offset,cls in controls],"body":[node]}
            gates.append(node)
        copies=[{"gate":CleanupGate.CX.value,"wires":[Bundle(fresh[0],1,fresh[2],fresh[1]),Bundle(bit[0],1,bit[2],bit[1])]} for bit,fresh in sorted(mapping.items())]
        released=self.rows[plan["release"]].bundle;local["$terminal_released"]=released
        return [*prefix,*gates,*copies,{"inverse":True,"body":gates},*suffix,{"relinquish":"$terminal_released"}],local


class Source:
    def __init__(self, obj, target, catalog):
        self.obj, self.target, self.catalog = obj, target, catalog
        self.cls = catalog.default_class
        self.serial = 0
        self.calls = []
        self.budgets=[]
        self.invocations=[]
        self.token_budgets={}

    def fresh(self, name, width, cls=None, state="clean"):
        self.serial += 1
        return Bundle(f"source:{self.serial}:{name}", width, cls or ("any" if self.catalog.ledger is not None else self.cls), state=state)

    @staticmethod
    def token_context(env,names):
        identities=env.get(_SOURCE_TOKEN_IDENTITIES)
        if identities is None:return None
        require(all(name in identities for name in names),"K91: source token identity missing from lexical context")
        return tuple(identities[name] for name in names)

    def region(self, name, args, budget, interface=None, controls=(), adjoint=False,raw_inverse=False,token_context=None):
        require(name not in self.calls, "§5.1: recursive region call graph")
        if getattr(self.catalog.ledger,"admission",False) and self.calls and self.obj.functions[name].kind=="oracle":
            # In Q source, every nested oracle token is forwarded from root
            # parameters (possibly through lproc/action parameters). Minting
            # is forbidden in that tier. K55 leaves those budgets unknown at
            # admission even when the request provides concrete token values.
            return Profile()
        previous_exact=self.catalog.require_exact
        self.calls.append(name)
        self.budgets.append(budget)
        try:
            fn = self.obj.functions[name]
            self.catalog.require_exact=previous_exact or fn.kind in ["oracle","perm_action"]
            sig = self.obj.symbol(name)["signature"]
            parsed = resolved_arguments(sig.get("args",sig.get("params",[])), args, self.obj)
            env = dict(interface or {})
            wire_groups = fn.groups[:4] if fn.kind == "oracle" else fn.groups[:3]
            for group in wire_groups:
                for n,ty,role in group:
                    if n not in env: env[n] = self.fresh(n,type_width(ty,self.obj.ptr))
            arg_group = fn.groups[4] if fn.kind == "oracle" else fn.groups[3]
            env.update({n:(raw if ty=="f64" else v) for (n,ty,r),v,raw in zip(arg_group,parsed,args)})
            invocation={"args":args,"budget":budget}
            if token_context is not None:
                names=[n for n,ty,r in arg_group if ty=="token"]
                offset=int(fn.kind=="oracle")
                require(len(token_context)==len(names)+offset,"K91: source token context arity mismatch")
                tuples=([budget] if offset else [])+[env[n] for n in names]
                aliases=validate_token_aliases(canonical_token_aliases(token_context),tuples)
                for identity,value in zip(token_context,tuples):
                    value=tuple(integer(n,0) for n in value)
                    require(self.token_budgets.get(identity,value)==value,"K91: forwarded token identity changed its tuple")
                    self.token_budgets[identity]=value
                env[_SOURCE_TOKEN_IDENTITIES]=MappingProxyType(dict(zip(names,token_context[offset:])))
                invocation["token_aliases"]=aliases
            self.invocations.append({"region":name,"invocation":invocation,"inherited_controls":len(set((b[0],b[1]) for b in controls)),"source_adjoint":adjoint,"raw_inverse":raw_inverse,"path":[{k:v for k,v in edge.items() if k!="entered_invocation"} for edge in self.catalog.call_edges]})
            if self.catalog.ledger is not None and len(self.calls)==1 and not self.catalog.prebound_interfaces:
                for bit in controls:self.catalog.ledger.interface(f"control:{bit[1]}",Bundle(bit[0],1,bit[2],bit[1]))
                names=["in","tgt","fault","mem"] if fn.kind=="oracle" else ["mut","in","mem"]
                for group,role in zip(wire_groups,names):
                    for index,(n,ty,mode) in enumerate(group):
                        self.catalog.ledger.interface(f"{role}:{index}",env[n])
                        if role=="mem":self.catalog.ledger.records[-1]["role"]="mem_"+mode
            if fn.kind in ["action","perm_action"]:
                regions={}
                for n,ty,role in fn.groups[2]:
                    m=re.fullmatch(r"region\[([0-9]+),([0-9]+)\]",ty)
                    regions[n]=(int(m[1]),int(m[2]),env[n])
                nodes=self.action_construction(fn,env,regions,controls,adjoint)
                p=self.expand_region(lambda reverse:self.catalog.body(nodes,env,controls,reverse),raw_inverse,False)
                require(all(v == 0 for v in p.delta.values()),"§5.1: unmatched allocation/release in action")
                return p
            require(fn.kind == "oracle", "root region must be action, oracle, CC or R")
            return self.expand_region(lambda reverse:self.oracle(fn,env,budget,controls,raw_inverse=reverse),raw_inverse,True)
        finally:
            self.catalog.require_exact=previous_exact
            self.calls.pop()
            self.budgets.pop()

    def expand_region(self,expand,raw_inverse,oracle):
        catalog=self.catalog
        def run(reverse):
            active=self.catalog;saved=active.region_raw,active.region_oracle
            active.region_raw,active.region_oracle=reverse,oracle
            try:return expand(reverse)
            finally:active.region_raw,active.region_oracle=saved
        if not raw_inverse or catalog.ledger is None or isinstance(catalog.ledger,OrdinalCounter) or catalog.raw_limits is not None:return run(raw_inverse)
        # A dry traversal counts per-point domains, including nested calls.
        # Only counts/orientations survive; no gate or circuit list is built.
        counter_catalog=Catalog(catalog.text,self.target)
        # Inherited controls can be scratch from the surrounding catalog.
        # A private dry traversal must not reuse those allocation identities.
        counter_catalog.serial=catalog.serial
        counter=OrdinalCounter(counter_catalog,catalog.ledger.schedule,admission=getattr(catalog.ledger,"admission",False));counter_catalog.ledger=counter
        counter_catalog.source_metadata=dict(catalog.source_metadata)
        for field in ["source_context","call_edges","root_step","root_phase"]:setattr(counter_catalog,field,getattr(catalog,field))
        counter_catalog.loop_coordinates=list(catalog.loop_coordinates)
        serial,invocations=self.serial,len(self.invocations)
        try:
            self.catalog=counter_catalog;run(False)
        finally:
            self.catalog=catalog;self.serial=serial;del self.invocations[invocations:]
        previous=catalog.raw_limits,catalog.raw_cursors
        catalog.raw_limits={key:(size,-sign) for key,(size,sign) in counter.domains.items()};catalog.raw_cursors={}
        try:
            result=run(True)
            require(all(catalog.raw_cursors.get(key,0)==size for key,(size,sign) in catalog.raw_limits.items()),"raw inverse omitted part of its forward domain")
            return result
        finally:catalog.raw_limits,catalog.raw_cursors=previous

    def action_construction(self,fn,env,regions,controls=(),adjoint=False):
        """Local-region lifetimes enclose the whole invocation, under calls too."""
        prefix,suffix=[],[]
        for inst in fn.code:
            if inst.op!="qregion":continue
            n,A,W,*image=inst.args;A,W=integer(A,0),integer(W,1)
            require(n not in env,"qregion shadows a source binding")
            env[n]=self.fresh(n,(1<<A)*W);regions[n]=(A,W,env[n])
            before=[{"acquire":n}];after=[{"relinquish":n}]
            if image:
                data=self.obj.sections.get("data",{}).get(image[0].removeprefix("@"))
                require(data is not None and len(data)*4==env[n].width,"qregion image width or binding mismatch")
                env[f"$image:{n}"]=data
                before.append({"image":f"$image:{n}","wires":n})
                after.insert(0,{"inverse":True,"body":[{"image":f"$image:{n}","wires":n}]})
            meta={"symbol":self.obj.symbol(fn.name)["interface_hash"],"point":f"{inst.block}:{inst.ordinal}","depth":0,"kind":"qregion","exact":fn.kind=="perm_action"}
            if self.catalog.ledger is not None:
                for node in before+after:self.catalog.source_metadata[id(node)]=(node,meta)
            prefix+=before;suffix=after+suffix
        pairs=self.oracle_pairs(fn,env,controls,adjoint)
        body=self.action_nodes([i for _,code in fn.blocks.values() for i in code],env,regions,controls,adjoint=adjoint,oracle_pairs=pairs)
        nodes=prefix+body+suffix
        if self.catalog.ledger is not None and not adjoint:
            nodes=TerminalCleanups(self,nodes,env,controls).partition()
        return nodes

    @staticmethod
    def empty_cleanups(fn):
        """K65 empty inverse family; general terminal chains remain separate."""
        if any(i.op not in ["qalloc","qfree"] for i in fn.code):return set()
        live={};points=set()
        for inst in fn.code:
            if inst.op=="qalloc":
                require(len(inst.lhs)==1,"missing allocation result")
                live[inst.lhs[0]]=(inst.block,inst.ordinal)
            else:
                require(len(inst.args)==1,"qfree operand arity")
                previous=live.pop(inst.args[0],None)
                if previous is not None:points.update([previous,(inst.block,inst.ordinal)])
        return points

    def oracle_pairs(self,fn,env,controls,adjoint=False):
        """K81 joint versions for flat permutation/call bodies, before expansion.

        These bodies have no release or intrinsic boundaries. Other source
        families still need the complete release-ended partition pass.
        """
        rows=[]
        if _SOURCE_TOKEN_IDENTITIES not in env:return set()
        for inst in fn.code:
            op,args=inst.op,inst.args;own=[]
            while op in ["adj","ctl"]:
                require(len(args)>=(3 if op=="ctl" else 2),"wrapped region call arity")
                if op=="ctl":own+=bits(wire(args[0],env));op,args=args[1],args[2:]
                else:op,args=args[0],args[1:]
            if op not in ["oracle_call","x","cx","ccx","mcx","swap","qxor","qexch"]:return set()
            rows.append((inst,op,args,tuple(sorted(set(controls+tuple(own))))))
        versions=WireVersions();intervals={}
        parts=[b for group in fn.groups[:3] for n,ty,role in group for b in wire(n,env)]
        parts += [Bundle(identity,1,cls,index) for identity,index,cls in controls]
        for b in parts:intervals.setdefault(b.identity,[]).append((b.offset,b.offset+b.width))
        for identity,spans in intervals.items():
            merged=[]
            for lo,hi in sorted(spans):
                if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
                else:merged.append((lo,hi))
            versions.ranges[identity]=tuple((lo,hi,0,False) for lo,hi in merged)
        history={};pairs=set();serial=0
        for inst,op,a,joined in reversed(rows) if adjoint else rows:
            geometry=lambda ws:tuple((b.identity,b.offset,b.width) for b in ws)
            if op=="oracle_call":
                require(len(a)==7,"oracle_call needs token, inputs, target, fault, memory and argument groups")
                callee=a[0].removeprefix("@");child=self.obj.functions[callee]
                outputs=wire([a[3],a[4]],env)
                reads=wire(list_operand(a[2])+list_operand(a[5]),env)
                actuals=list_operand(a[6]);types=child.groups[4]
                require(len(actuals)==len(types) and all(n in env for n in actuals),"oracle call classical argument arity/binding")
                identities=self.token_context(env,[a[1]]+[n for (name,ty,role),n in zip(types,actuals) if ty=="token"])
                values=[env[n] if ty in ["token","f64"] else str(env[n]) for (name,ty,role),n in zip(types,actuals)]
                binding=(callee,jcs(values),identities)
            else:
                if op in ["qxor","qexch"]:
                    require(len(a)==2,"wire operation arity")
                    if op=="qexch":reads=[];outputs=wire(a,env)
                    else:reads=wire(a[0],env);outputs=wire(a[1],env)
                else:
                    ws=wire([list_operand(n) if n.startswith("(") else n for n in a],env)
                    require(ws and all(b.width>0 for b in ws),"gate has no wire operands")
                    if op=="swap":reads=[];outputs=ws
                    else:
                        outputs=[ws[-1].bit(ws[-1].width-1)]
                        reads=ws[:-1]+([ws[-1].slice(0,ws[-1].width-1)] if ws[-1].width>1 else [])
                binding=()
            reads += [Bundle(identity,1,cls,index) for identity,index,cls in joined]
            key=(op,geometry(outputs),geometry(reads),binding)
            before=versions.capture(outputs);inputs=versions.capture(reads)
            entry=history.get((key,inputs,before))
            if entry is not None:
                versions.restore(entry)
                if op=="oracle_call":pairs.add((inst.block,inst.ordinal))
            else:
                serial+=1;versions.assign(outputs,serial,False)
                history[(key,inputs,versions.capture(outputs))]=before
        return pairs

    def oracle_recompute(self,inst,env,regions,controls,meta,function):
        """Restore XOR-oracle targets with fresh T/F and fresh call spaces."""
        a=inst.args;local=dict(env);names=[];widths=[]
        for label,actual in zip(["target","fault"],a[3:5]):
            width=sum(b.width for b in wire(actual,env));fresh=self.fresh("cleanup_"+label,width)
            name=f"$cleanup_{label}:{self.serial}";local[name]=fresh;names.append(name);widths.append(width)
        actuals=list(a);actuals[3:5]=names;calls=[]
        for occurrence in [0,1]:
            replacement=Instruction("oracle_call",actuals,[],block=inst.block,ordinal=inst.ordinal)
            call=self.action_nodes([replacement],local,regions,controls,function_name=function)
            if self.catalog.ledger is not None:
                for node in call:self.catalog.source_metadata[id(node)]=(node,{**meta,"call":True,"oracle_call":True,"call_index":occurrence})
            calls.append(call)
        helpers=[*({"acquire":n} for n in names),*({"invoke":"bind.qxor","args":[w,n,actual]} for w,n,actual in zip(widths,names,a[3:5])),*({"relinquish":n} for n in reversed(names))]
        if self.catalog.ledger is not None:
            for node in helpers:self.catalog.source_metadata[id(node)]=(node,{**meta,"call":False})
        return Captured([*helpers[:2],*calls[0],*helpers[2:4],*calls[1],*helpers[4:]],local,controls)

    def action(self, nodes, env, regions, controls=(), inverse=False):
        out = Profile()
        # Source adjoints require instruction replacements before expansion.
        # The environment tracks forward allocation names during lowering.
        if inverse:
            forward = self.action_nodes(nodes,dict(env),regions,controls)
            return self.catalog.body(forward,env,controls,True)
        nodes = self.action_nodes(nodes,env,regions,controls)
        return self.catalog.body(nodes,env,controls)

    def oracle(self, fn, env, budget, controls=(),raw_inverse=False):
        require(self.obj.versions["isa"] == "0.9", "0.8 has no published complete expansion library; exact padded cost requires 0.9")
        B = unsigned(budget[0])
        root_env=env
        instances=self.obj.procedure_instances(fn.name)
        by_instance={(record["function"].name,record["key"]):record for record in instances}
        rows=[(record,row) for record in instances for row in record["function"].code]
        for record,row in rows:
            owner=record["function"]
            pseudo_names={n for n,ty,role in (owner.groups[4] if owner.kind=="oracle" else owner.groups[3]) if ty!="token"}
            operands=row.args
            if row.op=="lift.call":operands=[row.args[1]]
            elif row.op in ["lift.oracle_call","lift.oracle_uncall"]:operands=row.args[2:6]
            elif row.op=="lift.perm_call":operands=row.args[1:4]
            reads={name for arg in operands if not arg.startswith(("@","^")) for name in re.findall(NAME,arg)}
            require(not reads & pseudo_names,"EST-SOURCE-01: published ref source binding does not fix classical pseudo-location allocations; see docs/CONTRACT_GAPS.md")
        N = len(rows)
        P = max(1,N.bit_length())
        sig = self.obj.symbol(fn.name)["signature"]
        Fwidth,T = integer(sig["fault"],4),integer(sig["tgt"],1)
        root_args=[n for n,ty,r in fn.groups[4]];root_mem=[n for n,ty,r in fn.groups[3]]
        locations=[];location_state=[]
        def widths_of(scope):return {n:(b.width if isinstance(b,Bundle) else sum(w.width for w in b)) for n,b in scope.items() if isinstance(b,Bundle) or isinstance(b,list) and b and all(isinstance(w,Bundle) for w in b)}
        for record in instances:
            owner=record["function"]
            local=env if owner.kind=="oracle" else {**{n:root_env[root_args[i]] for n,i in record["arguments"].items()},**{n:root_env[root_mem[i]] for n,i in record["regions"].items()}}
            if owner.kind!="oracle" and _SOURCE_TOKEN_IDENTITIES in root_env:
                tokens=root_env[_SOURCE_TOKEN_IDENTITIES]
                local[_SOURCE_TOKEN_IDENTITIES]=MappingProxyType({n:tokens[root_args[i]] for n,i in record["arguments"].items() if root_args[i] in tokens})
            declared=owner.regs if owner.kind=="oracle" else owner.groups[0]+owner.groups[1]+owner.regs
            record["env"]=local;record["locations"]=[];record["location_ids"]={}
            for position,(n,ty,role) in enumerate(declared):
                width=type_width(ty,self.obj.ptr)
                label=n if owner.kind=="oracle" else f"{owner.name}{record['key']}:{n}"
                local[n]=self.fresh(label,width)
                descriptor={"id":len(locations),"width":width,"slot":position,"location":local[n]}
                record["location_ids"][n]=descriptor["id"]
                record["locations"].append(descriptor);locations.append(descriptor)
                location_state.append((label,local[n]))
        location_formal=next(f for f in self.catalog.recipes["lift.ret"]["parameters"] if f["name"]=="Globals")
        global_records=self.catalog.bind([location_formal],[locations],{},())[0]["Globals"]
        for record in instances:
            record["locations"]=self.catalog.bind([location_formal],[record["locations"]],{},())[0]["Globals"]
        slot_widths = []
        layout=self.obj.sections.get("layout")
        require(len(instances)==1 or layout is not None,"§7.2: procedures require layout state")
        Sc=integer(layout["S_cells"],0)+1 if layout is not None else 1
        Dc=max(1,(unsigned(budget[3])+1).bit_length())
        Did=max(1,(max(1,len(locations))-1).bit_length())
        for record,row in rows:
            widths=widths_of(record["env"])
            ws = [widths[n] for n in row.lhs]
            if row.op=="lift.alloc":
                require(layout is not None,"lift.alloc requires a layout")
                ws=[self.obj.ptr,2*self.obj.ptr+2,integer(layout["H"],0)+2,integer(layout["A_tab"],0)+1]
            elif row.op=="lift.call":ws=[widths[n] for n in list_operand(row.args[1])]+[Sc,Sc,Dc]
            elif row.op=="lift.ret":ws=[widths[row.args[0]],Sc,Dc]
            for j,w in enumerate(ws):
                if j == len(slot_widths): slot_widths.append(w)
                else: slot_widths[j] = max(slot_widths[j],w)
        if B and any(row.op=="lift.ret" for record,row in rows):
            require(max(location["width"] for location in locations)<=slot_widths[0],"EST-SOURCE-03: published lift.ret scans a location wider than its delivery history slot; see docs/CONTRACT_GAPS.md")
        Q = 2*P + sum(slot_widths) + 1
        pc,nextpc = self.fresh("pc",P), self.fresh("pc_prime",P)
        faulted,code,result = self.fresh("faulted",1),self.fresh("code",Fwidth),self.fresh("result_val",T)
        frame = self.fresh("frame",Q)
        state=self.oracle_state(fn,env,budget,P,Q,pc,nextpc,faulted,code,result,location_state)
        state_wires={record["name"]:record["storage"] for record in state}
        flag = {"range":"frame","from":P+sum(slot_widths),"to":P+sum(slot_widths)+1}
        successor = {"range":"frame","from":Q-P,"to":Q}
        row_templates,next_templates=[],[]
        template_formal=[{"name":"frame","type":"wire","width":Q}]
        def invoke(name, actuals): return {"invoke":name,"args":actuals}
        def lit(value): return invoke("successor.literal",[P,value,"next"])
        def displacement(position,width):
            start=P+sum(slot_widths[:position])
            return {"range":"frame","from":start,"to":start+width}
        for index,(instance,row) in enumerate(rows):
            owner=instance["function"];env=instance["env"];labels=instance["labels"];widths=widths_of(env)
            op = re.sub(r"\.i[1-9][0-9]*$","",row.op)
            a = row.args
            body=[]
            meta={"symbol":self.obj.symbol(owner.name)["interface_hash"],"point":f"{row.block}:{row.ordinal}","instance":list(instance["key"]),"depth":0,"kind":row.op,"exact":True}
            written=row.lhs
            if written:
                require(len(written)==1 or op=="lift.parmov","unsupported multi-result lifted row")
                w=written[0];width=widths[w]
                slot={"range":"frame","from":P,"to":P+width}
            if op in ["lift.const","lift.label","lift.addr"]:
                if op=="lift.addr":
                    layout=self.obj.sections.get("layout")
                    require(layout is not None and width==self.obj.ptr,"lift.addr needs layout and pointer-width destination")
                    name=a[0].removeprefix("@")
                    entry=layout["globals"].get(name,layout["interface_regions"].get(owner.name,{}).get(name))
                    require(entry is not None,"lift.addr names no global or own interface region")
                    value=integer(entry["base"],0)
                else:
                    value=int(a[0]) if op=="lift.const" else labels[a[0].removeprefix("^")]
                require(value.bit_length()<=width if value>=0 else op=="lift.const" and (-value-1).bit_length()<width,"lifted literal out of range")
                if value<0 and self.catalog.ledger is None:
                    # The canonical unsigned word is 2^width+value. Its set
                    # bits number width-popcount(-value-1), without building
                    # that potentially enormous integer or its gate sequence.
                    def signed_literal(joined,inverse,call_env,n=width,zero_bits=(-value-1).bit_count(),target=env[w],temporary=slot):
                        scratch=wire(temporary,call_env)
                        literal=self.catalog.gate_event("x",[scratch[0].bit(0)],joined).repeat(n-zero_bits)
                        exchange=self.catalog.recipe("bind.qexch",[n,temporary,target],call_env,joined,inverse)
                        return exchange.then(literal) if inverse else literal.then(exchange)
                    capture=f"$constant:{self.serial}";self.serial+=1
                    env[capture]=Captured([],{},controls,builder=signed_literal)
                    body=[{"splice":capture}]
                else:
                    if value<0:value%=1<<width
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
            elif op=="lift.alloc":
                require(width==self.obj.ptr,"lift.alloc destination must be ptr width")
                require(not re.fullmatch(r"0|[1-9][0-9]*",a[0]),"EST-SOURCE-02: published lift.alloc has no physical binding for a literal length; see docs/CONTRACT_GAPS.md")
                nwidth=widths[a[0]];used_width=integer(layout["H"],0)+2;top_width=integer(layout["A_tab"],0)+1
                extended=max(nwidth,used_width)+1
                displacements=[];cursor=P
                for j,slot_width in enumerate([self.obj.ptr,2*self.obj.ptr+2,used_width,top_width]):
                    displacements.append({"range":"frame","from":cursor,"to":cursor+slot_width});cursor+=slot_widths[j]
                body=[invoke(op,[self.obj.ptr,nwidth,used_width,top_width,extended,min(used_width,self.obj.ptr),min(nwidth,self.obj.ptr),1<<integer(layout["A_tab"],0),integer(layout["heap_base"],0),unsigned(budget[1]),Fwidth,a[0],state_wires["heap_used"],state_wires["atop"],state_wires["alloctab"],w,*displacements,flag,faulted,code])]
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
            elif op=="qjumpr":
                require(widths[a[0]]>=P,"qjumpr width cannot represent the canonical index space")
                require(not B or widths[a[0]]==P,"EST-SOURCE-04: published qjumpr binds its address and successor to one width; ISA permits distinct address widths; see docs/CONTRACT_GAPS.md")
                body=[invoke(op,[P,Fwidth,instance["first"],instance["first"]+len(owner.code),a[0],successor,flag,faulted,code])]
            elif op=="lift.call":
                callee=by_instance[instance["calls"][id(row)]]
                formals=callee["function"].groups[0];actuals=list_operand(a[1]);m=len(actuals)
                captures=[{"position":i,"width":widths[value],"source":env[value],"parameter":callee["env"][name],"capture":displacement(i,widths[value])} for i,((name,ty,role),value) in enumerate(zip(formals,actuals))]
                record_size=3+len(callee["locations"])
                stack=state_wires["stack"];K=stack.width//(1<<integer(layout["S_cells"],0))
                body=[invoke(op,[Dc,Sc,max(Sc,record_size.bit_length())+1,record_size,1<<integer(layout["S_cells"],0),K,P,Did,Fwidth,unsigned(budget[3]),unsigned(budget[2]),index+1,instance["location_ids"][w],state_wires["depth"],state_wires["sp"],state_wires["fp"],stack,displacement(m,Sc),displacement(m+1,Sc),displacement(m+2,Dc),flag,faulted,code,callee["locations"],captures])]
            elif op=="lift.ret":
                stack=state_wires["stack"];K=stack.width//(1<<integer(layout["S_cells"],0))
                body=[invoke(op,[Dc,Sc,1<<integer(layout["S_cells"],0),K,P,Did,Fwidth,slot_widths[0],widths[a[0]],state_wires["depth"],state_wires["fp"],stack,displacement(1,Sc),displacement(2,Dc),flag,faulted,code,a[0],displacement(0,slot_widths[0]),successor,instance["locations"],global_records])]
            elif op=="lift.free" or op=="lift.boundscheck" and not re.fullmatch(r"0|[1-9][0-9]*",a[1]):
                require(layout is not None,"allocator-table row requires layout")
                require(widths[a[0]]==self.obj.ptr,"allocator-table pointer width mismatch")
                count=1<<integer(layout["A_tab"],0);entry_width=2*self.obj.ptr+2
                table=state_wires["alloctab"]
                fields=[RecordField(table.identity,count*w,table.cls,table.offset+offset,table.state,w,entry_width) for offset,w in [(0,self.obj.ptr),(self.obj.ptr,self.obj.ptr),(2*self.obj.ptr,1),(2*self.obj.ptr+1,1)]]
                # The free recipe never reads its legacy n/L/E formals.
                # Alias its unused n to the existing pointer, adding no wire.
                length_width,length=(self.obj.ptr,a[0]) if op=="lift.free" else (widths[a[1]],a[1])
                body=[invoke(op,[self.obj.ptr,length_width,max(self.obj.ptr,length_width)+1,count,integer(layout["A_tab"],0)+1,Fwidth,a[0],length,*fields,state_wires["atop"],flag,faulted,code])]
            elif op in ["lift.oracle_call","lift.oracle_uncall","lift.perm_call"]:
                if op=="lift.perm_call":
                    require(self.obj.functions[a[0].removeprefix("@")].kind=="perm_action","lift.perm_call requires permutation action")
                regions={}
                for n,ty,role in (owner.groups[3] if owner.kind=="oracle" else owner.groups[4]):
                    shape=re.fullmatch(r"region\[([0-9]+),([0-9]+)\]",ty)
                    regions[n]=(int(shape[1]),int(shape[2]),env[n])
                adapter=Instruction("action_call" if op=="lift.perm_call" else "oracle_call",a,[],block=row.block,ordinal=row.ordinal)
                body=self.action_nodes([adapter],env,regions,controls,function_name=owner.name)
                if self.catalog.ledger is not None:
                    for node in body:
                        prior=self.catalog.source_metadata[id(node)][1]
                        self.catalog.source_metadata[id(node)]=(node,{**meta,**{k:prior[k] for k in ["call","oracle_call","call_index"] if k in prior}})
                if op=="lift.oracle_uncall":
                    # K65/K81: this intrinsic alone owns its cleanup carrier.
                    # Reverse is the adjoint of its exact computing call.
                    reverse=[{"inverse":True,"body":body}]
                    local=dict(env)
                    target_width=sum(b.width for b in wire(a[3],env))
                    fault_width=sum(b.width for b in wire(a[4],env))
                    fresh_target=self.fresh("cleanup_target",target_width)
                    target_name=f"$cleanup_target:{self.serial}"
                    fresh_fault=self.fresh("cleanup_fault",fault_width)
                    fault_name=f"$cleanup_fault:{self.serial}"
                    local[target_name]=fresh_target;local[fault_name]=fresh_fault
                    actuals=list(a);actuals[3:5]=[target_name,fault_name]
                    calls=[]
                    for occurrence in [0,1]:
                        replacement=Instruction("oracle_call",actuals,[],block=row.block,ordinal=row.ordinal)
                        call=self.action_nodes([replacement],local,regions,controls,function_name=owner.name)
                        if self.catalog.ledger is not None:
                            for node in call:self.catalog.source_metadata[id(node)]=(node,{**meta,"call":True,"oracle_call":True,"call_index":occurrence})
                        calls.append(call)
                    helpers=[{"acquire":target_name},{"acquire":fault_name},invoke("bind.qxor",[target_width,target_name,a[3]]),invoke("bind.qxor",[fault_width,fault_name,a[4]]),{"relinquish":fault_name},{"relinquish":target_name}]
                    recompute=[*helpers[:2],*calls[0],*helpers[2:4],{"inverse":True,"body":calls[1]},*helpers[4:]]
                    if self.catalog.ledger is not None:
                        for node in helpers:self.catalog.source_metadata[id(node)]=(node,meta)
                    capture=f"$lift_cleanup:{self.serial}";self.serial+=1
                    env[capture]=Captured(reverse,dict(env),controls,cleanup=True,recompute=Captured(recompute,local,controls))
                    body=[{"splice":capture}]
            elif op in ["lift.load","lift.store"] or op=="lift.boundscheck" and re.fullmatch(r"0|[1-9][0-9]*",a[1]):
                raise ContractError("EST-SOURCE-02: published ref source binding does not fix implicit/literal length wires; see docs/CONTRACT_GAPS.md")
            else: raise ContractError(f"oracle source binding not implemented: {row.op}; no row omitted")
            if op in ["lift.retval","fault"]: nxt=[lit(N)]
            elif op=="qjump": nxt=[lit(labels[a[0][1:]])]
            elif op=="qbranch": nxt=[invoke("bind.qxor",[P,successor,"next"])]
            elif op in ["qjumpr","lift.ret"]: nxt=[invoke("successor.dynamic",[P,N,flag,successor,"next"])]
            elif op=="lift.call":nxt=[invoke("successor.flagged",[P,callee["first"],N,flag,"next"])]
            elif op in ["lift.faultif","lift.udiv","lift.urem","lift.sdiv","lift.srem","lift.alloc","lift.free","lift.boundscheck"]: nxt=[invoke("successor.flagged",[P,index+1,N,flag,"next"])]
            else: nxt=[lit(index+1)]
            row_templates.append(({"parameters":template_formal,"body":body},dict(env),controls))
            next_templates.append(({"parameters":template_formal+[{"name":"next","type":"wire","width":P}],"body":nxt},dict(env),controls))
            if self.catalog.ledger is not None:
                for node in body+nxt:
                    prior=self.catalog.source_metadata.get(id(node),(None,{}))[1]
                    context={**meta,**{k:prior[k] for k in ["call","oracle_call","call_index"] if k in prior}} if prior.get("call") else meta
                    self.catalog.source_metadata[id(node)]=(node,context)
        env=root_env;env["$source_rows"]=row_templates;env["$source_next"]=next_templates
        if self.catalog.ledger is not None:
            return self.oracle_stream(fn,env,budget,controls,P,N,Q,Fwidth,T,pc,nextpc,faulted,code,result,"$source_rows","$source_next",state,raw_inverse)
        step=self.catalog.recipe("step",[P,N,Q,pc,nextpc,frame,"$source_rows","$source_next"],env,controls) if B else Profile()
        require(all(v==0 for v in step.delta.values()),"unbalanced step workspace")
        target=env[fn.groups[1][0][0]];fault=env[fn.groups[2][0][0]]
        # Exactly the published commit segment, with the source-bound state.
        commit_nodes=self.catalog.recipes["oracle.construct"]["body"][2:-2]
        commit_env=dict(env,P=P,N=N,F=Fwidth,T=T,pc=pc,next=nextpc,faulted=faulted,code=code,result=result,tgt=target,fr=fault)
        commit=self.catalog.body(commit_nodes,commit_env,controls)
        self.last_state=state
        prefix,suffix=Profile(),Profile()
        for record in state:
            b=record["storage"]
            init=record["initial"]
            prep=self.catalog.recipe("value.literal",[b.width,init,b],{},controls) if init else Profile()
            for byte_base,image in record["images"]:
                chunk=b.slice(byte_base*8,(byte_base+len(image)//2)*8)
                prep=prep.then(self.catalog.body([{"image":"I","wires":"cells"}],{"I":image,"cells":chunk}))
            prefix=prefix.then(space_profile(b.cls,"clean",b.width)).then(prep)
            suffix=prep.then(space_profile(b.cls,"clean",-b.width)).then(suffix)
        work=step.repeat(B).then(commit).then(step.repeat(B))
        return prefix.then(work).then(suffix)

    def oracle_stream(self,fn,env,budget,controls,P,N,Q,Fwidth,T,pc,nextpc,faulted,code,result,rows,next_rows,state,raw_inverse=False):
        """Replay catalog steps against allocation endpoints, preserving K64.

        The analytic path above remains constant work in B. A concrete
        schedule must inspect its selected dynamic leaves; none are retained.
        """
        catalog=self.catalog;ledger=catalog.ledger
        self.last_state=state
        symbol=self.obj.symbol(fn.name)["interface_hash"]
        support={pt:{"symbol":symbol,"point":pt,"depth":0,"kind":"support","exact":True} for pt in ["$construct","$step","$commit","$release"]}
        saved=catalog.source_context,catalog.root_step,catalog.root_phase,catalog.reverse_limits
        saved_edges=catalog.call_edges
        nested=bool(saved_edges and "entered_invocation" in saved_edges[-1])
        def step_context(step=None,phase=None):
            if nested:catalog.call_edges=saved_edges[:-1]+({**saved_edges[-1],"entered_invocation":metadata_counts([step,phase])},)
            else:catalog.root_step,catalog.root_phase=step,phase
        out=Profile();frames=[]
        try:
            catalog.reverse_limits=None
            catalog.source_context=support["$release" if raw_inverse else "$construct"]
            for record in state:
                b=record["storage"]
                out=out.then(catalog.space_event(b,True))
                if record["name"].startswith("frame:"):
                    frames.append(b);ledger.records[-1]["category"]="history"
                if record["initial"]:out=out.then(catalog.recipe("value.literal",[b.width,record["initial"],b],{},controls))
                for byte_base,image in record["images"]:
                    chunk=b.slice(byte_base*8,(byte_base+len(image)//2)*8)
                    out=out.then(catalog.body([{"image":"I","wires":"cells"}],{"I":image,"cells":chunk}))
            step_args=[P,N,Q,pc,nextpc,None,rows,next_rows]
            for index,frame in enumerate(frames,1):
                catalog.source_context=support["$step"];step_context(index,"rev" if raw_inverse else "fwd")
                step_args[5]=frame
                out=out.then(catalog.recipe("step",step_args,env,controls))
            # All steps have the same forward point domains. Retain counts,
            # not gates, to address inverse leaves by their forward ordinal.
            limits={key:value[1] for key,value in catalog.source_ordinals.items()}
            catalog.source_context=support["$commit"];step_context()
            commit_env=dict(env,P=P,N=N,F=Fwidth,T=T,pc=pc,next=nextpc,faulted=faulted,code=code,result=result,tgt=env[fn.groups[1][0][0]],fr=env[fn.groups[2][0][0]])
            out=out.then(catalog.body(catalog.recipes["oracle.construct"]["body"][2:-2],commit_env,controls,inverse=raw_inverse))
            for index in range(len(frames),0,-1):
                catalog.source_context=support["$step"];step_context(index,"fwd" if raw_inverse else "rev");catalog.reverse_limits=limits
                step_args[5]=frames[index-1]
                out=out.then(catalog.recipe("step",step_args,env,controls,inverse=True))
            catalog.reverse_limits=None
            catalog.source_context=support["$construct" if raw_inverse else "$release"];step_context()
            for record in reversed(state):
                b=record["storage"]
                for byte_base,image in reversed(record["images"]):
                    chunk=b.slice(byte_base*8,(byte_base+len(image)//2)*8)
                    out=out.then(catalog.body([{"image":"I","wires":"cells"}],{"I":image,"cells":chunk},inverse=True))
                if record["initial"]:out=out.then(catalog.recipe("value.literal",[b.width,record["initial"],b],{},controls,inverse=True))
                out=out.then(catalog.space_event(b,False))
            return out
        finally:
            catalog.source_context,catalog.root_step,catalog.root_phase,catalog.reverse_limits=saved
            catalog.call_edges=saved_edges

    def oracle_state(self,fn,env,budget,P,Q,pc,nextpc,faulted,code,result,location_state=None):
        """K25 source state, stored as compact descriptors rather than wires.

        The B frames share one cost coordinate; it represents B distinct equal
        lifetimes, not a shared frame identity for a scheduled certificate.
        """
        records=[]
        if location_state is None:location_state=[(n,env[n]) for n,ty,r in fn.regs]
        def add(name,b,initial=0,images=()):
            require(initial>=0 and initial.bit_length()<=b.width,"construction initial value outside width")
            records.append({"name":name,"storage":b,"initial":initial,"images":list(images)})
            return b
        for name,b in [("pc",pc),("pc_prime",nextpc),("faulted",faulted),("code",code),("result_val",result)]: add(name,b)
        layout=self.obj.sections.get("layout")
        table=None;packed=0
        if layout is not None:
            require(integer(layout["ptr_width"],1)==self.obj.ptr,"layout pointer width differs from object")
            H,A,S=(integer(layout[k],0) for k in ["H","A_tab","S_cells"])
            require(H<=self.obj.ptr,"layout H exceeds pointer width")
            entries=[]
            mapped=layout["interface_regions"].get(fn.name,{})
            mem_formals={n:ty for n,ty,role in fn.groups[3]}
            require(set(mapped)==set(mem_formals),"layout mapped regions differ from source interface")
            images=[]
            ranges=[(0,integer(layout["null_size"],0),"null")]
            for name,g in layout["globals"].items():
                base,size=integer(g["base"],0),integer(g["size"],0)
                require(g["image"]==name and name in self.obj.sections.get("data",{}),"global image/data name mismatch")
                image=self.obj.sections["data"][name]
                require(len(image)==2*size,"global size differs from data image")
                entries.append((base,size));ranges.append((base,base+size,name))
                images.append((base,image))
            for name,entry in mapped.items():
                shape=re.fullmatch(r"region\[([0-9]+),8\]",mem_formals[name])
                require(shape,"mapped interface regions require W=8")
                base,size=integer(entry["base"],0),1<<int(shape[1])
                entries.append((base,size));ranges.append((base,base+size,name))
            require(len(entries)<=1<<A,"too many allocator pre-entries")
            heap_base,heap_max=integer(layout["heap_base"],0),integer(layout["heap_limit_max"],0)
            ranges.append((heap_base,heap_base+heap_max,"heap"))
            for i,(lo,hi,name) in enumerate(ranges):
                require(0<=lo<=hi<=1<<H,f"layout range outside memory: {name}")
                for a,b,other in ranges[:i]:
                    if lo<hi and a<b: require(hi<=a or lo>=b,f"overlapping layout ranges: {name}/{other}")
            Hc,Ac,Sc,Dc=H+2,A+1,S+1,max(1,(unsigned(budget[3])+1).bit_length())
            for name,width,initial in [("heap_used",Hc,0),("atop",Ac,len(entries)),("sp",Sc,0),("fp",Sc,0),("depth",Dc,0)]: add(name,self.fresh(name,width),initial)
            add("mem",self.fresh("mem",8*(1<<H)),images=sorted(images))
            location_widths=[b.width for n,b in location_state]
            Did=max(1,(max(1,len(location_widths))-1).bit_length())
            cell_width=max(P,Sc,Did,*location_widths)
            add("stack",self.fresh("stack",(1<<S)*cell_width))
            entry_width=2*self.obj.ptr+2
            table=self.fresh("alloctab",(1<<A)*entry_width)
            for i,(base,size) in enumerate(entries):
                packed|=(base+(size<<self.obj.ptr)+(3<<(2*self.obj.ptr)))<<(i*entry_width)
        for n,b in location_state:add(n,b)
        if table is not None: add("alloctab",table,packed)
        B=unsigned(budget[0])
        if self.catalog.ledger is not None:
            for i in range(B):add(f"frame:{i}",self.fresh(f"frame:{i}",Q))
        elif B:add("frames",self.fresh("frames",B*Q))
        return records

    @staticmethod
    def binding_types(env,regions):
        inactive=env.get(_SOURCE_INACTIVE,())
        result={}
        for name,value in env.items():
            if not isinstance(name,str) or name.startswith("$") or name in inactive:continue
            parts=[value] if isinstance(value,Bundle) else value
            if isinstance(parts,(list,tuple)) and parts and all(isinstance(part,Bundle) for part in parts):
                result[name]=("region",*regions[name][:2]) if name in regions else ("wire",sum(part.width for part in parts))
        return result

    def source_loop(self,inst,env,regions,controls,depth,adjoint,n):
        """Finite binding transitions; repeat source templates, never gates.

        Widths/classes come from fixed arguments, literal allocation shapes
        and existing bindings. A state includes physical handles and liveness,
        so a repeated state admits exact composition of the whole cycle.
        """
        def snapshot(values):
            result=dict(values);result[_SOURCE_INACTIVE]=set(values.get(_SOURCE_INACTIVE,()))
            return result
        def state(values):
            inactive=values.get(_SOURCE_INACTIVE,())
            return tuple(sorted((key,b.identity,b.width,b.cls,b.offset,b.state,key in inactive) for key,b in values.items() if isinstance(key,str) and not key.startswith("$") and isinstance(b,Bundle)))
        initial=snapshot(env);current=snapshot(env)
        entry_types=self.binding_types(initial,regions)
        variants=[];states=[initial];seen={};prefix=cycle=0
        if not n:
            # Check the body without changing the zero-visit exit bindings.
            self.action_nodes(inst.body,current,regions,controls,depth+1,adjoint)
            require(self.binding_types(current,regions)==entry_types,"§4.6: qloop entry/exit live names and types must agree")
        while len(variants)<n:
            key=state(current)
            if key in seen:
                prefix=seen[key];cycle=len(variants)-prefix;break
            seen[key]=len(variants)
            body=self.action_nodes(inst.body,current,regions,controls,depth+1,adjoint)
            require(self.binding_types(current,regions)==entry_types,"§4.6: qloop entry/exit live names and types must agree")
            variants.append(Captured(body,snapshot(current),controls))
            states.append(snapshot(current))
        else:prefix=len(variants)
        final=states[prefix+(n-prefix)%cycle] if cycle else states[-1]
        env.clear();env.update(snapshot(final))
        def expand(joined,inverse,call_env):
            catalog=self.catalog;out=Profile()
            reverse=adjoint!=inverse
            if catalog.ledger is not None:
                coordinates=catalog.loop_coordinates
                try:
                    for index in range(n-1,-1,-1) if reverse else range(n):
                        selected=index if index<prefix else prefix+(index-prefix)%cycle
                        variant=variants[selected]
                        # Source-adjoint formation has a new forward loop;
                        # raw inversion retains that loop's forward indices.
                        catalog.loop_coordinates=coordinates+[n-1-index if adjoint else index]
                        out=out.then(catalog.body(variant.body,variant.env,joined,inverse))
                finally:catalog.loop_coordinates=coordinates
                return out
            segments=[(range(prefix),1)]
            if cycle:
                repeats,remainder=divmod(n-prefix,cycle)
                segments.extend([(range(prefix,prefix+cycle),repeats),(range(prefix,prefix+remainder),1)])
            for indices,count in reversed(segments) if reverse else segments:
                if not count:continue
                profile=Profile()
                for index in reversed(indices) if reverse else indices:
                    variant=variants[index]
                    profile=profile.then(catalog.body(variant.body,variant.env,joined,inverse))
                out=out.then(profile.repeat(count))
            return out
        return Captured([],{},controls,builder=expand,loop_plan=(n,prefix,cycle,tuple(variants),adjoint))

    def conditional_loop(self,captured,condition,controls):
        n,prefix,cycle,variants,adjoint=captured.loop_plan
        require(sum(part.width for part in condition)==n,"§4.6: qloop while selector width mismatch")
        body_name=f"$while_visit:{self.serial}";self.serial+=1
        def visit(joined,inverse,call_env):
            iteration=call_env["$iteration" if adjoint else "i"]
            index=n-1-iteration if adjoint else iteration
            selected=index if index<prefix else prefix+(index-prefix)%cycle
            variant=variants[selected]
            return self.catalog.body(variant.body,variant.env,joined,inverse)
        body=Captured([],{},controls,builder=visit)
        def expand(joined,inverse,call_env):
            catalog=self.catalog
            if catalog.ledger is None and catalog.closed_form and not catalog.target.doc.get("topology") and len(condition)==1 and not isinstance(condition[0],RecordField) and not any(identity==condition[0].identity for identity,_,_ in joined):
                flags=self.fresh("while_flags",n,catalog.default_class)
                init=catalog.body([{"gate":"cx","wires":[condition[0].bit(0),flags.bit(0)]}],{},joined) if n else Profile()
                advance=catalog.body([{"gate":"ccx","wires":[flags.bit(0),condition[0].bit(1),flags.bit(1)]}],{},joined) if n>1 else Profile()
                body_controls=tuple(dict.fromkeys(joined+bits([flags.bit(0)]))) if n else joined
                body_profiles={}
                def body_profile(index):
                    if index not in body_profiles:
                        variant=variants[index]
                        body_profiles[index]=catalog.body(variant.body,variant.env,body_controls,inverse)
                    return body_profiles[index]
                def compose(limit,reverse=False,before=False,after=False):
                    segments=[(range(min(prefix,limit)),1)]
                    if limit>prefix:
                        repeats,remainder=divmod(limit-prefix,cycle)
                        segments.extend([(range(prefix,prefix+cycle),repeats),(range(prefix,prefix+remainder),1)])
                    result=Profile()
                    for indices,count in reversed(segments) if reverse else segments:
                        if not count:continue
                        part=Profile()
                        for index in reversed(indices) if reverse else indices:
                            visit=body_profile(index)
                            if before:visit=advance.then(visit)
                            if after:visit=visit.then(advance)
                            part=part.then(visit)
                        result=result.then(part.repeat(count))
                    return result
                result=space_profile(flags.cls,"clean",n).then(init)
                if n:
                    last=n-1 if n-1<prefix else prefix+(n-1-prefix)%cycle
                    if adjoint:
                        result=result.then(advance.repeat(n-1)).then(compose(n,reverse=not inverse)).then(advance.repeat(n-1))
                    elif inverse:
                        result=result.then(advance.repeat(n-1)).then(body_profile(last)).then(compose(n-1,reverse=True,before=True))
                    else:
                        result=result.then(compose(n-1,after=True)).then(body_profile(last)).then(advance.repeat(n-1))
                    result=result.then(init)
                return result.then(space_profile(flags.cls,"clean",-n))
            local={"N":n,"cond":condition,body_name:body}
            if not adjoint:return self.catalog.recipe("qloop.while",[n,condition,body_name],local,joined,inverse)
            recipe=self.catalog.recipes["qloop.while"]["body"]
            nodes=[recipe[0],*recipe[3]["body"],{"for":"$iteration","from":0,"to":n,"body":[{"under":"flags[[\"-\",[\"-\",\"N\",1],\"$iteration\"]]","body":[{"splice":body_name}]}]},recipe[3],recipe[4]]
            return self.catalog.body(nodes,local,joined,inverse)
        return Captured([],{},controls,builder=expand)

    def lower_action_call(self,inst,env,regions,controls,adjoint):
        a=inst.args
        require(len(a)==5,"action_call requires four complete argument groups")
        name=a[0].removeprefix("@")
        require(name in self.obj.functions and name not in self.calls,"unknown/cyclic action call")
        fn=self.obj.functions[name]
        require(fn.kind in ["action","perm_action"],"action_call requires action")
        actual_groups=[list_operand(x) for x in a[1:]]
        require(all(len(g)==len(v) for g,v in zip(fn.groups[:4],actual_groups)),"action call argument arity")
        child={}
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
            child[n]=b
            all_wires+=wire(b,env)
        for i,b in enumerate(all_wires):
            for other in all_wires[:i]: require(b.identity!=other.identity or b.offset+b.width<=other.offset or other.offset+other.width<=b.offset,"overlapping action call arguments")
        caller=self.obj.functions[self.calls[-1]]
        caller_types={n:ty for n,ty,r in (caller.groups[4] if caller.kind=="oracle" else caller.groups[2]+caller.groups[3] if caller.kind=="lproc" else caller.groups[3])}
        for (n,ty,r),actual in zip(fn.groups[3],actual_groups[3]):
            require(caller_types.get(actual)==ty,"action call classical argument type mismatch")
            child[n]=env[actual]
        arguments=[child[n] if ty in ["token","f64"] else str(child[n]) for n,ty,r in fn.groups[3]]
        identities=self.token_context(env,[actual for (n,ty,r),actual in zip(fn.groups[3],actual_groups[3]) if ty=="token"])
        def invoke_action(joined,inverse,call_env,name=name,values=arguments,tuple_=list(self.budgets[-1]),interface=dict(child),source_adjoint=adjoint,identities=identities):
            return self.region(name,values,tuple_,interface,joined,source_adjoint,raw_inverse=inverse,token_context=identities)
        self.serial+=1
        capture=f"$call:{self.serial}"
        env[capture]=Captured([],{},controls,builder=invoke_action)
        return {"splice":capture}

    def lower_oracle_call(self,inst,env,regions,controls,function):
        a=inst.args
        require(len(a)==7,"oracle_call needs token, inputs, target, fault, memory and argument groups")
        callee=a[0].removeprefix("@")
        require(callee in self.obj.functions and self.obj.functions[callee].kind=="oracle","oracle_call requires linked oracle")
        fn=self.obj.functions[callee]
        token=env.get(a[1]);validate_budget(token,self.obj)
        actual_groups=[list_operand(a[2]),[a[3]],[a[4]],list_operand(a[5]),list_operand(a[6])]
        require(all(len(g)==len(v) for g,v in zip(fn.groups,actual_groups)),"oracle call argument arity")
        child={};wires=[]
        for group,actuals in zip(fn.groups[:4],actual_groups[:4]):
            for (n,ty,role),actual in zip(group,actuals):
                ws=wire(actual,env)
                require(sum(b.width for b in ws)==type_width(ty,self.obj.ptr),"oracle call interface width mismatch")
                if ty.startswith("region["):
                    require(actual in regions and ty==f"region[{regions[actual][0]},{regions[actual][1]}]","oracle call memory shape mismatch")
                child[n]=ws;wires+=ws
        for i,b in enumerate(wires):
            for other in wires[:i]:require(b.identity!=other.identity or b.offset+b.width<=other.offset or other.offset+other.width<=b.offset,"overlapping oracle call arguments")
        caller=self.obj.functions[function]
        caller_types={n:ty for n,ty,r in (caller.groups[4] if caller.kind=="oracle" else caller.groups[2]+caller.groups[3] if caller.kind=="lproc" else caller.groups[3])}
        arguments=[]
        for (n,ty,r),actual in zip(fn.groups[4],actual_groups[4]):
            require(caller_types.get(actual)==ty,"oracle call classical argument type mismatch")
            arguments.append(env[actual] if ty in ["token","f64"] else str(env[actual]))
        identities=self.token_context(env,[a[1]]+[actual for (n,ty,r),actual in zip(fn.groups[4],actual_groups[4]) if ty=="token"])
        def invoke_oracle(joined,inverse,call_env,name=callee,values=arguments,tuple_=list(token),interface=dict(child),identities=identities):
            return self.region(name,values,tuple_,interface,joined,raw_inverse=inverse,token_context=identities)
        self.serial+=1;capture=f"$oracle:{self.serial}"
        env[capture]=Captured([],{},controls,builder=invoke_oracle)
        return {"splice":capture}

    def lower_qinplace(self,inst,env,regions,controls,adjoint,function,meta):
        a=inst.args
        require(len(a) in [4,7],"qinplace needs two oracles, token, target and complete optional groups")
        names=[n.removeprefix("@") for n in a[:2]]
        if adjoint:names.reverse()
        require(all(n in self.obj.functions and self.obj.functions[n].kind=="oracle" for n in names),"qinplace requires linked oracle pair")
        signatures=[self.obj.symbol(n)["signature"] for n in names]
        require(signatures[0]==signatures[1],"qinplace pair signature mismatch")
        sig=signatures[0];N=sum(b.width for b in wire(a[3],env));Fwidth=integer(sig["fault"],4)
        require(sig["in"] and integer(sig["in"][0],1)==N==integer(sig["tgt"],1),"qinplace target/first input width mismatch")
        token=env.get(a[2]);validate_budget(token,self.obj)
        ins,mem,args=[list_operand(x) for x in a[4:]] if len(a)==7 else [[],[],[]]
        require([len(ins),len(mem),len(args)]==[len(sig["in"])-1,len(sig["mem"]),len(sig["args"])],"qinplace argument arity")
        extra=[wire(value,env) for value in ins]
        require([sum(b.width for b in ws) for ws in extra]==[integer(w,1) for w in sig["in"][1:]],"qinplace input width mismatch")
        caller_types={n:ty for n,ty,r in self.obj.functions[function].groups[3]}
        values=[]
        for ty,value in zip(sig["args"],args):
            require(caller_types.get(value)==ty,"qinplace classical argument type mismatch")
            values.append(env[value] if ty in ["token","f64"] else str(env[value]))
        memory=[]
        for desc,value in zip(sig["mem"],mem):
            require(value in regions and list(regions[value][:2])==[integer(desc["A"],0),integer(desc["W"],1)],"qinplace memory shape mismatch")
            memory.append(regions[value][2])
        templates=[]
        identities=self.token_context(env,[a[2]]+[actual for ty,actual in zip(sig["args"],args) if ty=="token"])
        for call_index,name_ in enumerate(names):
            fn=self.obj.functions[name_]
            def invoke_pair(joined,inverse,call_env,name=name_,fn=fn,values=list(values),tuple_=list(token),inputs=extra,memories=memory,identities=identities):
                child={fn.groups[0][0][0]:wire("x",call_env),fn.groups[1][0][0]:wire("t",call_env),fn.groups[2][0][0]:wire("f",call_env)}
                child.update({n:ws for (n,ty,role),ws in zip(fn.groups[0][1:],inputs)})
                child.update({n:b for (n,ty,role),b in zip(fn.groups[3],memories)})
                return self.region(name,values,tuple_,child,joined,raw_inverse=inverse,token_context=identities)
            self.serial+=1;capture=f"$qinplace:{self.serial}";env[capture]=Captured([],{},controls,builder=invoke_pair)
            node={"splice":capture}
            if self.catalog.ledger is not None:self.catalog.source_metadata[id(node)]=(node,{**meta,"call":True,"oracle_call":True,"call_index":call_index})
            templates.append([{"parameters":[{"name":"x","type":"wire","width":N},{"name":"t","type":"wire","width":N},{"name":"f","type":"wire","width":Fwidth}],"body":[node]}])
        return {"invoke":"qinplace","args":[N,Fwidth,a[3],*templates,[]]}

    def action_nodes(self, source_nodes, env, regions, controls=(),depth=0,adjoint=False,function_name=None,oracle_pairs=None):
        out,fragments = [],[]
        inactive=env.setdefault(_SOURCE_INACTIVE,set())
        lifetimes=env.setdefault(_SOURCE_LIFETIMES,{})
        predicates = []
        def emit(node,controlled=True):
            if predicates and controlled:
                node = {"under": list(predicates), "body":[node]}
            if self.catalog.ledger is not None:self.catalog.source_metadata[id(node)]=(node,meta)
            out.append(node)
        for inst in source_nodes:
            beginning=len(out)
            op,a = inst.op,inst.args
            function=function_name or self.calls[-1]
            meta={"symbol":self.obj.symbol(function)["interface_hash"],"point":f"{inst.block}:{inst.ordinal}","depth":depth,"kind":op,"call":op in ["action_call","oracle_call"],"oracle_call":op=="oracle_call","exact":self.obj.functions[function].kind=="perm_action"}
            if op in GATES or op == "mcx":
                require(not any(self.obj.functions[n].kind in ["oracle","perm_action"] for n in self.calls) or op in ["x","cx","ccx","mcx","swap"],"§5.3: non-permutation source gate in permutation action")
                params = []
                if op in ["rx","ry","rz"]:
                    theta,*a = a
                    theta=env.get(theta,theta)
                    angle(theta)
                    if adjoint:
                        theta="0x"+format(int(theta[2:],16)^(1<<63),"016x") if isinstance(theta,str) and theta.startswith("0x") else -float(theta)
                    params = [theta]
                a = [list_operand(x) if x.startswith("(") else x for x in a]
                emit({"gate":ADJOINT.get(op,op) if adjoint else op,"wires":a,**({"params":params} if params else {})})
            elif op in ["qalloc","qborrow","qcopy","qload"]:
                require(len(inst.lhs)==1,"missing allocation result")
                name = inst.lhs[0]
                require(name not in env or name in inactive,"allocation shadows a live binding")
                if op in ["qalloc","qborrow"]:
                    cls,n = a
                    n = env.get(n,integer(n,1) if re.fullmatch(r"[0-9]+",n) else None)
                    require(isinstance(n,int) and n>0,"invalid allocation width")
                    cls = self.cls if cls == "any" and self.catalog.ledger is None else cls
                    state = "borrowed" if op == "qborrow" else "clean"
                elif op == "qcopy":
                    n = sum(b.width for b in wire(a[0],env)); cls,state = (self.cls if self.catalog.ledger is None else "any"),"clean"
                else:
                    require(a[0] in regions,"unknown region")
                    A,n,_ = regions[a[0]]; cls,state=(self.cls if self.catalog.ledger is None else "any"),"clean"
                if name in env:
                    b=env[name]
                    require(isinstance(b,Bundle),"allocation replaces a non-wire binding")
                    lifetimes.setdefault((name,b.width,b.cls,b.state),b)
                    if (b.width,b.cls,b.state)!=(n,cls,state):
                        # Earlier source rows retain the lifetime they used.
                        # A consumed name may be produced again with another
                        # shape, without rewriting those earlier operands.
                        prefix=[node for fragment in reversed(fragments) for node in fragment] if adjoint else list(out)
                        if prefix:
                            capture=f"$prior_lifetime:{self.serial}";self.serial+=1
                            env[capture]=Captured(prefix,dict(env),controls)
                            wrapper={"splice":capture}
                            out=[wrapper];fragments=[[wrapper]];beginning=1
                        b=lifetimes.get((name,n,cls,state))
                        if b is None:b=self.fresh(name,n,cls,state)
                else:
                    b=lifetimes.get((name,n,cls,state))
                    if b is None:b=self.fresh(name,n,cls,state)
                lifetimes[(name,n,cls,state)]=b
                env[name] = b
                inactive.discard(name)
                # Bind allocation result outside captured loops; acquire/release
                # retain its source identity. No wire-sized array is created.
                if not adjoint:emit({"acquire":name},False)
                if op == "qcopy":
                    emit({"invoke":"bind.qxor","args":[n,a[0],name]})
                elif op == "qload":
                    A,W,cells = regions[a[0]]
                    addr = [] if a[1] == "()" else a[1]
                    emit({"invoke":"dispatch.copy","args":[A,1<<A,W,addr,cells,name]})
                if adjoint:emit({"relinquish":name},False)
            elif op in ["qfree","qreturn","quncopy","qunload"]:
                name = a[-1]
                require(name in env and isinstance(env[name],Bundle),"release of unknown bundle")
                require(name not in inactive,"release of inactive source binding")
                b = env[name]
                require(lifetimes.get((name,b.width,b.cls,b.state))==b,"§4.3: release requires a locally owned allocation")
                require((b.state=="borrowed")== (op=="qreturn"),"§4.3: release kind differs from clean/borrowed allocation")
                inactive.add(name)
                if adjoint:emit({"acquire":name},False)
                if op == "quncopy": emit({"invoke":"bind.qxor","args":[b.width,a[0],name]})
                if op == "qunload":
                    A,W,cells=regions[a[0]]
                    emit({"invoke":"dispatch.copy","args":[A,1<<A,W,[] if a[1]=="()" else a[1],cells,name]})
                if not adjoint:emit({"relinquish":name},False)
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
                require(len(a)==1 or len(a)==3 and a[1]=="while","qloop while syntax")
                entry=dict(env);entry[_SOURCE_INACTIVE]=set(inactive)
                captured=self.source_loop(inst,env,regions,controls,depth,adjoint,n)
                if len(a)==3:captured=self.conditional_loop(captured,wire(a[2],entry),controls)
                inactive=env[_SOURCE_INACTIVE]
                if out and any(isinstance(b,Bundle) and env.get(key)!=b for key,b in entry.items()):
                    prefix=[node for fragment in reversed(fragments) for node in fragment] if adjoint else list(out)
                    capture=f"$before_loop:{self.serial}";self.serial+=1
                    env[capture]=Captured(prefix,entry,controls)
                    wrapper={"splice":capture};out=[wrapper];fragments=[[wrapper]];beginning=1
                capture=f"$source_loop:{self.serial}";self.serial+=1
                env[capture]=captured;emit({"splice":capture})
            elif op == "qif":
                entry=dict(env);entry[_SOURCE_INACTIVE]=set(inactive)
                then = self.action_nodes(inst.body,env,regions,controls,depth)
                then_name=f"$then:{self.serial}";self.serial+=1
                env[then_name]=Captured(then,dict(env),controls)
                otherwise = self.action_nodes(inst.otherwise,env,regions,controls,depth)
                if out and any(isinstance(b,Bundle) and env.get(key)!=b for key,b in entry.items()):
                    prefix=[node for fragment in reversed(fragments) for node in fragment] if adjoint else list(out)
                    capture=f"$before_if:{self.serial}";self.serial+=1
                    env[capture]=Captured(prefix,entry,controls)
                    wrapper={"splice":capture};out=[wrapper];fragments=[[wrapper]];beginning=1
                inactive=env[_SOURCE_INACTIVE]
                emit({"under":a[0],"body":[{"splice":then_name}]})
                emit({"gate":"x","wires":[a[0]]})
                emit({"under":a[0],"body":otherwise})
                emit({"gate":"x","wires":[a[0]]})
            elif op in ["qstore","qexchm"]:
                A,W,cells=regions[a[0]]
                emit({"invoke":"dispatch.store" if op=="qstore" else "dispatch.exchange","args":[A,1<<A,W,[] if a[1]=="()" else a[1],cells,a[2]]})
            elif op=="ctl":
                require(len(a)>=3,"ctl requires control and region call")
                nested=Instruction(a[1],a[2:],[],block=inst.block,ordinal=inst.ordinal)
                emit({"under":a[0],"body":self.action_nodes([nested],env,regions,controls,depth,adjoint,function_name,oracle_pairs)})
            elif op=="adj":
                require(len(a)>=2,"adj requires region call")
                nested=Instruction(a[0],a[1:],[],block=inst.block,ordinal=inst.ordinal)
                capture=f"$adjcall:{self.serial}";self.serial+=1
                body=self.action_nodes([nested],env,regions,controls,depth,not adjoint,function_name,oracle_pairs)
                env[capture]=Captured(body,dict(env),controls)
                emit({"splice":capture})
            elif op=="action_call":
                emit(self.lower_action_call(inst,env,regions,controls,adjoint))
            elif op=="oracle_call":
                emit(self.lower_oracle_call(inst,env,regions,controls,function))
            elif op=="qinplace":
                emit(self.lower_qinplace(inst,env,regions,controls,adjoint,function,meta))
            elif op == "qregion": pass
            else:
                raise ContractError(f"source binding not implemented: {op}; no estimate or exactness claim emitted")
            fragment=out[beginning:]
            if op=="oracle_call" and oracle_pairs and (inst.block,inst.ordinal) in oracle_pairs:
                recompute=self.oracle_recompute(inst,env,regions,controls,meta,function)
                capture=f"$oracle_cleanup:{self.serial}";self.serial+=1
                env[capture]=Captured(fragment,dict(env),controls,cleanup=True,recompute=recompute)
                wrapper={"splice":capture}
                if self.catalog.ledger is not None:self.catalog.source_metadata[id(wrapper)]=(wrapper,{**meta,"call":False})
                fragment=[wrapper];out[beginning:]=fragment
            if adjoint and op=="qif":
                replacement={"inverse":True,"body":fragment}
                if self.catalog.ledger is not None:self.catalog.source_metadata[id(replacement)]=(replacement,meta)
                fragment=[replacement]
            if not adjoint and op in ["quncopy","qunload","qfree","qreturn"]:
                recompute=None
                if op in ["quncopy","qunload"]:
                    fresh=self.fresh("recompute",b.width)
                    fresh_name=f"$fresh:{self.serial}"
                    local=dict(env);local[fresh_name]=fresh
                    if op=="quncopy":compute={"invoke":"bind.qxor","args":[b.width,a[0],fresh_name]}
                    else:compute={"invoke":"dispatch.copy","args":[A,1<<A,W,[] if a[1]=="()" else a[1],cells,fresh_name]}
                    # Keep the effective predicate on gates, and allocation
                    # lifetimes unconditional, just as in the source copy.
                    quantum=[compute,{"invoke":"bind.qxor","args":[b.width,fresh_name,name]},{"inverse":True,"body":[compute]}]
                    if predicates:quantum=[{"under":list(predicates),"body":quantum}]
                    replacement=[{"acquire":fresh_name},*quantum,{"relinquish":fresh_name},{"relinquish":name}]
                    recompute=Captured(replacement,local,controls)
                capture=f"$cleanup:{self.serial}";self.serial+=1
                env[capture]=Captured(fragment,dict(env),controls,cleanup=True,recompute=recompute)
                wrapper={"splice":capture}
                if self.catalog.ledger is not None:self.catalog.source_metadata[id(wrapper)]=(wrapper,meta)
                fragment=[wrapper];out[beginning:]=fragment
            fragments.append(fragment)
        require(not predicates,"nonempty predicate stack at scope exit")
        return [node for fragment in reversed(fragments) for node in fragment] if adjoint else out


def estimate(obj,target,region,args,budget,variant="forward",inherited_controls=0,step_bound=None,epsilon="0",include_frame=False,token_aliases=None):
    require(region in obj.functions,"unknown entry region")
    require(step_bound is None or obj.functions[region].kind in ["cc","r"],"E_ARG: classical step bound requires a CC/R entry")
    args=loads(jcs(args));budget=list(budget)
    if token_aliases is not None:
        fn=obj.functions[region]
        types=[ty for n,ty,r in (fn.groups[0] if fn.kind in ["cc","r"] else fn.groups[4] if fn.kind=="oracle" else fn.groups[3])]
        values=resolved_arguments(types,args,obj)
        tuples=([budget] if fn.kind=="oracle" else [])+[value for ty,value in zip(types,values) if ty=="token"]
        token_aliases=validate_token_aliases(token_aliases,tuples)
    root_token_context=tuple(("request",label) for label in token_aliases) if token_aliases is not None else None
    require(obj.ptr in target.doc["ptr_widths_supported"],"E_PTR_WIDTH: target does not support object pointer width")
    require(isinstance(variant,str) and variant,"empty variant")
    inherited_controls=integer(inherited_controls,0)
    accuracy=decimal_value(epsilon)
    require(accuracy>=0,"negative request accuracy")
    accuracy_text=exact_decimal(accuracy)
    validate_budget(budget,obj)
    catalog = Catalog(globals().get("CATALOG_TEXT") or (Path(__file__).resolve().parents[1]/"data/ref-0.9.json").read_text(),target)
    identities=obj.identities()
    for symbol in obj.sections["symbols"].values():
        require(identities[symbol["name"]]==symbol["interface_hash"],f"§9.2: incorrect interface_hash for {symbol['name']}")
    closure=obj.identities(closure=True)[region]
    bindings={"closure_hash":closure,"target_hash":target.hash,"region":region,"variant":variant,
              "inherited_controls":inherited_controls,"budget":budget,"params_hash":digest(jcs(args)),"epsilon":accuracy_text if accuracy else 0,
              "expansion":{"name":"ref","version":"0.9","hash":catalog.hash},
              "scheduler":{"name":"bennett-estimate-default","version":"0.1.0"}}
    if token_aliases is not None:bindings["token_aliases"]=token_aliases
    effective_schedule={"bindings":bindings,"entries":[]}
    if "schedule" in obj.sections:
        schedule=obj.sections["schedule"]
        if token_aliases is not None and (schedule["entries"] or "interface_vertices" in schedule):
            require("token_aliases" in schedule["bindings"],"E_ARG: alias-aware schedule requires token_aliases upgrade")
        Schedule(schedule,obj,schedule["bindings"].get("region"))
        def binding_equal(key,value):
            supplied=schedule["bindings"].get(key)
            if key=="expansion" and supplied is None:return obj.versions["isa"]=="0.9"
            if key=="budget":
                return isinstance(supplied,list) and len(supplied)==4 and [rational(n) for n in supplied]==[rational(n) for n in value]
            if key=="epsilon": return supplied is not None and rational(supplied)==rational(value)
            if key=="inherited_controls":return integer(supplied,0)==value
            return supplied==value
        selected=all(binding_equal(k,v) for k,v in bindings.items() if k!="scheduler")
        if selected:
            effective_schedule=loads(jcs(schedule))
    source = Source(obj,target,catalog)
    fn = obj.functions[region]
    if effective_schedule["entries"] and fn.kind in ["action","perm_action","oracle"]:
        admission_catalog=Catalog(catalog.text,target)
        admission_catalog.ledger=Admission(Schedule(effective_schedule,obj,region))
        admission_controls=tuple(("inherited",i,admission_catalog.default_class) for i in range(inherited_controls))
        Source(obj,target,admission_catalog).region(region,args,budget,controls=admission_controls,token_context=root_token_context)
        admission_catalog.ledger.schedule.validate_call_domains(admission_catalog.call_domains)
    ledger=None
    default_share=F(0)
    finite_capacity=any(c["capacity"]!="unbounded" for c in target.doc["classes"].values())
    summarize=fn.kind in ["action","perm_action","oracle"] and not (include_frame or effective_schedule["entries"] or "interface_vertices" in effective_schedule or "topology" in target.doc)
    replay=bool(include_frame or effective_schedule["entries"] or "interface_vertices" in effective_schedule or "topology" in target.doc or accuracy or any(c["capacity"]!="unbounded" for c in target.doc["classes"].values()))
    if replay and not summarize and fn.kind in ["action","perm_action","oracle"]:
        ledger=Ledger(target,Schedule(effective_schedule,obj,region),exact=fn.kind in ["perm_action","oracle"],count_only=bool(accuracy))
        catalog.ledger=ledger
    elif effective_schedule["entries"] or "interface_vertices" in effective_schedule:
        raise ContractError("scheduled classical source replay remains pending; selected schedule was not ignored")
    if fn.kind in ["cc","r"]:
        require(not accuracy and inherited_controls==0,"classical cost request has no accuracy or inherited quantum controls")
        if step_bound is None:
            p,steps = ClassicalMachine(source,fn,args,token_aliases).run()
        else:
            # A caller-supplied termination assumption is explicit evidence,
            # never a proof that an unbounded classical program terminates.
            resolved_arguments([ty for n,ty,r in fn.groups[0]],args,obj)
            classical_ops={"add","sub","mul","and","or","xor","shl","lshr","ashr","udiv","urem","sdiv","srem","select","alloc","free","br","call","uncall","ret","trap","fault","effect","hostcall","inttoptr","budget.mint"}
            reachable=set();pending=[region]
            while pending:
                name=pending.pop()
                if name in reachable:continue
                require(name in obj.functions,"step-only bound has an unresolved call")
                reachable.add(name)
                for inst in obj.functions[name].code:
                    if inst.op=="call":pending.append(inst.args[0].removeprefix("@"))
            for name in reachable:
                f=obj.functions[name]
                require(f.kind in ["cc","r"],"step-only classical bound cannot omit quantum regions")
                require(all(i.op in classical_ops or i.op.startswith(("const.i","icmp.","load.i","store.i","zext.i","sext.i","trunc.i","ptrtoint.i")) for i in f.code),"step-only bound cannot omit quantum/register operations")
            steps=integer(step_bound,0)
            reversals=any(i.op=="uncall" for name in reachable for i in obj.functions[name].code)
            p=Profile(time=rational(target.doc["capabilities"]["classical_step_time"])*steps*(2 if reversals else 1))
        interface = {}
    else:
        controls = tuple(("inherited",i,source.cls) for i in range(inherited_controls))
        sig = obj.symbol(region)["signature"]
        widths = list(sig.get("in",[]))+list(sig.get("mut",[]))+([sig["tgt"],sig["fault"]] if fn.kind=="oracle" else [])
        widths += [(1<<integer(m["A"],0))*integer(m["W"],1) for m in sig.get("mem",[])]
        interface = {source.cls:sum(integer(w,1) for w in widths)+inherited_controls}
        if summarize:
            try:
                if accuracy:
                    # K58 counts source expansion operations before schemes.
                    # The population composes through the same loop algebra.
                    catalog.count_only=True
                    population=source.region(region,args,budget,controls=controls,token_context=root_token_context).inexact_operations
                    default_share=F(accuracy)/population if population else F(0)
                    catalog=Catalog(catalog.text,target);catalog.eps=default_share
                    source=Source(obj,target,catalog)
                p=source.region(region,args,budget,controls=controls,token_context=root_token_context)
                # This is also a proof of the default class decisions: if the
                # sequential peak fits, an any allocation never needs fallback.
                fits=all(desc["capacity"]=="unbounded" or interface.get(cls,0)+p.peak.get((cls,"total"),0)<=desc["capacity"] for cls,desc in target.doc["classes"].items())
            except ContractError as ex:
                if not (finite_capacity and str(ex).startswith("E_GATE_UNSUPPORTED")):raise
                fits=False
            if not fits:
                catalog=Catalog(catalog.text,target)
                ledger=Ledger(target,Schedule(effective_schedule,obj,region),exact=fn.kind in ["perm_action","oracle"],count_only=bool(accuracy))
                catalog.ledger=ledger;source=Source(obj,target,catalog)
        if ledger is not None or not summarize:p=source.region(region,args,budget,controls=controls,token_context=root_token_context)
        if ledger is not None and ledger.count_only:
            count=ledger.nonexact_native_operations
            seen=set()
            while True:
                require(count not in seen,"E_SCHEDULE_INFEASIBLE: class/accuracy default resolution has no stable operation count")
                seen.add(count)
                share=F(accuracy)/count if count else F(0)
                catalog=Catalog(globals().get("CATALOG_TEXT") or (Path(__file__).resolve().parents[1]/"data/ref-0.9.json").read_text(),target)
                ledger=Ledger(target,Schedule(effective_schedule,obj,region),default_share=share,exact=fn.kind in ["perm_action","oracle"])
                catalog.ledger=ledger;source=Source(obj,target,catalog)
                p=source.region(region,args,budget,controls=controls,token_context=root_token_context)
                if ledger.nonexact_native_operations==count:break
                count=ledger.nonexact_native_operations
            require(ledger.error<=accuracy,"E_SCHEDULE_INFEASIBLE: achieved error exceeds request accuracy")
        if accuracy and ledger is None:require(p.error<=accuracy,"E_SCHEDULE_INFEASIBLE: achieved error exceeds request accuracy")
        steps = None
    if ledger is not None:ledger.schedule.validate_call_domains(catalog.call_domains)
    rows=ledger.finish() if ledger is not None else p.resources(target,interface)
    for cls,desc in target.doc["classes"].items():
        peak = rows.get("peak_qubits["+escape(cls)+"]",0)
        require(desc["capacity"]=="unbounded" or peak <= desc["capacity"], f"E_SCHEDULE_INFEASIBLE: capacity exceeded for {cls}")
    result={"schema":"bennett-estimate/0.1", "label":"bound" if step_bound is not None else "exact", "scope":"scheduled reference realisation" if ledger is not None else "sequential reference realisation", "object_hash":obj.hash,
            "kind":fn.kind,"signature":obj.symbol(region)["signature"],"bounds":obj.symbol(region)["signature"].get("bounds",[]),
            "interface_hash":identities[region],"closure_hash":closure,"effective_schedule":effective_schedule,"schedule_hash":digest(jcs(effective_schedule)),
            "target_hash":target.hash,"region":region,"variant":variant,"inherited_controls":inherited_controls,
            "invocation":{"args":args,"budget":budget},"params_hash":digest(jcs(args)),
            "resources":{n:decimal_up(q) for n,q in rows.items()},
            "exact_resources":{n:{"numerator":str(q.numerator),"denominator":str(q.denominator)} for n,q in rows.items()},
            "gates":{n:str(v) for n,v in sorted(ledger.gates.items() if ledger is not None else p.gates.items())},"classical_steps":str(steps) if steps is not None else None,
            "error_bound":str(ledger.error if ledger is not None else p.error),"summary_operations":catalog.visits}
    obligations=target.native_model_obligations()
    if obligations:result["native_model_obligations"]=obligations
    if token_aliases is not None:result["invocation"]["token_aliases"]=token_aliases
    if step_bound is not None:
        result["bound_assumptions"]=[f"classical execution terminates within {steps} source instructions, including callees"]
        if reversals:result["bound_assumptions"].append("each source frame is reversed at most once; at most twice the forward instruction bound is charged")
        result["rational_upper_bounds"]=result.pop("exact_resources")
    elif fn.kind in ["cc","r"]:
        result["classical_status"]=source.classical_status
        result["reversed_classical_steps"]=str(source.reversed_classical_steps)
        if source.classical_fault_reason is not None:result["classical_fault_reason"]=source.classical_fault_reason
    if fn.kind=="oracle":result["padded_steps"]={"forward":budget[0],"inverse":budget[0]}
    if ledger is not None:
        result["resolved_default_epsilon_share"]={"numerator":str(ledger.default_share.numerator),"denominator":str(ledger.default_share.denominator)}
        result["frame"]=ledger.frame()
        result["cleanup_decisions"]=metadata_counts(ledger.cleanup_decisions)
        result["invocation_contexts"]=source.invocations
    elif accuracy:
        result["resolved_default_epsilon_share"]={"numerator":str(default_share.numerator),"denominator":str(default_share.denominator)}
    return result


class Certificate:
    """Schema reader, distinct from a proof or numerical/channel checker."""
    def __init__(self,doc): self.doc=doc

    @staticmethod
    def hash(value):
        require(isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value),"invalid certificate hash")

    @staticmethod
    def array(value):
        require(isinstance(value,list),"certificate field must be array")
        return value

    @staticmethod
    def count(value):
        require(isinstance(value,(int,Decimal,str)) and not isinstance(value,bool),"certificate count must be integer")
        return unsigned(value) if isinstance(value,str) else integer(value,0)

    @staticmethod
    def name(value):
        require(isinstance(value,str) and value,"empty/non-string certificate name")

    @classmethod
    def budget(cls,value):
        require(len(cls.array(value))==4,"K13: budget needs four components")
        for part in value:unsigned(part)

    @classmethod
    def inverse_pair(cls,pair,token_order=None):
        keys(pair,["g","ginv","claim","budget"],["arg_tokens","token_aliases"],"inverse pair")
        cls.hash(pair["g"]);cls.hash(pair["ginv"]);cls.budget(pair["budget"]);cls.count(pair["claim"])
        tokens=pair.get("arg_tokens",{})
        require(isinstance(tokens,dict),"arg_tokens must be object")
        for name,token in tokens.items():cls.name(name);cls.budget(token)
        if token_order is not None:
            require(len(token_order)==len(tokens) and set(token_order)==set(tokens),"inverse pair token argument inventory mismatch")
        if "token_aliases" in pair:
            # With several token arguments, a standalone certificate does not
            # supply formal declaration order. Defer tuple checks until linked;
            # JCS dictionary-key order is not signature order.
            values=([tokens[n] for n in token_order] if token_order is not None else list(tokens.values()) if len(tokens)<=1 else [None]*len(tokens))
            validate_token_aliases(pair["token_aliases"],[pair["budget"]]+values)

    @classmethod
    def inverse_pair_context_covers(cls,pair,budget,argument_tokens,token_aliases):
        """K4/K91 token metadata coverage, not proof or args-domain checking.

        The caller supplies token arguments in callee declaration order. A
        successful result discharges only tuple/identity/budget conditions.
        """
        cls.budget(budget)
        require(isinstance(argument_tokens,dict),"argument_tokens must be an ordered mapping")
        for name,token in argument_tokens.items():cls.name(name);cls.budget(token)
        validate_token_aliases(token_aliases,[budget]+list(argument_tokens.values()))
        cls.inverse_pair(pair)
        if set(pair.get("arg_tokens",{}))!=set(argument_tokens):return False
        cls.inverse_pair(pair,list(argument_tokens))
        if argument_tokens:require("token_aliases" in pair,"E_ARG: inverse pair requires token_aliases upgrade")
        aliases=pair.get("token_aliases",[0])
        return (aliases==token_aliases and
                all(unsigned(a)<=unsigned(b) for a,b in zip(pair["budget"],budget)) and
                all(tuple(map(unsigned,pair["arg_tokens"][n]))==tuple(map(unsigned,value)) for n,value in argument_tokens.items()))

    @classmethod
    def invocation(cls,value,uniform=False,kind=None):
        keys(value,["args","budget"],["token_aliases"],context="invocation")
        if value["args"]=="all" or value["budget"]=="all":
            expected={"args":"all","budget":"all"}
            if "token_aliases" in value:expected["token_aliases"]="all"
            require(uniform and value==expected,"K13/K91: only structural invocations may quantify all arguments, budgets and partitions")
            return
        cls.budget(value["budget"])
        for argument in cls.array(value["args"]):
            if isinstance(argument,list):cls.budget(argument)
            elif isinstance(argument,str) and re.fullmatch(r"0x[0-9a-f]{16}",argument):pass
            else:unsigned(argument)
        if "token_aliases" in value:
            aliases=cls.array(value["token_aliases"])
            tokens=[argument for argument in value["args"] if isinstance(argument,list)]
            if kind=="oracle" or kind is None and len(aliases)==len(tokens)+1:tokens=[value["budget"],*tokens]
            validate_token_aliases(aliases,tokens)

    @classmethod
    def domain(cls,domain,inherited_controls=0):
        keys(domain,["bundles","borrowed","regions"],["args"],"domain")
        require(len(cls.array(domain["bundles"]))>=inherited_controls,"K69: domain omits inherited control positions")
        for group in ["bundles","borrowed","args"]:
            names=set()
            for position,component in enumerate(cls.array(domain.get(group,[]))):
                keys(component,["name","width","lo","hi"],context="domain component")
                cls.name(component["name"])
                # Borrowed names are annotations; allocation position is its
                # identity. Interface names resolve against the linked object.
                if group!="borrowed" and not (group=="bundles" and position<inherited_controls):
                    require(component["name"] not in names,"K72: repeated domain component")
                    names.add(component["name"])
                width=cls.count(component["width"]);lo=cls.count(component["lo"]);hi=cls.count(component["hi"])
                require(width>0 and lo<=hi and hi.bit_length()<=width,"K72: domain width/range mismatch")
                if group=="bundles" and position<inherited_controls:require(width==1,"K69: inherited control width must be one")
        names=set()
        for region in cls.array(domain["regions"]):
            keys(region,["name","cells"],context="domain region");cls.name(region["name"])
            require(region["name"] not in names,"K72: repeated domain region");names.add(region["name"])
            if region["cells"]=="all":continue
            indices=set()
            for cell in cls.array(region["cells"]):
                keys(cell,["index","lo","hi"],context="domain cell")
                index=cls.count(cell["index"]);lo=cls.count(cell["lo"]);hi=cls.count(cell["hi"])
                require(index not in indices and lo<=hi,"K72: repeated cell/reversed range");indices.add(index)

    @classmethod
    def expected(cls,value,kind):
        if isinstance(value,str):
            require(value=="oracle" or value=="inverse_pair" and kind=="exhaustive","unknown expected relation")
            return
        require(isinstance(value,dict) and len(value)==1,"expected relation needs one table/program")
        if "program" in value:cls.hash(value["program"]);return
        keys(value,["table"],context="expected table")
        seen=set()
        for row in cls.array(value["table"]):
            keys(row,["before","after"],context="table row")
            for state in row.values():
                keys(state,["bundles","borrowed","regions"],context="table tuple")
                for group in ["bundles","borrowed"]:
                    for item in cls.array(state[group]):unsigned(item)
                for region in cls.array(state["regions"]):
                    for item in cls.array(region):unsigned(item)
            before=jcs(row["before"])
            require(before not in seen,"K13: duplicate table input");seen.add(before)

    @classmethod
    def metric_bounds(cls,value,metrics=("operator_norm","diamond")):
        keys(value,[],metrics,"metric bounds")
        for bound in value.values():require(decimal_value(bound)>=0,"negative certificate error bound")

    @classmethod
    def variant_key(cls,value,closure=False):
        require(isinstance(value,str) and ":" in value,"invalid variant/control key")
        variant,controls=value.rsplit(":",1);unsigned(controls)
        if closure:
            require(":" in variant,"composition key lacks closure hash")
            hash_,variant=variant.split(":",1);cls.hash(hash_)
        cls.name(variant)

    @classmethod
    def claim(cls,claim,count):
        require(isinstance(claim,dict),"claim must be object")
        kind=claim.get("kind")
        required={"exhaustive":["domain","expected","subject"],"sampled":["domain","expected","subject","sampler"],"structural":["rule","subclaims","witness"],"numerical":["subject","metric","precision_bits","bound"],"channel":["subject","metric","precision_bits","bound","dual"]}
        require(kind in required,"unknown claim kind")
        keys(claim,["kind",*required[kind]],["label","invocation"],"claim")
        if "label" in claim:require(claim["label"] in ["proof","evidence"],"unknown requested claim label")
        if "invocation" in claim:cls.invocation(claim["invocation"],uniform=kind=="structural")
        if "domain" in claim:
            controls=cls.count(claim["subject"].get("inherited_controls",0)) if isinstance(claim.get("subject"),dict) else 0
            cls.domain(claim["domain"],controls);cls.expected(claim["expected"],kind)
            require("args" not in claim["domain"] or claim["expected"]=="inverse_pair","§12.2: only inverse-pair domains quantify args")
        if "subject" in claim:
            subject=claim["subject"]
            keys(subject,["closure_hash","variant","inherited_controls"],["schedule_hash"],"subject")
            cls.hash(subject["closure_hash"]);cls.name(subject["variant"]);cls.count(subject["inherited_controls"])
            if "schedule_hash" in subject:cls.hash(subject["schedule_hash"])
            if kind in ["numerical","channel"] or claim.get("expected")=="oracle":require("schedule_hash" in subject,"K13: realised claim lacks schedule hash")
            if "schedule_hash" not in subject and claim.get("expected")!="inverse_pair":require("invocation" in claim,"K13: standalone reference claim lacks invocation")
        if kind=="sampled":
            sampler=claim["sampler"];keys(sampler,["algorithm","seed","count"],context="sampler")
            seed=cls.array(sampler["seed"])
            require(sampler["algorithm"]=="xoshiro256**" and len(seed)==4,"invalid sampler")
            words=[unsigned(n) for n in seed]
            require(any(words) and all(n.bit_length()<=64 for n in words),"invalid xoshiro256** seed words")
            cls.count(sampler["count"])
        if kind in ["numerical","channel"]:
            require(claim["metric"]==("operator_norm" if kind=="numerical" else "diamond"),"claim metric does not match kind")
            require(cls.count(claim["precision_bits"])>0 and decimal_value(claim["bound"])>=0,"invalid claim precision/bound")
        if kind=="channel":
            for dual in cls.array(claim["dual"]):
                keys(dual,["Y","mu"],context="dual witness");decimal_value(dual["mu"])
                for entry in cls.array(dual["Y"]):
                    require(len(cls.array(entry))==4 and all(isinstance(v,str) for v in entry),"interval entry needs four decimal strings")
                    lo,hi,ilo,ihi=map(decimal_value,entry)
                    require(lo<=hi and ilo<=ihi,"reversed matrix interval")
        if kind=="structural":
            require("invocation" in claim,"K13: structural claim lacks invocation")
            for index in cls.array(claim["subclaims"]):require(cls.count(index)<count,"structural subclaim index outside claims")
            rule=claim["rule"];witness=claim["witness"]
            require(rule in ["translation_lemma","inverse_pair_library","adjoint_table"],"unknown structural rule")
            if rule=="adjoint_table":keys(witness,[],context="adjoint witness")
            elif rule=="inverse_pair_library":
                keys(witness,["library_closure_hash","claim_index"],context="library witness")
                cls.hash(witness["library_closure_hash"]);cls.count(witness["claim_index"])
            else:
                keys(witness,["V","W","X","B","frame"],context="translation witness")
                for values in witness.values():cls.array(values)
                require(len(witness["frame"])==2,"translation frame needs first/last point")

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
        require(isinstance(doc["regions"],dict),"certificate regions must be an object")
        keys(b,["object_hash","interface_hash","closure_hash","reference_program_hash","dialect_mapping_version","target_hash"],["schedule_hash","invocation"],"certificate bindings")
        for key,value in b.items():
            if key.endswith("_hash"): require(isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value),f"invalid {key}")
        if "schedule_hash" in b:
            require("invocation" in b,"K13: scheduled certificate lacks invocation")
        if "invocation" in b:
            root=doc["regions"].get(b["closure_hash"],{})
            cls.invocation(b["invocation"],kind=root.get("kind") if isinstance(root,dict) else None)
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
                for q in region["resources"].values(): require(decimal_value(q)>=0,"negative resource")
            for gate in region["gates_used"].values():
                keys(gate,["count"],["scheme","epsilon"],"gates_used")
                cls.count(gate["count"])
                if "epsilon" in gate:require(decimal_value(gate["epsilon"])>=0,"negative gate epsilon")
                if "scheme" in gate:cls.name(gate["scheme"])
            claims=region["claims"]
            for claim in cls.array(claims):cls.claim(claim,len(claims))
            verification=region["verification"]
            keys(verification,["oracle","borrow_frames","inverse_pairs","unitary","channel","fault_rate"],context="verification")
            indices=[verification["oracle"]] if verification["oracle"] is not None else []
            for group in ["borrow_frames","unitary","channel"]: indices+=cls.array(verification[group])
            for pair in cls.array(verification["inverse_pairs"]):
                cls.inverse_pair(pair)
                indices.append(pair["claim"])
            for i in indices: require(cls.count(i)<len(claims),"claim index outside claims array")
            fault=verification["fault_rate"]
            keys(fault,["domain","faults_by_code","undefined_excluded","layout_dependent_excluded"],context="fault_rate")
            cls.domain(fault["domain"])
            require(isinstance(fault["faults_by_code"],dict),"fault counts must be object")
            for code,count in fault["faults_by_code"].items():
                require(0<unsigned(code)<2**64,"fault code outside nonzero i64 range");cls.count(count)
            cls.count(fault["undefined_excluded"]);cls.count(fault["layout_dependent_excluded"])
            require(isinstance(region["cleanup"],dict) and isinstance(region["error"],dict),"cleanup/error must be objects")
            for key,records in region["cleanup"].items():
                cls.variant_key(key)
                for record in cls.array(records):
                    keys(record,["path","realisation"],context="cleanup")
                    cls.array(record["path"])
                    require(record["realisation"] in ["reverse","recompute"],"unknown certificate cleanup realisation")
            for key,error in region["error"].items():
                cls.variant_key(key);keys(error,["local","inclusive"],context="error")
                cls.metric_bounds(error["local"]);cls.metric_bounds(error["inclusive"])
            for assumption in cls.array(region["definedness_assumptions"]):cls.name(assumption)
        keys(doc["composition"],["multiplicities","epsilon_total","method"],context="composition")
        require(doc["composition"]["method"]=="sum_over_multiplicities","unknown composition method")
        require(isinstance(doc["composition"]["multiplicities"],dict),"multiplicities must be object")
        for key,n in doc["composition"]["multiplicities"].items():cls.variant_key(key,closure=True);cls.count(n)
        keys(doc["composition"]["epsilon_total"],["diamond"],context="epsilon_total")
        cls.metric_bounds(doc["composition"]["epsilon_total"],("diamond",))
        return cls(doc)

    def check_bindings(self,result):
        b=self.doc["bindings"]
        for name in ["object_hash","interface_hash","closure_hash","target_hash","schedule_hash"]:
            require(b.get(name)==result[name],f"certificate {name} mismatch")
        require(b.get("invocation")==result["invocation"],"certificate invocation mismatch")

    def with_estimate(self,result):
        """Add reconstructed K12 costs to supplied, bound proof metadata.

        This produces a certificate document, not a correctness verdict.
        Provenance, claims, domains and error composition are never invented.
        """
        self.check_bindings(result)
        require(result["label"]=="exact" and "frame" in result,"certificate production requires exact costs and a reconstructed frame")
        doc=loads(jcs(self.doc))
        root=doc["regions"].get(result["closure_hash"])
        require(root is not None,"certificate template has no root region")
        for name in ["kind","signature","bounds"]:require(root[name]==result[name],f"certificate template {name} differs from linked source")
        root.update(frame=result["frame"],resources=result["resources"],estimate={"precision_digits":34,"exact_resources":result["exact_resources"]},gates_used={name:{"count":int(count) if int(count)<2**53 else count} for name,count in result["gates"].items()})
        doc["producer"]={"name":"bennett-estimate","version":"0.1.0","materialisation":{"llvm_version":"none","pipeline":"isa-0.9-resource-reconstruction","normaliser_version":"none"}}
        produced=Certificate.read(jcs(doc))
        produced.check_resource_rows(result)
        return produced.doc

    def check_resource_rows(self,result):
        self.check_bindings(result)
        region=self.doc["regions"].get(result["closure_hash"])
        require(region is not None and "estimate" in region,"certificate has no bound K12 estimate")
        for name in ["kind","signature","bounds"]:require(region[name]==result[name],f"certificate {name} differs from linked source")
        gates={n:integer(record["count"],0) for n,record in region["gates_used"].items()}
        require(gates=={n:int(v) for n,v in result["gates"].items()},"certificate gate inventory differs from independently reconstructed native counts")
        require(region["resources"]==result["resources"] and region["estimate"]["exact_resources"]==result["exact_resources"],"certificate resources differ from independently reconstructed cost")
        if "frame" in result:
            def normalise(frame):
                answer={}
                for group in ["slots","scratch","history","borrow","ancillae"]:
                    answer[group]=[]
                    for r in frame[group]:
                        item={k:v for k,v in r.items() if k!="id" or group=="slots"}
                        item["width"]=integer(expression(r["width"],{"c":F(result["inherited_controls"])},{}),0)
                        answer[group].append(item)
                # A trace with distinct occurrences grants no shared storage.
                require(not frame.get("live_ranges"),"certificate frame sharing differs from reconstructed lifetimes")
                return answer
            require(normalise(region["frame"])==normalise(result["frame"]),"certificate frame differs from independently reconstructed lifetimes")
        return "resource_rows_verified; "+("frame_verified; " if "frame" in result else "")+"correctness_claims_not_checked"


def main(argv=None):
    parser=argparse.ArgumentParser(prog="bennett-estimate",allow_abbrev=False,description="ISA 0.9 resource estimator, exact rational arithmetic; JSON on stdout")
    parser.add_argument("object",type=Path)
    parser.add_argument("--target",type=Path,required=True)
    parser.add_argument("--region",help="required for objects with multiple executable definitions")
    parser.add_argument("--params",default="[]",help="complete K13 JSON array, or @file")
    parser.add_argument("--token-aliases",help="canonical K91 token equality partition as a JSON array, or @file")
    parser.add_argument("--budget",help="B,heap,stack,depth; required for oracle/token-taking entries, including an explicit zero tuple")
    parser.add_argument("--variant",default="forward")
    parser.add_argument("--inherited-controls",type=int,default=0)
    parser.add_argument("--epsilon",default="0",help="exact decimal requested accuracy (default 0)")
    parser.add_argument("--certificate",type=Path,help="read certificate and cross-check K12 resources; does not verify correctness claims")
    parser.add_argument("--include-frame",action="store_true",help="reconstruct B5 allocation descriptor, visiting each allocation occurrence")
    parser.add_argument("--certificate-template",type=Path,help="bound certificate supplying provenance and proof metadata for K12 output; claims remain unchecked")
    parser.add_argument("--write-certificate",type=Path,help="write JCS K12 certificate using --certificate-template")
    parser.add_argument("--classical-step-bound",type=int,help="conditional upper bound for purely classical objects; termination assumption is reported")
    a=parser.parse_args(argv)
    try:
        require((a.certificate_template is None)==(a.write_certificate is None),"--certificate-template and --write-certificate must be used together")
        object_bytes=a.object.read_bytes()
        obj=Object.read(object_bytes.decode("utf-8"))
        target=Target.read(a.target.read_text())
        candidates=[f.name for f in obj.functions.values() if f.kind!="lproc"]
        region=a.region or (candidates[0] if len(candidates)==1 else None)
        require(region is not None,"multiple entry regions: supply --region")
        require(region in obj.functions,"unknown entry region")
        fn=obj.functions[region]
        groups=fn.groups[0] if fn.kind in ["cc","r"] else fn.groups[4] if fn.kind=="oracle" else fn.groups[3]
        require(a.budget is not None or fn.kind!="oracle" and all(ty!="token" for n,ty,r in groups),
                "E_ARG: oracle/token-taking entry requires --budget B,heap,stack,depth (use --budget 0,0,0,0 for zero)")
        params=loads(Path(a.params[1:]).read_text() if a.params.startswith("@") else a.params)
        aliases=None
        if a.token_aliases is not None:
            aliases=loads(Path(a.token_aliases[1:]).read_text() if a.token_aliases.startswith("@") else a.token_aliases)
            require(isinstance(aliases,list),"E_ARG: token_aliases must be a JSON array")
        budget=a.budget.split(",") if a.budget is not None else ["0"]*4
        request={"target":a.target.stem,"object_sha256":hashlib.sha256(object_bytes).hexdigest(),
                 "budget":metadata_counts(dict(zip(["steps","heap","stack","depth"],validate_budget(budget,obj))))}
        result=estimate(obj,target,region,params,budget,a.variant,a.inherited_controls,a.classical_step_bound,a.epsilon,a.include_frame or a.certificate is not None or a.certificate_template is not None,aliases)
        result.update(request,padded=result["resources"])
        if a.certificate:
            result["certificate_status"]=Certificate.read(a.certificate.read_text()).check_resource_rows(result)
        if a.certificate_template:
            produced=Certificate.read(a.certificate_template.read_text()).with_estimate(result)
            a.write_certificate.write_text(jcs(produced))
            result["certificate_output"]=str(a.write_certificate)
            result["certificate_status"]=Certificate(produced).check_resource_rows(result)
        print(jcs(result))
        return 0
    except (ContractError,OSError,ValueError,KeyError,TypeError,RecursionError) as ex:
        print(f"bennett-estimate: {ex}",file=sys.stderr)
        code=str(ex).split(":",1)[0]
        if isinstance(ex,ContractError) and code in ["EST-SOURCE-01","EST-SOURCE-02","EST-SOURCE-03","EST-SOURCE-04","EST-CONTEXT-03"]:
            # The request remains concrete/reviewable while the missing
            # published binding is tracked. No resource number is invented.
            pending={**request,"schema":"bennett-estimate/0.1","label":"pending evidence","object_hash":obj.hash,"target_hash":target.hash,
                     "region":region,"variant":a.variant,"inherited_controls":a.inherited_controls,
                     "invocation":{"args":params,"budget":budget},"params_hash":digest(jcs(params)),
                     "epsilon":exact_decimal(decimal_value(a.epsilon)),
                     "pending":[{"code":code,"reason":str(ex).split(":",1)[1].strip()}]}
            if aliases is not None:pending["invocation"]["token_aliases"]=aliases
            print(jcs(pending))
            return 3
        return 1


if __name__=="__main__":
    sys.exit(main())
