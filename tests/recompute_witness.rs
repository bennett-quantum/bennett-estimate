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
    differing_forward_outputs: usize,
    dirty_forward_releases: usize,
}

macro_rules! witness {
    ($name:literal, $mutable:literal, $inputs:literal, $effect:ident, $different:literal, $dirty:literal) => {
        Witness {
            name: $name,
            source: include_str!(concat!("fixtures/recompute_witness/", $name, ".bisa")),
            recompute: include_str!(concat!("fixtures/recompute_witness/", $name, ".recompute.bisa")),
            mutable: $mutable,
            inputs: $inputs,
            effect: Effect::$effect,
            differing_forward_outputs: $different,
            dirty_forward_releases: $dirty,
        }
    };
}

const WITNESSES: [Witness; 6] = [
    witness!("disjoint-between", "y", "x,z", FlipY, 0, 0),
    witness!("disjoint-before-release", "y", "x,z", FlipY, 0, 0),
    witness!("scratch-read", "y", "x,z", XIntoY, 4, 0),
    witness!("unrestored-input", "x", "z", FlipX, 0, 4),
    witness!("restored-input", "x", "z", Identity, 0, 0),
    witness!("restored-input-read", "x,y", "z", NotXIntoY, 0, 0),
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
    let mut operations: Vec<_> = program.lines().filter_map(|line| {
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
    }).collect();
    if inverse { operations.reverse(); }
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
                assert!(values.insert(name.to_owned(), false).is_none(), "duplicate live allocation: {name}");
            }
            Operation::Release(name) => {
                assert!(!initial.contains_key(name), "cannot release an interface wire");
                // Observe a dirty release rather than erasing its violation.
                // Such an execution is invalid even if its interface agrees.
                releases.push((name.to_owned(), values.remove(name).expect("release must be live")));
            }
            Operation::X(name) => *values.get_mut(name).expect("X target must be live") ^= true,
            Operation::Cx(control, target) => {
                let bit = values[control];
                *values.get_mut(target).expect("CX target must be live") ^= bit;
            }
        }
    }
    assert_eq!(values.keys().collect::<Vec<_>>(), initial.keys().collect::<Vec<_>>(), "all private scratch must be released");
    Execution { interface: values, releases }
}

fn assert_witness(witness: &Witness) {
    let names: Vec<_> = witness.mutable.split(',').chain(witness.inputs.split(',')).collect();
    let mut differing = 0;
    let mut dirty = 0;
    for basis in 0..1 << names.len() {
        let initial: BTreeMap<_, _> = names.iter().enumerate()
            .map(|(bit, name)| (name.to_string(), basis & (1 << bit) != 0)).collect();
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
            assert_eq!(source.interface, expected, "{} inverse={inverse} basis={basis}", witness.name);
            assert!(source.releases.iter().all(|(_, value)| !value), "{} source dirty release", witness.name);
            assert_eq!(source.releases.len(), 1);
            let recompute = execute(witness.recompute, &initial, inverse);
            assert_eq!(recompute.releases.len(), 2);
            if !inverse {
                differing += usize::from(source.interface != recompute.interface);
                dirty += usize::from(recompute.releases.iter().any(|(_, value)| *value));
            }
            if witness.differing_forward_outputs == 0 && witness.dirty_forward_releases == 0 {
                assert_eq!(recompute.interface, expected, "{} inverse={inverse} basis={basis}", witness.name);
                assert!(recompute.releases.iter().all(|(_, value)| !value));
            }
        }
    }
    assert_eq!(differing, witness.differing_forward_outputs, "{} differing output count", witness.name);
    assert_eq!(dirty, witness.dirty_forward_releases, "{} dirty release count", witness.name);
}

#[test]
fn pjj_disjoint_placements_execute_equivalently() {
    for witness in &WITNESSES[..2] { assert_witness(witness); }
}

#[test]
fn yak_scratch_read_changes_four_outputs() { assert_witness(&WITNESSES[2]); }

#[test]
fn yak_unrestored_input_dirties_every_release() { assert_witness(&WITNESSES[3]); }

#[test]
fn tdf_restored_input_executes_equivalently() { assert_witness(&WITNESSES[4]); }

#[test]
fn w2b_read_of_flipped_input_executes_equivalently() { assert_witness(&WITNESSES[5]); }
