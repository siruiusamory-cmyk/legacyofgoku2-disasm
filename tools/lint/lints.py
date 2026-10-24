from __future__ import annotations

import ast
import csv
import io
import os
import re
import subprocess
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QUOTED_INTERPRETER = re.compile(r"""["']cmd["']""")
SWITCH_INTERPRETER = re.compile(r"(?<![\w.\\/:-])cmd\s+[/-][ck]\b", re.I)
BATCH_INTERPRETER = re.compile(r"(?<![\w.\\/:-])cmd(?![A-Za-z0-9_.\-])")
POOL_SOURCE = re.compile(r"(?m)^\s*(?:import\s+multiprocessing\b"
                         r"|from\s+multiprocessing[\w.]*\s+import\b"
                         r"|from\s+concurrent\.futures\s+import\b[^\n]*ProcessPool)")
POOL_CALL = re.compile(r"\b(?:multiprocessing\.Pool|ProcessPoolExecutor)\s*\(")
MAIN_GUARD = re.compile(r"(?m)^if\s+__name__\s*==\s*[\"']__main__[\"']\s*:")
SEARCH_PATH = re.compile(r"sys\.path\.(?:insert|append)\s*\([^)]*")
WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]")

C_SOURCES = (".c",)
CONTROL_KEYWORDS = frozenset(("if", "for", "while", "switch", "return", "do", "else", "sizeof"))
FUNCTION_DEFINITION = re.compile(r"^[^\s#/].*\)\s*\{\s*$")
FUNCTION_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*(?:_[A-Z][A-Za-z0-9]*)+$")
UNKNOWN_FUNCTION_NAME = re.compile(r"^sub_[0-9A-F]{8}$")
MARKER = re.compile(r"NONMATCHING-REFERENCE")
COMPILE_C = re.compile(r"src/[^\s\"]+\.c\b")
TRACKED_IMAGE = re.compile(r"\.gba$")
SIZE_LIMIT = 1024 * 1024
ASSETS = "assets/"

CHECKS = ("P-148-repo-module-path", "P-159-bare-interpreter", "P-167-pool-guard",
          "NAMING-function-name", "NAMING-c-status", "NAMING-symbol",
          "NAMING-address-ratchet", "NAMING-behaviour-test", "ROM-tracked-image",
          "README-numbers", "TEST-silent-return", "P-518-stale-incbin-call", "DUP-block",
          "READABILITY-ratchet", "READABILITY-index", "READABILITY-path",
          "BOUNDS-entry-allow", "RECOMP-census")
ENTRY_ALLOW = "tools/code/FUNCTION_ENTRY_ALLOW.csv"
FUNCTION_ENDS = "tools/code/FUNCTION_ENDS.csv"
FUNCTION_BOUNDS = "tools/code/FUNCTION_BOUNDS.csv"
RECOMP = "tools/recomp/RECOMP_INPUTS.toml"
CODE_MODES = ("arm", "thumb")
ENTRY_FLAGS = ("data", "undecodable", "clobber")
ENTRY_REASONS = ("prefix", "row-start")
ADDRESS_HEX = re.compile(r"^0x[0-9A-Fa-f]{8}$")
STALE_CALL = re.compile(r"incbin\.bat\s+baserom\.gba\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)")
TEST_FILE = re.compile(r"^test_[^/\\]*\.py$")
DUP_MINIMUM = 8
DUP_PYTHON_ROOT = "tools/"
DUP_C_ROOTS = ("src/", "include/")
DUP_IMPORT_LINE = re.compile(r"^(?:from|import|#include)\b")
DUP_ALLOWLIST = ()
README_PERCENT = re.compile(r"([\d.]+)\s*%")
README_BYTES = re.compile(r"([\d,]+)\s+of\s+([\d,]+)\s+bytes")
README_SPLIT = re.compile(r"proven\s+code\s+([\d,]+)\s+B,\s+filtered\s+pointer-entry\s+code\s+"
                          r"([\d,]+)\s+B,\s+literal\s+pool\s+([\d,]+)\s+B,\s+overlay\s+"
                          r"([\d,]+)\s+B,\s+unclassified\s+([\d,]+)\s+B")
README_COMMAND = re.compile(r"python tools\\gate\\gate\.py")
README_FUNCTIONS = re.compile(r"([\d,]+)\s+of\s+the\s+([\d,]+)\s+functions")
BEHAVIOUR_CLASS = "behaviour-test"
BEHAVIOUR_CITATION = re.compile(r"(tools/[A-Za-z0-9_/]+\.py)::([A-Za-z_][A-Za-z0-9_]*)")
BEHAVIOUR_GUARD = "LG2_BEHAVIOUR_TEST"
CITED_PASSED = ("PASSED", "SKIPPED", "XFAIL", "XPASS")
CITED_RESULT = re.compile(r"^(\S+?\.py)::(\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
BATCH = (".cmd", ".bat")
SOURCES = (".py", ".cmd", ".bat")


def line_of(text, index):
    return text.count("\n", 0, index) + 1


def source_files():
    argv = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        return None
    return sorted(name for name in proc.stdout.decode("utf-8", "replace").split("\0")
                  if name.endswith(SOURCES))


def bare_interpreter(name, text):
    patterns = [QUOTED_INTERPRETER, SWITCH_INTERPRETER]
    if name.endswith(BATCH):
        patterns.append(BATCH_INTERPRETER)
    hits = []
    reported = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            line = line_of(text, match.start())
            if line in reported:
                continue
            reported.add(line)
            hits.append(("P-159-bare-interpreter",
                         "%s:%d: %s" % (name, line, text.splitlines()[line - 1].strip())))
    return hits


def pool_without_guard(name, text):
    match = POOL_SOURCE.search(text) or POOL_CALL.search(text)
    if match is None or MAIN_GUARD.search(text):
        return []
    line = line_of(text, match.start())
    return [("P-167-pool-guard", "%s:%d: a process pool in a module with no main guard: %s"
             % (name, line, text.splitlines()[line - 1].strip()))]


def out_of_repo_module_path(name, text):
    hits = []
    for match in SEARCH_PATH.finditer(text):
        if WINDOWS_PATH.search(match.group(0)):
            hits.append(("P-148-repo-module-path",
                         "%s:%d: %s" % (name, line_of(text, match.start()), match.group(0).strip())))
    return hits


def tracked_files():
    argv = ["git", "ls-files", "-z", "--cached"]
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        return None
    return sorted(name for name in proc.stdout.decode("utf-8", "replace").split("\0") if name)


def c_source_files():
    argv = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        return None
    return sorted(name for name in proc.stdout.decode("utf-8", "replace").split("\0")
                  if name.startswith("src/") and name.endswith(C_SOURCES))


def compiled_c_sources():
    try:
        text = open(os.path.join(ROOT, "rebuild.cmd"), encoding="utf-8", errors="replace").read()
    except OSError:
        return set()
    return set(match.group(0) for match in COMPILE_C.finditer(text))


def read_source(name):
    path = name if os.path.isabs(name) else os.path.join(ROOT, name)
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None


def defined_functions(text):
    for number, line in enumerate(text.splitlines(), 1):
        if FUNCTION_DEFINITION.match(line) is None:
            continue
        words = re.findall(r"[A-Za-z_]\w*", line.split("(", 1)[0])
        if not words or words[-1] in CONTROL_KEYWORDS:
            continue
        yield number, words[-1]


def function_name_findings(name, text):
    findings = []
    for number, function in defined_functions(text):
        if FUNCTION_NAME.match(function) or UNKNOWN_FUNCTION_NAME.match(function):
            continue
        findings.append(("NAMING-function-name",
                         "%s:%d: %s is not Module_Verb or sub_08XXXXXX" % (name, number, function)))
    return findings


def c_status_findings(name, text, compiled=None):
    if compiled is None:
        compiled = compiled_c_sources()
    marked = MARKER.search(header_text(text)) is not None
    if name in compiled:
        if marked:
            return [("NAMING-c-status",
                     "%s:1: rebuild.cmd compiles this file and it carries NONMATCHING-REFERENCE"
                     % name)]
        return []
    if marked:
        return []
    return [("NAMING-c-status",
             "%s:1: rebuild.cmd does not compile this file and it carries no "
             "NONMATCHING-REFERENCE marker" % name)]


def header_text(text):
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("/*", "*", "//")):
            break
        lines.append(line)
    return "\n".join(lines)


def tracked_image_name(name):
    if TRACKED_IMAGE.search(name):
        return [("ROM-tracked-image", "%s: a tracked *.gba path" % name)]
    return []


def oversize_tracked(name, size):
    if name.startswith(ASSETS) or size is None or size <= SIZE_LIMIT:
        return []
    return [("ROM-tracked-image", "%s: %d tracked bytes outside assets/" % (name, size))]


def c_source_findings():
    names = c_source_files()
    if names is None:
        return [("lint-enumeration", "git ls-files failed, the C source checks cannot see the tree")]
    findings = []
    compiled = compiled_c_sources()
    for name in names:
        text = read_source(name)
        if text is None:
            findings.append(("lint-read", "%s: cannot be read" % name))
            continue
        findings += function_name_findings(name, text)
        findings += c_status_findings(name, text, compiled)
    return findings


def tracked_rom_findings(tracked=None):
    if tracked is None:
        tracked = tracked_files()
        if tracked is None:
            return [("lint-enumeration",
                     "git ls-files failed, the tracked-path check cannot see the tree")]
    findings = []
    for name in tracked:
        findings += tracked_image_name(name)
        if name.startswith(ASSETS):
            continue
        try:
            size = os.path.getsize(os.path.join(ROOT, name))
        except OSError:
            continue
        findings += oversize_tracked(name, size)
    return findings


def uncomma(text):
    return int(text.replace(",", ""))


def readme_numbers_findings(text, built, total, percent):
    findings = []
    percents = README_PERCENT.findall(text)
    spans = README_BYTES.findall(text)
    found = percents.count(percent)
    if found != 1:
        findings.append(("README-numbers",
                         "README.md: %s %% expected exactly 1 time, found %d"
                         % (percent, found)))
    if len(spans) != 1:
        findings.append(("README-numbers",
                         "README.md: one <built> of <size> bytes span expected, found %d"
                         % len(spans)))
    if README_COMMAND.search(text) is None:
        findings.append(("README-numbers",
                         "README.md: the progress line must name the command that prints it: "
                         "python tools\\gate\\gate.py"))
    for listed in percents:
        if listed != percent:
            findings.append(("README-numbers",
                             "README.md: %s %% is not the gate's %s %%" % (listed, percent)))
    for first, second in spans:
        if (uncomma(first), uncomma(second)) != (built, total):
            findings.append(("README-numbers",
                             "README.md: %s of %s bytes is not the gate's %d of %d bytes"
                             % (first, second, built, total)))
    return findings


def readme_split_findings(text, totals):
    found = README_SPLIT.findall(text)
    if len(found) != 1:
        return [("README-numbers",
                 "README.md: one 'proven code <bytes> B, filtered pointer-entry code <bytes> B, "
                 "literal pool <bytes> B, overlay <bytes> B, unclassified <bytes> B' figure "
                 "expected, found %d" % len(found))]
    measured = [uncomma(cell) for cell in found[0]]
    wanted = [totals[name] for name in ("proven code", "filtered pointer-entry code",
                                        "literal pool", "IWRAM overlay", "unclassified")]
    if measured != wanted:
        return [("README-numbers",
                 "README.md: the split reads %s, not CODE_SPLIT.md's %s"
                 % (", ".join(str(value) for value in measured),
                    ", ".join(str(value) for value in wanted)))]
    return []


def readme_findings():
    text = read_source("README.md")
    if text is None:
        return [("README-numbers", "README.md: cannot be read")]
    sys.path.insert(0, os.path.join(ROOT, "tools", "gate"))
    import gate
    built = gate.source_bytes()
    findings = readme_numbers_findings(text, built, gate.ROM_SIZE,
                                       "%.4f" % (100.0 * built / gate.ROM_SIZE))
    sys.path.insert(0, os.path.join(ROOT, "tools", "split"))
    import code_split
    try:
        totals = code_split.read_totals()
    except (OSError, ValueError) as error:
        return findings + [("README-numbers", "tools/split/CODE_SPLIT.md: %s" % error)]
    module = naming_module()
    starts = module.starts()
    if starts is None:
        return findings + [("README-numbers", "%s: the function boundaries are absent"
                            % naming_site(module, module.BOUNDS))]
    starts = set(starts)
    named = naming_counts(module.read(module.TABLE), starts)
    return (findings + readme_split_findings(text, totals)
            + readme_naming_findings(text, len(starts) - len(named), len(starts)))


def readability_module():
    sys.path.insert(0, os.path.join(ROOT, "tools", "code"))
    sys.path.insert(0, os.path.join(ROOT, "tools", "research"))
    import readability_audit
    return readability_audit


def readability_findings(baseline_text, live):
    site = "tools/lint/READABILITY_BASELINE.txt"
    recorded = dict((key, int(value))
                    for key, value in re.findall(r"(ram|hardware)=(\d+)", baseline_text or ""))
    findings = []
    for key in ("ram", "hardware"):
        if key not in recorded:
            findings.append(("READABILITY-ratchet",
                             "%s: %s=<count> expected" % (site, key)))
            continue
        if live[key] > recorded[key]:
            findings.append(("READABILITY-ratchet",
                             "%s: %s=%d, above the baseline %d"
                             % (site, key, live[key], recorded[key])))
        if live[key] < recorded[key]:
            findings.append(("READABILITY-ratchet",
                             "%s: %s=%d, below the baseline %d, which this tree must lower"
                             % (site, key, live[key], recorded[key])))
    return findings


def newcomer_path_findings(readme, install):
    tokens = ("extract.cmd", "rebuild.cmd", "python tools\\gate\\gate.py", "docs/CODE_INDEX.md")
    findings = []
    for token in tokens:
        if token not in readme and token not in install:
            findings.append(("READABILITY-path",
                             "README.md and INSTALL.md: neither names %s" % token))
    return findings


def readability_index_findings():
    sys.path.insert(0, os.path.join(ROOT, "tools", "code"))
    import code_index
    if code_index.main(["--check"]) == 0:
        return []
    return [("READABILITY-index", "docs/CODE_INDEX.md is not what the tree derives")]


def readability_tree_findings():
    image = os.path.join(ROOT, "baserom.gba")
    if not os.path.exists(image):
        return []
    findings = []
    code = os.path.join(ROOT, "build", "code")
    if os.path.exists(code):
        module = readability_module()
        live = module.counts()
        findings = readability_findings(read_source("tools/lint/READABILITY_BASELINE.txt"),
                                        {"ram": live["ram_literals"],
                                         "hardware": live["hardware_literals"]})
    readme = read_source("README.md") or ""
    install = read_source("INSTALL.md") or ""
    findings += newcomer_path_findings(readme, install)
    findings += readability_index_findings()
    return findings


def naming_module():
    sys.path.insert(0, os.path.join(ROOT, "tools", "code"))
    import name_table
    return name_table


def naming_site(module, path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def naming_symbol_findings(table_text, ledger_text, addresses, starts=None):
    module = naming_module()
    table = naming_site(module, module.TABLE)
    ledger = naming_site(module, module.LEDGER)
    findings = []
    ledger_rows = module.ledger_rows(ledger_text)
    library = set(cells[2] for _number, cells in ledger_rows
                  if len(cells) == 5 and cells[3] == "toolchain-library")
    names = {}
    rows_at = {}
    for number, cells in module.table_rows(table_text):
        site = "%s:%d" % (table, number)
        if len(cells) != 2:
            findings.append(("NAMING-symbol",
                             "%s: one address and one name expected, found %d cell(s)"
                             % (site, len(cells))))
            continue
        address_text, name = cells
        if module.ADDRESS.match(address_text) is None:
            findings.append(("NAMING-symbol",
                             "%s: %s is not 0x and eight lowercase hex digits"
                             % (site, address_text)))
            continue
        if int(address_text, 16) not in addresses:
            findings.append(("NAMING-symbol",
                             "%s: %s is not a code entry the split proves" % (site, address_text)))
        if starts is not None and int(address_text, 16) not in starts:
            findings.append(("NAMING-symbol",
                             "%s: %s is an interior fragment, not a function start"
                             % (site, address_text)))
        if FUNCTION_NAME.match(name) is None and name not in library:
            findings.append(("NAMING-symbol",
                             "%s: %s is not Module_Verb and no toolchain-library ledger row "
                             "names it" % (site, name)))
        if name in rows_at:
            findings.append(("NAMING-symbol",
                             "%s: %s repeats the name at line %d" % (site, name, rows_at[name])))
            continue
        rows_at[name] = number
        names[int(address_text, 16)] = name
    recorded = set()
    for number, cells in ledger_rows:
        site = "%s:%d" % (ledger, number)
        if len(cells) != 5:
            findings.append(("NAMING-symbol",
                             "%s: address,old,new,evidence_class,evidence expected, found %d cell(s)"
                             % (site, len(cells))))
            continue
        address_text, _old, new, evidence_class, evidence = cells
        if module.ADDRESS.match(address_text) is None:
            findings.append(("NAMING-symbol",
                             "%s: %s is not 0x and eight lowercase hex digits"
                             % (site, address_text)))
            continue
        if not evidence_class or not evidence:
            findings.append(("NAMING-symbol",
                             "%s: the row needs an evidence class and an evidence cell" % site))
        if names.get(int(address_text, 16)) != new:
            findings.append(("NAMING-symbol",
                             "%s: %s is not the name table's name for %s"
                             % (site, new, address_text)))
        recorded.add(int(address_text, 16))
    for address in sorted(names):
        if address not in recorded:
            findings.append(("NAMING-symbol",
                             "%s:%d: 0x%08x carries no ledger row"
                             % (table, rows_at[names[address]], address)))
    return findings, names


def naming_ratchet_findings(addresses, names, baseline_text):
    module = naming_module()
    site = "%s:1" % naming_site(module, module.BASELINE)
    live = len([address for address in addresses if address not in names])
    baseline = None
    if baseline_text is not None:
        found = re.search(r"\d+", baseline_text)
        baseline = int(found.group(0)) if found else None
    if baseline is None:
        return [("NAMING-address-ratchet",
                 "%s: one count of address-named functions expected" % site)]
    if live > baseline:
        return [("NAMING-address-ratchet",
                 "%s: %d address-named functions, above the baseline %d" % (site, live, baseline))]
    if live < baseline:
        return [("NAMING-address-ratchet",
                 "%s: %d address-named functions, below the baseline %d, which this tree must "
                 "lower" % (site, live, baseline))]
    return []


def cited_test_problem(path, name):
    text = read_source(path)
    if text is None:
        return "%s cannot be read" % path
    if re.search(r"(?m)^def %s\(" % re.escape(name), text) is None:
        return "%s does not define %s" % (path, name)
    return None


def run_cited_test(path, name, launch=None):
    if os.environ.get(BEHAVIOUR_GUARD) == "1":
        return 0, "skipped: a nested lint run does not run a cited test"
    argv = [sys.executable, "-m", "pytest", "-q", "%s::%s" % (path, name)]
    environment = dict(os.environ)
    environment[BEHAVIOUR_GUARD] = "1"
    proc = (launch or subprocess.run)(argv, cwd=ROOT, capture_output=True, env=environment)
    lines = [line for line in proc.stdout.decode("utf-8", "replace").splitlines() if line.strip()]
    return proc.returncode, lines[-1] if lines else ""


def cited_test_results(text):
    results = {}
    for line in text.splitlines():
        match = CITED_RESULT.match(line)
        if match:
            results[(match.group(1), match.group(2))] = match.group(3)
    return results


def run_cited_tests(pairs, launch=None):
    if os.environ.get(BEHAVIOUR_GUARD) == "1":
        return dict((pair, run_cited_test(*pair)) for pair in pairs)
    environment = dict(os.environ)
    environment[BEHAVIOUR_GUARD] = "1"
    argv = [sys.executable, "-m", "pytest", "-v", "--tb=no"]
    argv += ["%s::%s" % pair for pair in dict.fromkeys(pairs)]
    proc = (launch or subprocess.run)(argv, cwd=ROOT, capture_output=True, env=environment)
    status = cited_test_results(proc.stdout.decode("utf-8", "replace"))
    return dict((pair, (0, "") if status.get(pair, "") in CITED_PASSED
                 else run_cited_test(pair[0], pair[1], launch)) for pair in pairs)


def behaviour_test_findings(ledger_text, tracked=None, run_test=None):
    module = naming_module()
    site = naming_site(module, module.LEDGER)
    found = []
    pending = []
    for number, cells in module.ledger_rows(ledger_text):
        if len(cells) != 5 or cells[3] != BEHAVIOUR_CLASS:
            continue
        place = "%s:%d" % (site, number)
        citations = BEHAVIOUR_CITATION.findall(cells[4])
        if len(citations) != 1:
            found.append((number, ("NAMING-behaviour-test",
                                   "%s: one tools/...py::test_name citation expected, found %d"
                                   % (place, len(citations)))))
            continue
        path, name = citations[0]
        if tracked is None:
            tracked = tracked_files()
            if tracked is None:
                return [("lint-enumeration",
                         "git ls-files failed, the behaviour test check cannot see the tree")]
        if path not in tracked:
            found.append((number, ("NAMING-behaviour-test",
                                   "%s: %s is not tracked" % (place, path))))
            continue
        problem = cited_test_problem(path, name)
        if problem is not None:
            found.append((number, ("NAMING-behaviour-test", "%s: %s" % (place, problem))))
            continue
        pending.append((number, place, path, name))
    if pending:
        pairs = [(path, name) for _number, _place, path, name in pending]
        if run_test is None:
            results = run_cited_tests(pairs)
        else:
            results = dict((pair, run_test(*pair)) for pair in pairs)
        for number, place, path, name in pending:
            code, output = results[(path, name)]
            if code != 0:
                found.append((number, ("NAMING-behaviour-test",
                                       "%s: %s::%s exits %d: %s"
                                       % (place, path, name, code, output))))
    return [finding for _number, finding in sorted(found)]


def naming_counts(table_text, addresses):
    module = naming_module()
    names = {}
    for _number, cells in module.table_rows(table_text):
        if len(cells) == 2 and module.ADDRESS.match(cells[0]):
            names[int(cells[0], 16)] = cells[1]
    return dict((address, name) for address, name in names.items() if address in addresses)


def entry_allow_findings(census_text, ends_text, allow_text):
    if not (allow_text or "").strip():
        return [("BOUNDS-entry-allow", "%s: the tree carries no entry allow-list, so a flagged "
                 "start has no reason recorded" % ENTRY_ALLOW)]
    starts = {}
    for row in csv.DictReader(io.StringIO(census_text or "")):
        if row.get("role") in ("start", "unreferenced"):
            starts[int(row["address"], 16)] = (row["role"], row.get("evidence") or "")
    ends = {}
    for row in csv.DictReader(io.StringIO(ends_text or "")):
        ends[int(row["address"], 16)] = (row["end"], row["reason"])
    findings = []
    seen = set()
    for row in csv.DictReader(io.StringIO(allow_text)):
        address = int(row["address"], 16)
        if address in seen:
            findings.append(("BOUNDS-entry-allow", "%s: 0x%08X is carried twice"
                             % (ENTRY_ALLOW, address)))
        seen.add(address)
        if starts.get(address) != (row["kind"], row["limb"]):
            findings.append(("BOUNDS-entry-allow",
                             "%s: 0x%08X carries kind %s and limb %s, and %s reads %s and %s"
                             % (ENTRY_ALLOW, address, row["kind"], row["limb"], FUNCTION_BOUNDS,
                                starts.get(address, ("-", "-"))[0],
                                starts.get(address, ("-", "-"))[1])))
        if not row["flags"] or any(flag not in ENTRY_FLAGS for flag in row["flags"].split("+")):
            findings.append(("BOUNDS-entry-allow", "%s: 0x%08X carries flags %s, and only %s name"
                             " a byte-level test" % (ENTRY_ALLOW, address, row["flags"],
                                                     ", ".join(ENTRY_FLAGS))))
        if row["reason"] not in ENTRY_REASONS:
            findings.append(("BOUNDS-entry-allow",
                             "%s: 0x%08X is kept with reason %s, and only %s name one"
                             % (ENTRY_ALLOW, address, row["reason"] or "none",
                                ", ".join(ENTRY_REASONS))))
            continue
        entry = row["entry"]
        if row["reason"] == "row-start":
            if entry != "-":
                findings.append(("BOUNDS-entry-allow",
                                 "%s: 0x%08X carries entry %s with no prologue to name"
                                 % (ENTRY_ALLOW, address, entry)))
            continue
        if not ADDRESS_HEX.match(entry or "") or int(entry, 16) <= address:
            findings.append(("BOUNDS-entry-allow",
                             "%s: 0x%08X is kept as a prefix and carries entry %s, which is "
                             "not an address after it" % (ENTRY_ALLOW, address, entry or "-")))
        elif ends.get(int(entry, 16), ("-",))[0] == "-":
            findings.append(("BOUNDS-entry-allow",
                             "%s: 0x%08X is corrected to %s, and %s carries no end there"
                             % (ENTRY_ALLOW, address, entry, FUNCTION_ENDS)))
    return findings


def bounds_allow_findings():
    return entry_allow_findings(read_source(FUNCTION_BOUNDS) or "",
                                read_source(FUNCTION_ENDS) or "",
                                read_source(ENTRY_ALLOW) or "")


def recomp_census_findings(export_text, ends_text):
    sys.path.insert(0, os.path.join(ROOT, "tools", "recomp"))
    import export_inputs
    found = [(int(match.group(1), 16), match.group(2), int(match.group(3)), match.group(4))
             for match in export_inputs.CODE_ROW.finditer(export_text or "")]
    code = {}
    twice = []
    for address, mode, size, origin in found:
        if address in code:
            twice.append(address)
        code[address] = (mode, size, origin)
    rows = list(csv.DictReader(io.StringIO(ends_text or "")))
    opened = [row for row in rows if row["end"] == "-"]
    closed = [row for row in rows if row["end"] != "-"]
    starts = set(int(row["address"], 16) for row in closed)
    missing = [row for row in closed if int(row["address"], 16) not in code]
    extra = sorted(address for address, (mode, _size, _origin) in code.items()
                   if mode in CODE_MODES and address not in starts)
    wrong = [(int(row["address"], 16), row["mode"],
              int(row["end"], 16) - int(row["address"], 16), code[int(row["address"], 16)])
             for row in closed
             if int(row["address"], 16) in code
             and code[int(row["address"], 16)][:2]
             != (row["mode"], int(row["end"], 16) - int(row["address"], 16))]
    origins = [(int(row["address"], 16), code[int(row["address"], 16)][2], row["origin"])
               for row in closed
               if int(row["address"], 16) in code
               and code[int(row["address"], 16)][2] != row["origin"]]
    modeless = sorted(address for address, (mode, _size, _origin) in code.items()
                      if mode not in CODE_MODES)
    findings = []
    if opened:
        findings.append(("RECOMP-census",
                         "%s: %d census row(s) have no end, the first 0x%08X"
                         % (RECOMP, len(opened), int(opened[0]["address"], 16))))
    if missing:
        findings.append(("RECOMP-census",
                         "%s: %d census row(s) have no code row, the first 0x%08X"
                         % (RECOMP, len(missing), int(missing[0]["address"], 16))))
    if wrong:
        address, mode, size, (carried, carried_size, _origin) = wrong[0]
        findings.append(("RECOMP-census",
                         "%s: 0x%08X carries %s and %d B, and %s reads %s and %d B"
                         % (RECOMP, address, carried, carried_size, FUNCTION_ENDS,
                            mode, size)))
    if origins:
        address, carried, read = origins[0]
        findings.append(("RECOMP-census",
                         "%s: 0x%08X carries origin %s, and %s reads %s"
                         % (RECOMP, address, carried, FUNCTION_ENDS, read)))
    if twice:
        findings.append(("RECOMP-census",
                         "%s: %d code row(s) repeat an address, the first 0x%08X"
                         % (RECOMP, len(twice), twice[0])))
    if extra:
        findings.append(("RECOMP-census",
                         "%s: %d code row(s) are absent from %s, the first 0x%08X"
                         % (RECOMP, len(extra), FUNCTION_ENDS, extra[0])))
    if modeless:
        findings.append(("RECOMP-census",
                         "%s: %d code row(s) carry a mode outside %s, the first 0x%08X"
                         % (RECOMP, len(modeless), ", ".join(CODE_MODES), modeless[0])))
    return findings


def recomp_tree_findings():
    return recomp_census_findings(read_source(RECOMP) or "",
                                  read_source(FUNCTION_ENDS) or "")


def naming_tree_findings():
    module = naming_module()
    addresses = set(module.emitted())
    rows = module.bounds()
    site = naming_site(module, module.BOUNDS)
    if rows is None:
        return [("NAMING-symbol", "%s: the function boundaries are absent" % site)]
    census = set(int(cells[0], 16) for cells in rows)
    starts = set(int(cells[0], 16) for cells in rows if cells[1] in ("start", "unreferenced"))
    table_text = module.read(module.TABLE)
    findings = []
    missing = sorted(addresses - census)
    invented = sorted(address for address in census - addresses if address not in starts)
    if missing:
        findings.append(("NAMING-symbol",
                         "%s: %d emitted entry(s) the census does not classify"
                         % (site, len(missing))))
    if invented:
        findings.append(("NAMING-symbol",
                         "%s: %d census row(s) the export does not name and no rule starts"
                         % (site, len(invented))))
    found, names = naming_symbol_findings(table_text, module.read(module.LEDGER), addresses,
                                          starts)
    return (findings + found
            + naming_ratchet_findings(starts, naming_counts(table_text, starts),
                                      module.read(module.BASELINE))
            + behaviour_test_findings(module.read(module.LEDGER)))


def readme_naming_findings(text, address_named, functions):
    found = README_FUNCTIONS.findall(text)
    if len(found) != 1:
        return [("README-numbers",
                 "README.md: one '<a> of the <b> functions' figure expected, found %d"
                 % len(found))]
    measured = [uncomma(cell) for cell in found[0]]
    if measured != [address_named, functions]:
        return [("README-numbers",
                 "README.md: %s of the %s functions is not the tree's %d of %d"
                 % (found[0][0], found[0][1], address_named, functions))]
    return []


def stale_call_findings(text, named):
    findings = []
    for match in STALE_CALL.finditer(text):
        start, end = int(match.group(1), 16), int(match.group(2), 16)
        if (start, end - start) not in named:
            findings.append(("P-518-stale-incbin-call",
                             "rebuild.cmd:%d: %s names a slice no asm/*.s INCBINs"
                             % (line_of(text, match.start()), match.group(0))))
    return findings


def stale_call_tree_findings():
    text = read_source("rebuild.cmd")
    if text is None:
        return [("P-518-stale-incbin-call", "rebuild.cmd: cannot be read")]
    sys.path.insert(0, os.path.join(ROOT, "tools", "gate"))
    import gate
    return stale_call_findings(text, set(gate.incbin_ranges()))


def normalised_lines(name, text):
    rows = python_lines(text) if name.endswith(".py") else c_lines(text)
    return [(number, line) for number, line in rows
            if line and DUP_IMPORT_LINE.match(line) is None]


def python_lines(text):
    out = {}
    strings = set()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return c_lines(text)
    for token in tokens:
        if token.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                          tokenize.DEDENT, tokenize.ENDMARKER):
            continue
        if token.start[0] != token.end[0]:
            continue
        out.setdefault(token.start[0], []).append(token.string)
        if token.type == tokenize.STRING:
            strings.add(token.start[0])
    return [(number, " ".join(parts)) for number, parts in sorted(out.items())
            if len(parts) > 1 or number not in strings]


def c_lines(text):
    out = []
    index = 0
    while index < len(text):
        if text[index] in "\"'":
            end = index + 1
            while end < len(text) and text[end] != text[index]:
                end += 2 if text[end] == "\\" else 1
            end = min(end + 1, len(text))
            out.append(text[index:end])
            index = end
        elif text.startswith("//", index):
            end = text.find("\n", index)
            end = len(text) if end < 0 else end
            out.append(" " * (end - index))
            index = end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = len(text) if end < 0 else end + 2
            out.append("".join("\n" if letter == "\n" else " " for letter in text[index:end]))
            index = end
        else:
            out.append(text[index])
            index += 1
    text = "".join(out)
    return [(number, " ".join(line.split())) for number, line in enumerate(text.splitlines(), 1)]


def dup_scan_files():
    proc = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                          cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        return None
    keep = []
    for name in proc.stdout.decode("utf-8", "replace").split("\0"):
        path = name.replace("\\", "/")
        if path.startswith(DUP_PYTHON_ROOT) and path.endswith(".py"):
            keep.append(name)
        elif path.startswith(DUP_C_ROOTS) and path.endswith((".c", ".h")):
            keep.append(name)
    return sorted(keep)


def duplicate_blocks(names):
    lines = {}
    index = {}
    for name in names:
        text = read_source(name)
        lines[name] = [] if text is None else normalised_lines(name, text)
        for position in range(len(lines[name]) - DUP_MINIMUM + 1):
            key = tuple(text for _, text in lines[name][position:position + DUP_MINIMUM])
            index.setdefault(key, []).append((name, position))
    found = []
    for key in sorted(index):
        places = index[key]
        if len(places) < 2:
            continue
        first = places[0]
        for other in places[1:]:
            if same_before(lines, first, other):
                continue
            found.append((site_of(lines, first), site_of(lines, other),
                          run_length(lines, first, other)))
    return found


def site_of(lines, place):
    name, position = place
    return name, lines[name][position][0]


def same_before(lines, first, other):
    if not first[1] or not other[1]:
        return False
    return lines[first[0]][first[1] - 1][1] == lines[other[0]][other[1] - 1][1]


def run_length(lines, first, other):
    length = DUP_MINIMUM
    while (first[1] + length < len(lines[first[0]])
           and other[1] + length < len(lines[other[0]])
           and lines[first[0]][first[1] + length][1] == lines[other[0]][other[1] + length][1]):
        length += 1
    return length


def dup_allowed(first, second):
    for entry in DUP_ALLOWLIST:
        if ((entry[0], entry[1]), (entry[2], entry[3])) in ((first, second), (second, first)):
            return True
    return False


def dup_block_findings(names=None):
    if names is None:
        names = dup_scan_files()
        if names is None:
            return [("lint-enumeration",
                     "git ls-files failed, the duplicate check cannot see the tree")]
    findings = []
    for first, second, length in duplicate_blocks(names):
        if dup_allowed(first, second):
            continue
        findings.append(("DUP-block", "%s:%d and %s:%d: %d identical lines"
                         % (first[0], first[1], second[0], second[1], length)))
    return findings


def silent_return_findings(name, text):
    if TEST_FILE.match(os.path.basename(name)) is None:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [("TEST-silent-return", "%s:%d: cannot be parsed: %s" % (name, exc.lineno, exc.msg))]
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        for line in returns_in(node.body):
            findings.append(("TEST-silent-return",
                             "%s:%d: %s returns instead of asserting, skipping or failing"
                             % (name, line, node.name)))
    return sorted(findings, key=lambda finding: finding[1])


def returns_in(body, checked=False):
    found = []
    for statement in body:
        if isinstance(statement, ast.Return):
            if not checked:
                found.append(statement.lineno)
            continue
        for nested in nested_bodies(statement):
            found += returns_in(nested, checked)
        checked = checked or checks_or_refuses(statement)
    return sorted(found)


def nested_bodies(statement):
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        return []
    bodies = []
    for field in ("body", "orelse", "finalbody"):
        value = getattr(statement, field, None)
        if isinstance(value, list):
            bodies.append(value)
    bodies += [handler.body for handler in getattr(statement, "handlers", [])]
    bodies += [case.body for case in getattr(statement, "cases", [])]
    return bodies


def checks_or_refuses(statement):
    if isinstance(statement, (ast.Assert, ast.Raise)):
        return True
    if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)):
        return False
    function = statement.value.func
    return (isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name)
            and function.value.id == "pytest" and function.attr in ("skip", "fail", "xfail"))


def run(files=None):
    whole_tree = files is None
    if whole_tree:
        files = source_files()
        if files is None:
            return [("lint-enumeration", "git ls-files failed, the lints cannot see the tree")]
    findings = []
    for name in files:
        path = name if os.path.isabs(name) else os.path.join(ROOT, name)
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            findings.append(("lint-read", "%s: %s" % (name, exc)))
            continue
        findings += bare_interpreter(name, text)
        if name.endswith(".py"):
            findings += pool_without_guard(name, text)
            findings += out_of_repo_module_path(name, text)
        findings += silent_return_findings(name, text)
    if whole_tree:
        findings += c_source_findings()
        findings += naming_tree_findings()
        findings += bounds_allow_findings()
        findings += recomp_tree_findings()
        findings += tracked_rom_findings()
        findings += readme_findings()
        findings += stale_call_tree_findings()
        findings += dup_block_findings()
        findings += readability_tree_findings()
    else:
        findings += dup_block_findings(files)
    return findings


def main(argv=None):
    files = list(argv) if argv else None
    findings = run(files)
    for name, detail in findings:
        print("LINT FAIL %s: %s" % (name, detail))
    print("LINT %s: %d finding(s) over %d file(s)"
          % ("FAIL" if findings else "PASS", len(findings),
             len(files) if files else len(source_files() or [])))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
