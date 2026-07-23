#!/usr/bin/env python
"""
Execute a lightweight-seed assistant birth from a Clone Agent generation plan.

The Brain's Clone Agent (`pyauto-brain clone --apply --mode lightweight-seed`)
reasons and emits a plan JSON; this primitive is the Hands that executes it
(the organ split in the agent's DESIGN.md: the Clone Agent never gives birth
itself). It is domain-free: every fact it acts on — target name, reference
path, file sets, name substitutions — arrives in the plan.

Usage:
    python clone_seed.py <plan.json> [--push]

Without --push it builds the seed tree in a scratch directory and stops
(inspection). With --push it creates the target repo PRIVATE under the
reference's owner and pushes the initial commit; flipping public is the
newborn's own publish gate, after the Heart validation legs pass
(PyAutoHeart/docs/newborn_validation.md).

Plan JSON schema (written by _clone.py):
    target: str                       # e.g. autofit_assistant
    owner: str                        # GitHub owner to create under
    reference_path: str               # local checkout of the reference assistant
    substitutions: [[old, new], ...]  # applied to paths AND file text, in order
    generic: [path, ...]              # copy + substitute
    mixed: [path, ...]                # copy + substitute (adaptation queue in PENDING)
    domain: [path, ...]               # NOT copied; drives the PENDING growth queue
    scaffold_dirs: [path, ...]        # created empty with a README stub
"""

import json
import shutil
import subprocess
import sys
import tempfile
from argparse import ArgumentParser
from pathlib import Path

PENDING_HEADER = """# PENDING — the newborn's growth queue

This assistant was born as a **lightweight-seed** clone: the generic
machinery was copied from the reference; everything domain-specific below
is scaffolded, not written. Grow it in use — each line is a future skill,
wiki page or dataset, in the reference's shape.

"""

SCAFFOLD_README = """# (scaffold)

Empty at birth — see PENDING.md at the repo root for what grows here.
"""


def substitute(text, subs):
    for old, new in subs:
        text = text.replace(old, new)
    return text


def build_seed(plan, out_dir):
    ref = Path(plan["reference_path"])
    subs = [tuple(s) for s in plan["substitutions"]]
    copied = 0
    for rel in plan["generic"] + plan["mixed"]:
        src = ref / rel
        dest = out_dir / substitute(rel, subs)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(substitute(src.read_text(), subs))
        except UnicodeDecodeError:
            shutil.copy2(src, dest)  # binary: copy verbatim
        copied += 1

    for rel in plan["scaffold_dirs"]:
        d = out_dir / substitute(rel, subs)
        d.mkdir(parents=True, exist_ok=True)
        (d / "README.md").write_text(SCAFFOLD_README)

    pending = [PENDING_HEADER]
    for rel in sorted(plan["domain"]):
        pending.append(f"- [ ] `{substitute(rel, subs)}` — regenerate for this domain "
                       f"(reference: `{rel}`)\n")
    for rel in sorted(plan["mixed"]):
        pending.append(f"- [ ] review `{substitute(rel, subs)}` — copied with name "
                       f"substitutions only; adapt values to this domain\n")
    (out_dir / "PENDING.md").write_text("".join(pending))
    return copied


def push_seed(plan, out_dir):
    target, owner = plan["target"], plan["owner"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out_dir, check=True)
    subprocess.run(["git", "add", "-A"], cwd=out_dir, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m",
         f"clone_seed: lightweight-seed birth of {target} (plan-driven)"],
        cwd=out_dir, check=True,
    )
    subprocess.run(
        ["gh", "repo", "create", f"{owner}/{target}", "--private",
         "--source", str(out_dir), "--push"],
        check=True,
    )


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--out", type=Path, default=None,
                        help="build dir (default: a temp dir, kept)")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text())
    out_dir = args.out or Path(tempfile.mkdtemp(prefix=f"seed_{plan['target']}_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    copied = build_seed(plan, out_dir)
    n_pending = len(plan["domain"]) + len(plan["mixed"])
    print(f"clone_seed: built {plan['target']} at {out_dir} "
          f"({copied} files copied, {n_pending} PENDING entries)")

    if args.push:
        push_seed(plan, out_dir)
        print(f"clone_seed: pushed https://github.com/{plan['owner']}/{plan['target']} (PRIVATE)")
        print("next: run the Heart newborn validation legs "
              "(PyAutoHeart/docs/newborn_validation.md) before any publish")


if __name__ == "__main__":
    main()
