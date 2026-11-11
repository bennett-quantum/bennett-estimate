# bennett-estimate

## What this repo is

Resource estimation from ISA objects, certificates and target descriptions, without materialising gates.

It is one of several independent repositories in the Bennett reboot. It talks to
the others only through published specs.

## Where the spec is

Resources and targets: Bennett-ISA-Spec.md section 8 (target 0.3); certificate: section 12 (cert 0.3); objects: section 9 (object 0.3).
The conformance suites for the versions in SPEC_VERSIONS.toml live in bennett-isa-spec.
Spec sources of truth: Bennett-ISA-Spec.md and Bennett-NorthStar.md in the Bennett.jl repo
until bennett-isa-spec is published.

## Rules

The one rulebook is bennett/docs/process/COMMON.md; it binds here. Gate: `scripts/pre-push`. Tasks: `bd` (`bd prime` lists its commands).
