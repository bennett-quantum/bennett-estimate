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
#[ignore = "Await council and implementation: docs/design/2026-11-08-recompute-cleanup-admissibility.md §4.1"]
fn pjj_estimator_accepts_both_disjoint_placements() {
    for witness in &WITNESSES[..2] {
        check_estimator(witness, "recompute", "");
    }
}

#[test]
#[ignore = "Await council and implementation: docs/design/2026-11-08-recompute-cleanup-admissibility.md §4.2"]
fn yak_estimator_rejects_both_semantically_wrong_recomputations() {
    check_estimator(&WITNESSES[2], "recompute", "entry:4");
    check_estimator(&WITNESSES[3], "recompute", "entry:5");
}

#[test]
#[ignore = "Await council and implementation: docs/design/2026-11-08-recompute-cleanup-admissibility.md §4.3"]
fn tdf_estimator_accepts_a_matched_input_flip_and_undo() {
    check_estimator(&WITNESSES[4], "recompute", "");
}

#[test]
#[ignore = "Await council and implementation: docs/design/2026-11-08-recompute-cleanup-admissibility.md §4.4"]
fn w2b_estimator_accepts_reading_the_flipped_input() {
    check_estimator(&WITNESSES[5], "recompute", "");
}

#[test]
#[ignore = "Await council and implementation: docs/design/2026-11-08-recompute-cleanup-admissibility.md §4.5"]
fn estimator_accepts_cancelling_scratch_reads() {
    check_estimator(&WITNESSES[6], "recompute", "");
}
