"""Run reproducible checks against the actual Lab 7 VDM-SL module."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import subprocess
import sys


HERE = Path(__file__).resolve().parent
LABELS = [
    "Unknown notice in the initial state",
    "Two new notices are queued with count 0",
    "Queued notice cannot start sending",
    "Pause / resume restores Queued",
    "Pause / resume restores Ready",
    "First send enters WaitingResult (attempt 1)",
    "Duplicate send while waiting is rejected",
    "Failure at 100 sets retryAt to 105",
    "Send at 104 returns TooEarly; state unchanged",
    "Send at 105 starts attempt 2",
    "Late reply for attempt 1 changes nothing",
    "Reply for attempt 2 reaches terminal Sent",
    "Reschedule to 116; other notice unchanged",
]
NEGATIVE = [
    ("DuplicateReservation", "Register", "Duplicate reservation is rejected"),
    ("DuplicateNotice", "Register", "Reuse of a notice ID is rejected"),
    ("InvalidPayload", "Prepare", "Invalid payload cannot be prepared"),
    ("LateCallback", "RecordResult", "Callback after Sent is rejected"),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("jar", type=Path)
    p.add_argument("--model", type=Path, default=HERE / "Лаб7_специфікація.vdmsl")
    p.add_argument("--checks", type=Path, default=HERE / "Lab7Checks.vdmsl")
    p.add_argument("--log", type=Path, help="Save raw VDMJ output for every run")
    args = p.parse_args()

    java = ["java", "-jar", str(args.jar)]
    options = ["-vdmsl", "-strict", "-c", "UTF-8"]

    def execute(command):
        q = subprocess.run(java + command, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, encoding="utf-8", timeout=25)
        return q.returncode, q.stdout.strip()

    version_rc, version = execute(["-v"])
    type_rc, static = execute(options + [str(args.model)])
    print(version)
    print(f"Model: {args.model.name}")
    print(static)
    if (version_rc or type_rc or "No syntax errors" not in static
            or "No type errors" not in static or "No completion errors" not in static):
        raise SystemExit("Static validation failed")

    def run(operation):
        return execute(options + ["-default", "Lab7Checks", "-e", operation + "()",
                                  str(args.model), str(args.checks)])

    names = ["RunChecks"] + [row[0] for row in NEGATIVE]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, names))
    if args.log:
        args.log.write_text(version + "\n\n[Type check]\n" + static + "\n" +
            "".join(f"\n[{name}; exit {rc}]\n{out}\n"
                    for name, (rc, out) in zip(names, results)), encoding="utf-8")

    if any("No type errors" not in out or "No init errors" not in out for _, out in results):
        raise SystemExit("The scenario modules did not type check or initialize")
    rc, out = results[0]
    matches = re.findall(r"^\[(true|false)((?:, (?:true|false))*)\]$", out, re.M)
    if rc or len(matches) != 1:
        raise SystemExit(out)
    actual = re.findall(r"true|false", "".join(matches[0]))
    if len(actual) != len(LABELS):
        raise SystemExit("Unexpected number of scenario results")
    checks = [(label, value == "true") for label, value in zip(LABELS, actual)]
    checks += [(label, rc != 0 and bool(re.search(
        rf"Precondition failure: pre_{operation}\b", out)))
        for (_, operation, label), (rc, out) in zip(NEGATIVE, results[1:])]
    print("\nVDM-SL interpreter checks (pre / post / inv enabled)")
    for i, (label, ok) in enumerate(checks, 1):
        print(f"{'PASS' if ok else 'FAIL'} C{i:02}  {label}")
    passed = sum(ok for _, ok in checks)
    print(f"\n{passed}/{len(checks)} checks passed.")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
