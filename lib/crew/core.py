"""Mechanism-only implementation of the crew turn contract."""
import argparse, json, os, pathlib, re, subprocess, sys, time, uuid

ROOT = pathlib.Path(os.environ.get("CREW_ROOT", pathlib.Path(__file__).resolve().parents[2]))
ROLES = {"worker", "reviewer", "tester", "scout"}
RATE_LIMITS = ("rate limit", "429", "quota exceeded", "insufficient_quota", "usage limit reached")
POLICY_CATEGORIES = ("Destructive git operations", "Destructive filesystem operations", "Secrets and credentials", "Production systems and live customer data", "Outward-facing actions")
RISK_HINTS = {
    "Destructive git operations": {"erase", "force", "reset", "rewrite", "rename", "discard"},
    "Destructive filesystem operations": {"rm", "delete", "overwrite", "truncate", "unlink", "wipe"},
    "Secrets and credentials": {"expose", "reveal", "secret", "credential", "token", "password", "key"},
    "Production systems and live customer data": {"production", "customer"},
    "Outward-facing actions": {"email", "slack", "publish", "pull", "request", "pay", "invoice", "contact"},
}
STOPWORDS = {"about", "access", "action", "approval", "can", "client", "data", "explicit", "finished", "for", "including", "local", "may", "never", "only", "operations", "policy", "report", "require", "requires", "run", "should", "system", "systems", "table", "the", "this", "to", "under", "user", "users", "without"}

class CrewError(Exception): pass

def common_root():
    common = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"], text=True).strip()
    path = pathlib.Path(common)
    if not path.is_absolute(): path = ROOT / path
    return path.resolve().parent

def home(delegation=None):
    base = common_root() / ".factory" / "crew"
    return base / delegation if delegation else base

def state_path():
    delegation = os.environ.get("FACTORY_CREW_DELEGATION_ID")
    if not delegation: raise CrewError("missing FACTORY_CREW_DELEGATION_ID")
    path = home(delegation) / "state.json"
    if not path.exists(): raise CrewError(f"unknown delegation: {delegation}")
    return path

def load(): return json.loads(state_path().read_text())
def save(state):
    path = (home(state["delegation_id"]) / "state.json") if "delegation_id" in state else state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
def output(value): print(json.dumps(value, sort_keys=True))
def event(name, state, **fields):
    command = [str(ROOT / "bin" / "telemetry-record"), name, f"trace_id={state['delegation_id']}", f"domain={state['domain']}"]
    command.extend(f"{key}={value}" for key, value in fields.items())
    subprocess.run(command, check=False, stdout=subprocess.DEVNULL)

def adapter(kind):
    selected = os.environ.get(f"FACTORY_{kind.upper()}", "herdr" if kind == "mux" else "pi")
    if not selected.replace("-", "").replace("_", "").isalnum(): raise CrewError(f"invalid {kind} adapter name: {selected}")
    directory = ROOT / "lib" / "crew" / "adapters"
    matches = [path for path in directory.glob(f"{selected}_{kind}*") if path.is_file() and os.access(path, os.X_OK)]
    if len(matches) != 1:
        expected = directory / f"{selected}_{kind}"
        raise CrewError(f"missing {kind} adapter: {selected} ({expected})")
    return [str(matches[0])]
def invoke(kind, verb, args=(), stdin=None):
    command = adapter(kind) + [verb, *args]
    result = subprocess.run(command, input=stdin, text=True, capture_output=True)
    if result.returncode: raise CrewError(result.stderr.strip() or f"{kind} adapter {verb} failed")
    return result.stdout

def capabilities(kind):
    try: value = json.loads(invoke(kind, "crew_capabilities" if kind == "mux" else "worker_capabilities"))
    except json.JSONDecodeError as exc: raise CrewError(f"malformed {kind} capability document: {exc}")
    required = ("layout", "focus", "persistent_context", "native_status", "banner", "isolation") if kind == "mux" else ("isolation", "session_resume")
    if not isinstance(value, dict) or any(not isinstance(value.get(key), bool) for key in required):
        raise CrewError(f"malformed {kind} capability document")
    if kind == "mux": value["isolation"] = capabilities("worker")["isolation"]
    return value

def profile():
    sources = [ROOT / "config/profiles.local.json", ROOT / "config/profiles.json", ROOT / ".claude/skills/delegate-to-pi/references/pi-profiles.json"]
    for source in sources:
        if not source.exists(): continue
        try: data = json.loads(source.read_text())
        except json.JSONDecodeError as exc: raise CrewError(f"malformed profile table {source}: {exc}")
        if "default_tier" not in data or not all(t in data.get("profiles", {}) for t in "SML"):
            raise CrewError(f"malformed profile table {source}: missing required tier or default_tier")
        return data
    raise CrewError("no profile table found")
def resolve_domain(explicit, cwd):
    if explicit: return explicit
    workspace = pathlib.Path(cwd) / "WORKSPACE.md"
    if workspace.exists():
        match = re.search(r"^domain:\s*(\S+)", workspace.read_text(), re.M)
        if match: return match.group(1)
    return "software"

def domain_pack_path(domain):
    directory = pathlib.Path(os.environ.get("FACTORY_DOMAIN_PACK_DIR", ROOT / ".claude/skills/delegate-to-pi/references/domains"))
    return directory / f"{domain}.md"

def domain_pack(domain):
    path = domain_pack_path(domain)
    if not path.exists(): raise CrewError(f"missing domain pack: {path}")
    markdown_sections(path, ("Workspace layout", "Verify command", "Reviewer rubric", "Risk gate", "Roles", "Definition of done"))
    return path

def verify_command(pack):
    text = pack.read_text()
    try: command = text.split("## Verify command\n```bash\n", 1)[1].split("\n```", 1)[0]
    except IndexError: raise CrewError(f"missing Verify command in domain pack: {pack}")
    if not any(line.strip() and not line.lstrip().startswith("#") for line in command.splitlines()):
        raise CrewError(f"missing runnable Verify command in domain pack: {pack}")
    return command

def run_verify_command(pack):
    return subprocess.run(["bash", "-c", verify_command(pack)]).returncode

def require_running(state):
    if state["state"] == "escalated": raise CrewError("delegation is escalated; refusing action")
    if state["state"] != "running": raise CrewError("delegation is not running")
def role(state, name):
    item = state["roles"].get(name)
    if not item: raise CrewError(f"role not spawned: {name}")
    return item

def markdown_sections(path, required=()):
    if not path.exists(): raise CrewError(f"missing policy file: {path}")
    try: text = path.read_text()
    except UnicodeDecodeError as exc: raise CrewError(f"unparseable policy file {path}: {exc}")
    sections, heading, body = {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading: sections[heading] = "\n".join(body).strip()
            heading, body = line[3:].strip(), []
        elif heading: body.append(line)
    if heading: sections[heading] = "\n".join(body).strip()
    missing = [name for name in required if not sections.get(name)]
    if missing: raise CrewError(f"unparseable policy file {path}: missing section {', '.join(missing)}")
    return sections

def risk_stem(word):
    word = word.lower()
    if word.startswith("pay"): return "pay"
    for suffix in ("ments", "ment", "ing", "ies", "es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[:-len(suffix)] + ("y" if suffix == "ies" else "")
    return word

def risk_terms(text):
    return {risk_stem(word) for word in re.findall(r"[a-z0-9]+", text.lower())
            if len(word) >= 2 and word not in STOPWORDS}

def classify_risk(question, domain):
    policy = markdown_sections(ROOT / "POLICY.md", POLICY_CATEGORIES)
    overlays = [policy]
    local = ROOT / "POLICY.local.md"
    if local.exists(): overlays.append(markdown_sections(local))
    pack = markdown_sections(ROOT / f".claude/skills/delegate-to-pi/references/domains/{domain}.md", ("Risk gate",))
    sources = [(heading, policy[heading]) for heading in POLICY_CATEGORIES]
    sources.extend((heading, body) for source in overlays[1:] for heading, body in source.items())
    sources.append((f"{domain} Risk gate", pack["Risk gate"]))
    source_terms = {heading: risk_terms(f"{heading} {body}") for heading, body in sources}
    term_counts = {term: sum(term in terms for terms in source_terms.values())
                   for terms in source_terms.values() for term in terms}
    question_terms = risk_terms(question)
    matches = []
    for heading, _ in sources:
        terms = {term for term in source_terms[heading] if term_counts[term] == 1}
        terms |= RISK_HINTS.get(heading, set())
        if question_terms & terms: matches.append(heading)
    return matches

def classify_risk_command(_):
    state = load(); matches = classify_risk(sys.stdin.read(), state["domain"])
    output({"matches": matches, "keyword_match": bool(matches), "must_still_judge": True})

def doctor(_):
    mux, worker = capabilities("mux"), capabilities("worker")
    output({"mux": mux, "worker": worker})
def begin(args):
    if args.tier not in "SML": raise CrewError("tier must be S, M, or L")
    domain = resolve_domain(args.domain, pathlib.Path.cwd())
    profiles = profile(); domain_pack(domain); delegation = str(uuid.uuid4()); directory = home(delegation); directory.mkdir(parents=True)
    state = {"delegation_id": delegation, "tier": args.tier, "domain": domain, "mux": os.environ.get("FACTORY_MUX", "herdr"), "worker": os.environ.get("FACTORY_WORKER", "pi"), "crew_mode": args.tier != "S", "round": 0, "turn": 0, "state": "running", "roles": {}, "diff_hashes": [], "last_verdict": None, "profile": profiles["profiles"][args.tier]}
    save(state); (directory / "progress.md").touch()
    output({"delegation_id": delegation, "next": f"pass --delegation-id {delegation} to every later crew command"})
def wait_for_settlement(identifier, timeout=60):
    """Wait for a spawned worker before its pane is inspected for a banner."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = invoke("mux", "crew_status", [identifier]).strip()
        if current == "settled": return
        if current in ("blocked", "failed"): raise CrewError(f"worker did not settle before profile verification: {current}")
        time.sleep(1)
    raise CrewError("worker did not settle before profile verification: timeout")

def verify_profile(identifier, selected_profile):
    command = adapter("mux") + ["crew_verify_profile", identifier, selected_profile["provider"], selected_profile["model"], selected_profile["thinking"]]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode == 2:
        print("crew: warning: cannot verify profile; adapter reports banner=false", file=sys.stderr)
        return "unverifiable"
    if result.returncode:
        raise CrewError(result.stderr.strip() or "mux adapter crew_verify_profile failed")
    return "verified"

def spawn(args):
    state = load(); require_running(state); name = args.role
    if args.tier is not None and args.tier not in "SML": raise CrewError(f"invalid tier {args.tier!r}; tier must be S, M, or L")
    role_tier = args.tier or state["tier"]
    role_profile = state["profile"] if args.tier is None else profile()["profiles"][role_tier]
    prefix = f"crew-{name}-{role_tier}"; cwd = str(pathlib.Path.cwd())
    session_id = str(uuid.uuid4()) if name == "scout" else f"{state['delegation_id']}-{name}"

    def _record_profile_reuse():
        profile_verified = "unverifiable" if not capabilities("mux")["banner"] else "verified"
        if profile_verified == "unverifiable": print("crew: warning: cannot verify profile; adapter reports banner=false", file=sys.stderr)
        event("pi_reuse", state, role=name)
        return profile_verified

    agents = json.loads(invoke("mux", "crew_list"))
    if name in state["roles"] and name != "scout":
        saved = state["roles"][name]
        if saved.get("tier", state["tier"]) == role_tier:
            live = next((agent for agent in agents if agent.get("id") == saved["id"] and agent.get("status") == "settled"), None)
            if live:
                saved.update({"tier": role_tier, "profile": role_profile})
                save(state)
                profile_verified = _record_profile_reuse()
                output({"id": saved["id"], "reused": True, "profile": role_profile, "profile_verified": profile_verified})
                return
        del state["roles"][name]
    found = next((a for a in agents if isinstance(a.get("name"), str) and (a["name"] == prefix or a["name"].startswith(prefix + "-")) and a.get("cwd") == cwd and a.get("status") == "settled"), None)
    if found:
        identifier, reused = found["id"], True
        profile_verified = _record_profile_reuse()
    else:
        argv = json.loads(invoke("worker", "worker_argv", [role_profile["provider"], role_profile["model"], role_profile["thinking"], session_id, ""]))
        spawn_args = [prefix, cwd, *( ["--stack-under", args.stack_under] if args.stack_under else [] ), "--", *argv]
        identifier = json.loads(invoke("mux", "crew_spawn", spawn_args))["id"]
        try:
            if capabilities("mux")["banner"]:
                wait_for_settlement(identifier)
                profile_verified = verify_profile(identifier, role_profile)
            else:
                profile_verified = "unverifiable"
                print("crew: warning: cannot verify profile; adapter reports banner=false", file=sys.stderr)
            if not capabilities("worker")["isolation"]:
                print("crew: warning: worker cannot provide repo-local skill isolation", file=sys.stderr)
        except CrewError:
            try: invoke("mux", "crew_close", [identifier])
            except CrewError: pass
            raise
        reused = False; event("pi_spawn", state, role=name)
    state["roles"][name] = {"id": identifier, "session_id": session_id, "tier": role_tier, "profile": role_profile, "fallback_used": False}
    save(state)
    output({"id": identifier, "reused": reused, "profile": role_profile, "profile_verified": profile_verified})
def send(args):
    state = load(); require_running(state); item = role(state, args.role); invoke("mux", "crew_send", [item["id"]], sys.stdin.read()); output({"sent": True})
def wait(args):
    state = load(); require_running(state); item = role(state, args.role); interval = args.interval; elapsed = 0; seen_working = False; settled = 0
    mux_capabilities = capabilities("mux")
    while elapsed <= args.timeout:
        if not mux_capabilities["native_status"]:
            turn_output = invoke("mux", "crew_read", [item["id"]])
            if "CREW_SETTLED" in turn_output:
                output({"outcome": "settled", "path": "sentinel_marker", "output": turn_output})
                return
            if interval: time.sleep(interval)
            elapsed += interval or 1
            continue
        status = invoke("mux", "crew_status", [item["id"]]).strip()
        if status == "timeout": output({"outcome": "timeout", "path": "native_timeout", "output": invoke("mux", "crew_read", [item["id"]])}); return
        if status == "failed": output({"outcome": "failed", "path": "native_failed", "output": invoke("mux", "crew_read", [item["id"]])}); return
        if status in ("settled", "blocked"):
            turn_output = invoke("mux", "crew_read", [item["id"]])
            if mux_capabilities["persistent_context"] and any(signature in turn_output.lower() for signature in RATE_LIMITS):
                output({"outcome": "failed", "path": "rate_limit", "output": turn_output})
                return
            if not mux_capabilities["persistent_context"]:
                output({"outcome": "blocked" if status == "blocked" else "settled", "path": "synchronous", "output": turn_output})
                return
            settled += 1
            if seen_working and settled >= 3: output({"outcome": "blocked" if status == "blocked" else "settled", "path": "after_unsettled", "output": invoke("mux", "crew_read", [item["id"]])}); return
            if not seen_working and elapsed >= 60: output({"outcome": "blocked" if status == "blocked" else "settled", "path": "all_settled_escape_hatch", "output": invoke("mux", "crew_read", [item["id"]])}); return
        else: seen_working = True; settled = 0
        if interval: time.sleep(interval)
        elapsed += interval or 1
    output({"outcome": "timeout", "path": "timeout", "output": invoke("mux", "crew_read", [item["id"]])}); raise CrewError("wait timed out")
def fallback(args):
    state = load(); require_running(state); item = role(state, args.role)
    if item["fallback_used"]:
        state["state"] = "escalated"; save(state); event("pi_escalated", state, reason="fallback_exhausted", role=args.role); output({"state": "escalated", "reason": "fallback_exhausted"}); raise CrewError("fallback exhausted")
    item["fallback_used"] = True; invoke("mux", "crew_close", [item["id"]]); fallback_profile = item.get("profile", state["profile"])["fallback"]
    session_id = str(uuid.uuid4())
    argv = json.loads(invoke("worker", "worker_argv", [fallback_profile["provider"], fallback_profile["model"], fallback_profile["thinking"], session_id, ""]))
    identifier = json.loads(invoke("mux", "crew_spawn", [f"crew-{args.role}-{item.get('tier', state['tier'])}", str(pathlib.Path.cwd()), "--", *argv]))["id"]
    try:
        wait_for_settlement(identifier); profile_verified = verify_profile(identifier, fallback_profile)
    except CrewError:
        try: invoke("mux", "crew_close", [identifier])
        except CrewError: pass
        raise
    item.update({"id": identifier, "session_id": session_id}); save(state); event("pi_fallback", state, role=args.role, provider=fallback_profile["provider"]); output({"id": identifier, "fallback": True, "profile_verified": profile_verified})
def end_counter(args, kind):
    state = load(); require_running(state); cap = 5 if kind == "round" else 6; key = kind
    state[key] += 1; state["last_verdict"] = getattr(args, "verdict", None)
    diff = getattr(args, "diff_hash", None)
    if diff: state["diff_hashes"] = (state["diff_hashes"] + [diff])[-2:]
    no_progress = len(state["diff_hashes"]) == 2 and state["diff_hashes"][0] == state["diff_hashes"][1]
    if state[key] > cap or no_progress:
        state["state"] = "escalated"; save(state); event(f"pi_{'crew_' if kind == 'round' else ''}{kind}_cap_hit", state); output({"state": "escalated", "reason": "no_progress" if no_progress else f"{kind}_cap"}); raise CrewError(f"{kind} cap reached")
    save(state)
    if kind == "round": event("pi_crew_round", state, verdict=state["last_verdict"] or "")
    output({key: state[key]})
def ledger(args):
    state = load()
    require_running(state)
    with (state_path().parent / "progress.md").open("a") as file:
        file.write(args.text + "\n")
def verify(_):
    state = load()
    raise SystemExit(run_verify_command(domain_pack_path(state["domain"])))
def end(args):
    state = load(); state["state"] = "done" if args.outcome == "goal_met" else "escalated"; save(state); event("pi_delegation_end", state, outcome=args.outcome); output({"state": state["state"]})

def main():
    # Accept the delegation handle before or after any subcommand; environment is fallback only.
    raw_args = sys.argv[1:]
    if "--delegation-id" in raw_args:
        index = raw_args.index("--delegation-id")
        try: os.environ["FACTORY_CREW_DELEGATION_ID"] = raw_args[index + 1]
        except IndexError: raise CrewError("--delegation-id requires a value")
        del raw_args[index:index + 2]
    parser = argparse.ArgumentParser(prog="crew"); sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor"); p = sub.add_parser("begin"); p.add_argument("--tier", required=True); p.add_argument("--domain"); p.add_argument("--goal-file")
    p = sub.add_parser("spawn"); p.add_argument("--role", choices=ROLES, required=True); p.add_argument("--stack-under"); p.add_argument("--tier")
    p = sub.add_parser("send"); p.add_argument("--role", choices=ROLES, required=True)
    p = sub.add_parser("wait"); p.add_argument("--role", choices=ROLES, required=True); p.add_argument("--timeout", type=float, default=600); p.add_argument("--interval", type=float, default=5)
    p = sub.add_parser("read"); p.add_argument("--role", choices=ROLES, required=True); p.add_argument("--recent", action="store_true"); p.add_argument("--visible", action="store_true"); p.add_argument("--lines", type=int)
    p = sub.add_parser("close"); p.add_argument("--role", choices=ROLES, required=True)
    p = sub.add_parser("fallback"); p.add_argument("--role", choices=ROLES, required=True)
    p = sub.add_parser("round"); p.add_argument("end"); p.add_argument("--verdict", choices=("approved", "changes_requested", "tester_pass", "tester_bugs"), required=True); p.add_argument("--diff-hash")
    p = sub.add_parser("turn"); p.add_argument("end")
    p = sub.add_parser("ledger"); p.add_argument("append"); p.add_argument("text")
    sub.add_parser("state"); sub.add_parser("verify"); sub.add_parser("classify-risk"); p = sub.add_parser("end"); p.add_argument("--outcome", choices=("goal_met", "escalated", "stuck"), required=True)
    args = parser.parse_args(raw_args)
    actions = {"doctor": doctor, "begin": begin, "spawn": spawn, "send": send, "wait": wait, "fallback": fallback, "ledger": ledger, "verify": verify, "classify-risk": classify_risk_command, "end": end}
    if args.command == "state": output(load())
    elif args.command == "round": end_counter(args, "round")
    elif args.command == "turn": end_counter(args, "turn")
    elif args.command == "read": print(invoke("mux", "crew_read", [role(load(), args.role)["id"]]), end="")
    elif args.command == "close": invoke("mux", "crew_close", [role(load(), args.role)["id"]])
    else: actions[args.command](args)
def safe_main():
    try: main()
    except CrewError as exc: print(f"crew: {exc}", file=sys.stderr); sys.exit(1)

if __name__ == "__main__":
    safe_main()
