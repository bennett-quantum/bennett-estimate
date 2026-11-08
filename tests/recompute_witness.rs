//! Exact execution witnesses; the proposed admissibility rule is in the design note §3.
use std::collections::BTreeMap;

#[derive(Clone, Copy)]
enum Effect {
    FlipY,
    XIntoY,
    FlipX,
    Identity,
    NotXIntoY,
}

struct Witness {
    name: &'static str,
    source: &'static str,
    recompute: &'static str,
    mutable: &'static str,
    inputs: &'static str,
    effect: Effect,
    differing_outputs_per_direction: usize,
    dirty_releases_per_direction: usize,
}

macro_rules! witness {
    ($name:literal, $mutable:literal, $inputs:literal, $effect:ident, $different:literal, $dirty:literal) => {
        Witness {
            name: $name,
            source: include_str!(concat!("fixtures/recompute_witness/", $name, ".bisa")),
            recompute: include_str!(concat!(
                "fixtures/recompute_witness/",
                $name,
                ".recompute.bisa"
            )),
            mutable: $mutable,
            inputs: $inputs,
            effect: Effect::$effect,
            differing_outputs_per_direction: $different,
            dirty_releases_per_direction: $dirty,
        }
    };
}

const WITNESSES: [Witness; 7] = [
    witness!("disjoint-between", "y", "x,z", FlipY, 0, 0),
    witness!("disjoint-before-release", "y", "x,z", FlipY, 0, 0),
    witness!("scratch-read", "y", "x,z", XIntoY, 4, 0),
    witness!("unrestored-input", "x", "z", FlipX, 0, 4),
    witness!("restored-input", "x", "z", Identity, 0, 0),
    witness!("restored-input-read", "x,y", "z", NotXIntoY, 0, 0),
    witness!("cancelling-scratch-reads", "y", "x,z", Identity, 0, 0),
];

#[derive(Debug, PartialEq, Eq)]
struct Execution {
    interface: BTreeMap<String, bool>,
    releases: Vec<(String, bool)>,
}

#[derive(Clone, Copy)]
enum Operation<'a> {
    Allocate(&'a str),
    Release(&'a str),
    X(&'a str),
    Cx(&'a str, &'a str),
}

fn execute(program: &str, initial: &BTreeMap<String, bool>, inverse: bool) -> Execution {
    // ISA 0.9 §§4.3/5.3: X and CX are phase-free, self-adjoint permutations;
    // adjointing a lifetime exchanges its allocation and release.
    let mut operations: Vec<_> = program
        .lines()
        .filter_map(|line| {
            let words: Vec<_> = line.split_whitespace().collect();
            match words.as_slice() {
                [] | ["^entry():"] => None,
                ["perm_action", "@root", ..] => None,
                [name, "=", "qalloc", "any", "1"] => Some(Operation::Allocate(name)),
                ["qfree", name] => Some(Operation::Release(name)),
                ["x", name] => Some(Operation::X(name)),
                ["cx", control, target] => {
                    assert_ne!(control, target, "CX operands must be disjoint");
                    Some(Operation::Cx(control, target))
                }
                _ => panic!("unsupported exact-oracle instruction: {line}"),
            }
        })
        .collect();
    if inverse {
        operations.reverse();
    }
    let mut values = initial.clone();
    let mut releases = Vec::new();
    for operation in operations {
        let operation = match (inverse, operation) {
            (true, Operation::Allocate(name)) => Operation::Release(name),
            (true, Operation::Release(name)) => Operation::Allocate(name),
            (_, operation) => operation,
        };
        match operation {
            Operation::Allocate(name) => {
                assert!(
                    values.insert(name.to_owned(), false).is_none(),
                    "duplicate live allocation: {name}"
                );
            }
            Operation::Release(name) => {
                assert!(
                    !initial.contains_key(name),
                    "cannot release an interface wire"
                );
                // Observe a dirty release rather than erasing its violation.
                // Such an execution is invalid even if its interface agrees.
                releases.push((
                    name.to_owned(),
                    values.remove(name).expect("release must be live"),
                ));
            }
            Operation::X(name) => *values.get_mut(name).expect("X target must be live") ^= true,
            Operation::Cx(control, target) => {
                let bit = values[control];
                *values.get_mut(target).expect("CX target must be live") ^= bit;
            }
        }
    }
    assert_eq!(
        values.keys().collect::<Vec<_>>(),
        initial.keys().collect::<Vec<_>>(),
        "all private scratch must be released"
    );
    Execution {
        interface: values,
        releases,
    }
}

fn assert_witness(witness: &Witness) {
    let names: Vec<_> = witness
        .mutable
        .split(',')
        .chain(witness.inputs.split(','))
        .collect();
    let mut differing = [0; 2];
    let mut dirty = [0; 2];
    for basis in 0..1 << names.len() {
        let initial: BTreeMap<_, _> = names
            .iter()
            .enumerate()
            .map(|(bit, name)| (name.to_string(), basis & (1 << bit) != 0))
            .collect();
        let mut expected = initial.clone();
        match witness.effect {
            Effect::FlipY => *expected.get_mut("y").unwrap() ^= true,
            Effect::XIntoY => *expected.get_mut("y").unwrap() ^= initial["x"],
            Effect::FlipX => *expected.get_mut("x").unwrap() ^= true,
            Effect::Identity => (),
            Effect::NotXIntoY => *expected.get_mut("y").unwrap() ^= !initial["x"],
        }
        for inverse in [false, true] {
            let source = execute(witness.source, &initial, inverse);
            assert_eq!(
                source.interface, expected,
                "{} inverse={inverse} basis={basis}",
                witness.name
            );
            assert!(
                source.releases.iter().all(|(_, value)| !value),
                "{} source dirty release",
                witness.name
            );
            assert_eq!(source.releases.len(), 1);
            let recompute = execute(witness.recompute, &initial, inverse);
            assert_eq!(recompute.releases.len(), 2);
            let mut candidate_expected = expected.clone();
            if matches!(witness.effect, Effect::XIntoY) {
                *candidate_expected.get_mut("y").unwrap() ^= initial["z"];
            }
            assert_eq!(recompute.interface, candidate_expected);
            if witness.dirty_releases_per_direction != 0 {
                let released: BTreeMap<_, _> = recompute.releases.iter().cloned().collect();
                assert!(released["d"], "unrestored input leaves d=1");
                assert!(!released["u"], "fresh uncomputation still cleans u");
            }
            differing[usize::from(inverse)] += usize::from(source.interface != recompute.interface);
            dirty[usize::from(inverse)] +=
                usize::from(recompute.releases.iter().any(|(_, value)| *value));
            if witness.differing_outputs_per_direction == 0
                && witness.dirty_releases_per_direction == 0
            {
                assert_eq!(
                    recompute.interface, expected,
                    "{} inverse={inverse} basis={basis}",
                    witness.name
                );
                assert!(recompute.releases.iter().all(|(_, value)| !value));
            }
        }
    }
    assert_eq!(
        differing, [witness.differing_outputs_per_direction; 2],
        "{} differing output count",
        witness.name
    );
    assert_eq!(
        dirty, [witness.dirty_releases_per_direction; 2],
        "{} dirty release count",
        witness.name
    );
}

#[test]
fn pjj_disjoint_placements_execute_equivalently() {
    for witness in &WITNESSES[..2] {
        assert_witness(witness);
    }
}

#[test]
fn yak_scratch_read_changes_four_outputs() {
    assert_witness(&WITNESSES[2]);
}

#[test]
fn yak_unrestored_input_dirties_scratch_on_every_basis() {
    assert_witness(&WITNESSES[3]);
}

#[test]
fn tdf_restored_input_executes_equivalently() {
    assert_witness(&WITNESSES[4]);
}

#[test]
fn w2b_read_of_flipped_input_executes_equivalently() {
    assert_witness(&WITNESSES[5]);
}

#[test]
fn cancelling_scratch_reads_execute_equivalently() {
    assert_witness(&WITNESSES[6]);
}

// This bridge only records actual emitted operands. It makes no admissibility
// decisions and does not provide expected basis outputs to the Rust interpreter.
const ESTIMATOR_TRACE: &str = r#"
from pathlib import Path
import sys
root = Path.cwd()
sys.path.insert(0, str(root / 'tests'))
from test_schedule import e, make_object, target, entry, point
fixture, mutable, inputs, realization, rejected_point = sys.argv[1:]
mutable, inputs = mutable.split(','), inputs.split(',')
signature = {'abi':'0.9', 'tier':'q', 'kind':'perm_action',
             'mut':[1]*len(mutable), 'in':[1]*len(inputs),
             'mem':[], 'args':[], 'bounds':[]}
obj = make_object(Path(fixture).read_text().rstrip(), signature)
t = target()
doc = e.estimate(obj, t, 'root', [], ['0']*4)['effective_schedule']
carrier = len(obj.functions['root'].code)-1
doc['entries'] = [entry('cleanup', path=[point(
    obj.symbol('root')['interface_hash'], f'entry:{carrier}')], realisation=realization)]
obj.sections['schedule'] = doc
if rejected_point:
    try:
        e.estimate(obj, t, 'root', [], ['0']*4)
    except e.ContractError as error:
        message = str(error)
        assert 'recompute' in message and rejected_point in message, message
        assert 'pending' not in message, message
    else:
        raise AssertionError('unsafe recompute was accepted as exact')
else:
    result = e.estimate(obj, t, 'root', [], ['0']*4)
    assert result['label'] == 'exact', result
    if realization == 'recompute':
        expected = {'disjoint-between':(8,5,37,[3,5,6]),
                    'disjoint-before-release':(8,5,37,[3,4,6]),
                    'restored-input':(9,4,32,[3,6,7]),
                    'restored-input-read':(10,5,45,[3,7,8]),
                    'cancelling-scratch-reads':(9,5,41,[3,6,7])}
        gates, peak, area, owned = expected[Path(fixture).stem]
        assert result['resources'] == {'gate_count':str(gates), 'time':str(gates),
            'peak_qubits[data]':str(peak), 'qubit_second[data]':str(area)}, result
        decisions = result['cleanup_decisions']
        assert len(decisions) == 1 and decisions[0]['realisation'] == 'recompute', decisions
        assert decisions[0]['owned_points'] == [f'entry:{p}' for p in owned], decisions
    class Trace(e.Ledger):
        def __init__(self, *args):
            super().__init__(*args)
            self.names, self.rows = {}, []
        def interface(self, slot, bundle, vertices=None):
            role, index = slot.split(':')
            self.names[(bundle.identity,bundle.offset)] = {'mut':mutable,'in':inputs}[role][int(index)]
            return super().interface(slot,bundle,vertices)
        def allocate(self, bundle, **address):
            assert bundle.width == 1
            name = f'scratch{len(self.names)}'
            self.names[(bundle.identity,bundle.offset)] = name
            self.rows.append(f'{name} = qalloc any 1')
            return super().allocate(bundle,**address)
        def release(self, bundle, **address):
            assert bundle.width == 1
            self.rows.append('qfree '+self.names[(bundle.identity,bundle.offset)])
            return super().release(bundle,**address)
        def gate(self, op, wires, controls=(), **address):
            assert not controls and all(bundle.width == 1 for bundle in wires)
            self.rows.append(' '.join([op]+[self.names[(b.identity,b.offset)] for b in wires]))
            return super().gate(op,wires,controls,**address)
    traces = []
    for inverse in (False,True):
        catalog = e.Catalog((root/'data/ref-0.9.json').read_text(),t)
        catalog.ledger = Trace(t,e.Schedule(doc,obj,'root'))
        e.Source(obj,t,catalog).region('root',[],['0']*4,raw_inverse=inverse)
        catalog.ledger.finish()
        traces.append('\n'.join(catalog.ledger.rows))
    print('\nRAW\n'.join(traces))
"#;

fn check_estimator(witness: &Witness, realization: &str, rejected_point: &str) {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let fixture = root
        .join("tests/fixtures/recompute_witness")
        .join(format!("{}.bisa", witness.name));
    let output = std::process::Command::new("python3")
        .args(["-I", "-B", "-c", ESTIMATOR_TRACE])
        .arg(fixture)
        .args([witness.mutable, witness.inputs, realization, rejected_point])
        .current_dir(root)
        .output()
        .expect("Python 3 must execute the estimator trace");
    assert!(
        output.status.success(),
        "{} {realization}: {}",
        witness.name,
        String::from_utf8_lossy(&output.stderr)
    );
    if !rejected_point.is_empty() {
        return;
    }
    let stdout = String::from_utf8(output.stdout).expect("trace must be UTF-8");
    let traces: Vec<_> = stdout.trim().split("\nRAW\n").collect();
    assert_eq!(traces.len(), 2, "forward and raw inverse traces required");
    let names: Vec<_> = witness
        .mutable
        .split(',')
        .chain(witness.inputs.split(','))
        .collect();
    for basis in 0..1 << names.len() {
        let initial = names
            .iter()
            .enumerate()
            .map(|(bit, name)| (name.to_string(), basis & (1 << bit) != 0))
            .collect();
        for (direction, trace) in traces.iter().enumerate() {
            // The emitted raw inverse is already reversed: execute it as printed.
            let actual = execute(trace, &initial, false);
            let reference = execute(witness.source, &initial, direction == 1);
            assert_eq!(
                actual.interface, reference.interface,
                "{} basis={basis} direction={direction}",
                witness.name
            );
            assert!(
                actual.releases.iter().all(|(_, value)| !value),
                "{} dirty actual release",
                witness.name
            );
            assert_eq!(
                actual.releases.len(),
                if realization == "reverse" { 1 } else { 2 }
            );
        }
    }
}

#[test]
fn reverse_estimator_operands_execute_like_every_source_witness() {
    for witness in &WITNESSES {
        check_estimator(witness, "reverse", "");
    }
}

#[test]
fn pjj_estimator_accepts_both_disjoint_placements() {
    for witness in &WITNESSES[..2] {
        check_estimator(witness, "recompute", "");
    }
}

#[test]
fn yak_estimator_rejects_both_semantically_wrong_recomputations() {
    check_estimator(&WITNESSES[2], "recompute", "entry:4");
    check_estimator(&WITNESSES[3], "recompute", "entry:5");
}

#[test]
fn tdf_estimator_accepts_a_matched_input_flip_and_undo() {
    check_estimator(&WITNESSES[4], "recompute", "");
}

#[test]
fn w2b_estimator_accepts_reading_the_flipped_input() {
    check_estimator(&WITNESSES[5], "recompute", "");
}

#[test]
fn estimator_accepts_cancelling_scratch_reads() {
    check_estimator(&WITNESSES[6], "recompute", "");
}

const FAMILY_VERDICTS: &str = r#"
import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tests'))
from test_schedule import e, make_object, target, entry, point
t=target()
signature={'abi':'0.9','tier':'q','kind':'perm_action','mut':[1,1],
           'in':[1],'mem':[],'args':[],'bounds':[]}
for source in sys.stdin.read().split('\nCASE\n'):
    obj=make_object(source.rstrip(),signature)
    doc=e.estimate(obj,t,'root',[],['0']*4)['effective_schedule']
    carrier=len(obj.functions['root'].code)-1
    doc['entries']=[entry('cleanup',path=[point(obj.symbol('root')['interface_hash'],
                          f'entry:{carrier}')],realisation='recompute')]
    obj.sections['schedule']=doc
    try:
        result=e.estimate(obj,t,'root',[],['0']*4)
    except e.ContractError as error:
        message=str(error)
        assert 'recompute' in message and 'refused:' in message, message
        assert 'pending' not in message, message
        print('refuse')
    else:
        assert result['label']=='exact', result
        print('admit')
"#;

fn enumerate_retained(prefix: &mut Vec<(usize, usize)>, cases: &mut Vec<Vec<(usize, usize)>>) {
    cases.push(prefix.clone());
    if prefix.len() == 3 {
        return;
    }
    let first_gap = prefix.last().map_or(0, |&(gap, _)| gap);
    for gap in first_gap..3 {
        for operation in 0..4 {
            // Temporary input changes live between inverses, or after the
            // source cleanup. No flip spans the earlier inverse endpoint.
            if gap == 0 && operation == 3 {
                continue;
            }
            prefix.push((gap, operation));
            enumerate_retained(prefix, cases);
            prefix.pop();
        }
    }
}

fn generated_programs(rows: &[(usize, usize)]) -> (String, String) {
    let operations = ["x y\n", "cx x y\n", "cx d y\n", "x x\n"];
    let prefix = "perm_action @root (x:wire, y:wire) (z:wire in) () () ()\n^entry():\nd = qalloc any 1\ncx x d\ncx z d\n";
    let mut source = prefix.to_owned();
    let mut candidate = prefix.to_owned();
    for gap in 0..3 {
        for &(position, operation) in rows {
            if position == gap {
                source.push_str(operations[operation]);
                candidate.push_str(operations[operation]);
            }
        }
        source.push_str(["cx z d\n", "cx x d\n", "qfree d\n"][gap]);
    }
    candidate
        .push_str("u = qalloc any 1\ncx x u\ncx z u\ncx u d\ncx z u\ncx x u\nqfree u\nqfree d\n");
    (source, candidate)
}

fn executed_family_verdict(source: &str, candidate: &str) -> Option<bool> {
    let mut equivalent = true;
    for basis in 0..8 {
        let initial = ["x", "y", "z"]
            .into_iter()
            .enumerate()
            .map(|(bit, name)| (name.to_owned(), basis & (1 << bit) != 0))
            .collect();
        for inverse in [false, true] {
            let original = execute(source, &initial, inverse);
            if original.releases.iter().any(|(_, bit)| *bit) {
                return None;
            }
            let replacement = execute(candidate, &initial, inverse);
            equivalent &= original.interface == replacement.interface
                && replacement.releases.iter().all(|(_, bit)| !bit);
        }
    }
    Some(equivalent)
}

#[test]
fn exhaustive_recompute_family_matches_executed_equivalence() {
    use std::io::Write;
    use std::process::{Command, Stdio};

    let mut cases = Vec::new();
    enumerate_retained(&mut Vec::new(), &mut cases);
    let programs: Vec<_> = cases
        .iter()
        .map(|rows| generated_programs(rows))
        .filter_map(|(source, candidate)| {
            executed_family_verdict(&source, &candidate).map(|verdict| (source, verdict))
        })
        .collect();
    let input = programs
        .iter()
        .map(|(source, _)| source.as_str())
        .collect::<Vec<_>>()
        .join("\nCASE\n");
    let mut child = Command::new("python3")
        .args(["-I", "-B", "-c", FAMILY_VERDICTS])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("Python 3 must execute family verdicts");
    child
        .stdin
        .take()
        .unwrap()
        .write_all(input.as_bytes())
        .expect("family source programs must be delivered");
    let output = child.wait_with_output().expect("family must finish");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout).unwrap();
    let verdicts: Vec<_> = stdout.lines().collect();
    assert_eq!(verdicts.len(), programs.len());
    for ((source, expected), verdict) in programs.iter().zip(verdicts) {
        assert_eq!(
            verdict,
            if *expected { "admit" } else { "refuse" },
            "admit-but-unsound or refuse-but-sound finding:\n{source}"
        );
    }
    let admitted = programs.iter().filter(|(_, verdict)| *verdict).count();
    assert!(admitted > 0 && admitted < programs.len());
    println!(
        "{} generated programs, {} valid sources, {admitted} admit, {} refuse; zero findings",
        cases.len(),
        programs.len(),
        programs.len() - admitted
    );
}

const REUSED_LIFETIME_SOURCE: &str =
    include_str!("fixtures/recompute_witness/reused-lifetime.bisa");

struct ReusedLifetimeCase {
    selector: &'static str,
    literal: &'static str,
    resources: [usize; 3],
    releases: usize,
}

// Hand-derived gates=time / peak / area: two reverse lifetimes cost
// 4/3/12; one replacement costs 6/4/21; both cost 8/4/30. See fixture notes.
const REUSED_LIFETIME_CASES: [ReusedLifetimeCase; 4] = [
    ReusedLifetimeCase {
        selector: "reverse",
        literal: REUSED_LIFETIME_SOURCE,
        resources: [4, 3, 12],
        releases: 2,
    },
    ReusedLifetimeCase {
        selector: "entry:3",
        literal: include_str!("fixtures/recompute_witness/reused-lifetime-first.recompute.bisa"),
        resources: [6, 4, 21],
        releases: 3,
    },
    ReusedLifetimeCase {
        selector: "entry:7",
        literal: include_str!("fixtures/recompute_witness/reused-lifetime-second.recompute.bisa"),
        resources: [6, 4, 21],
        releases: 3,
    },
    ReusedLifetimeCase {
        selector: "both",
        literal: include_str!("fixtures/recompute_witness/reused-lifetime-both.recompute.bisa"),
        resources: [8, 4, 30],
        releases: 4,
    },
];

fn assert_reused_lifetime_trace(
    program: &str,
    source_inverse: bool,
    program_inverse: bool,
    releases: usize,
) {
    for basis in 0..4 {
        let initial = ["x", "z"]
            .into_iter()
            .enumerate()
            .map(|(bit, name)| (name.to_owned(), basis & (1 << bit) != 0))
            .collect();
        let source = execute(REUSED_LIFETIME_SOURCE, &initial, source_inverse);
        assert_eq!(source.interface, initial, "source is identity on x/z");
        assert_eq!(source.releases.len(), 2);
        assert!(source.releases.iter().all(|(_, value)| !value));
        let actual = execute(program, &initial, program_inverse);
        assert_eq!(actual.interface, source.interface);
        assert_eq!(actual.releases.len(), releases);
        assert!(
            actual.releases.iter().all(|(_, value)| !value),
            "dirty release: basis={basis}, source_inverse={source_inverse}"
        );
    }
}

// Only object/schedule construction and actual operand recording use Python;
// the existing independent Rust oracle executes source, literals and traces.
const REUSED_LIFETIME_TRACE: &str = r#"
from pathlib import Path
import sys
root=Path.cwd()
sys.path.insert(0,str(root/'tests'))
from test_schedule import e, make_object, target, entry, point
selector,gates,peak,area=sys.argv[1:]
signature={'abi':'0.9','tier':'q','kind':'perm_action','mut':[],
           'in':[1,1],'mem':[],'args':[],'bounds':[]}
text=(root/'tests/fixtures/recompute_witness/reused-lifetime.bisa').read_text()
obj=make_object(text.rstrip(),signature);t=target()
doc=e.estimate(obj,t,'root',[],['0']*4)['effective_schedule']
realisation='reverse' if selector=='reverse' else 'recompute'
path={} if selector in ('reverse','both') else {'path':[point(
    obj.symbol('root')['interface_hash'],selector)]}
doc['entries']=[entry('cleanup',realisation=realisation,**path)]
obj.sections['schedule']=doc
result=e.estimate(obj,t,'root',[],['0']*4)
assert result['label']=='exact',result
assert result['resources']=={'gate_count':gates,'time':gates,
    'peak_qubits[data]':peak,'qubit_second[data]':area},result
decisions=result['cleanup_decisions']
assert [d['owned_points'] for d in decisions]==[
    ['entry:2','entry:3'],['entry:6','entry:7']],decisions
expected=['recompute' if selector in ('both',p) else 'reverse'
          for p in ('entry:3','entry:7')]
assert [d['realisation'] for d in decisions]==expected,decisions
class Trace(e.Ledger):
    def __init__(self,*args):
        super().__init__(*args)
        self.names,self.rows,self.serial={},[],0
    def interface(self,slot,bundle,vertices=None):
        role,index=slot.split(':')
        assert role=='in' and bundle.width==1
        self.names[(bundle.identity,bundle.offset)]=('x','z')[int(index)]
        return super().interface(slot,bundle,vertices)
    def allocate(self,bundle,**address):
        assert bundle.width==1
        key=(bundle.identity,bundle.offset)
        assert key not in self.names,('duplicate live operand',key)
        name=f'scratch{self.serial}';self.serial+=1
        self.names[key]=name
        self.rows.append(f'{name} = qalloc any 1')
        return super().allocate(bundle,**address)
    def release(self,bundle,**address):
        assert bundle.width==1
        self.rows.append('qfree '+self.names.pop((bundle.identity,bundle.offset)))
        return super().release(bundle,**address)
    def gate(self,op,wires,controls=(),**address):
        assert not controls and all(b.width==1 for b in wires)
        self.rows.append(' '.join([op]+[
            self.names[(b.identity,b.offset)] for b in wires]))
        return super().gate(op,wires,controls,**address)
traces=[]
for inverse in (False,True):
    catalog=e.Catalog((root/'data/ref-0.9.json').read_text(),t)
    catalog.ledger=Trace(t,e.Schedule(doc,obj,'root'))
    e.Source(obj,t,catalog).region('root',[],['0']*4,raw_inverse=inverse)
    catalog.ledger.finish()
    traces.append('\n'.join(catalog.ledger.rows))
print('\nRAW\n'.join(traces))
"#;

fn check_reused_lifetime_estimator(case: &ReusedLifetimeCase) {
    let output = std::process::Command::new("python3")
        .args(["-I", "-B", "-c", REUSED_LIFETIME_TRACE, case.selector])
        .args(case.resources.map(|value| value.to_string()))
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
        .expect("Python 3 must execute the reused-lifetime trace");
    assert!(
        output.status.success(),
        "{}: {}",
        case.selector,
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout).expect("trace must be UTF-8");
    let traces: Vec<_> = stdout.trim().split("\nRAW\n").collect();
    assert_eq!(traces.len(), 2);
    for (direction, trace) in traces.iter().enumerate() {
        assert_reused_lifetime_trace(trace, direction == 1, false, case.releases);
    }
}

#[test]
fn reused_lifetime_literals_and_reverse_execute_cleanly_in_both_directions() {
    for case in &REUSED_LIFETIME_CASES {
        for inverse in [false, true] {
            assert_reused_lifetime_trace(case.literal, inverse, inverse, case.releases);
        }
    }
    check_reused_lifetime_estimator(&REUSED_LIFETIME_CASES[0]);
}

#[test]
fn first_recompute_binds_its_source_allocation_occurrence() {
    check_reused_lifetime_estimator(&REUSED_LIFETIME_CASES[1]);
}

#[test]
fn second_recompute_binds_its_source_allocation_occurrence() {
    check_reused_lifetime_estimator(&REUSED_LIFETIME_CASES[2]);
}

#[test]
fn both_recomputes_bind_distinct_source_allocation_occurrences() {
    check_reused_lifetime_estimator(&REUSED_LIFETIME_CASES[3]);
}
