"""The PreToolUse safety guard (architecture §8, layer 3).

Claude Code runs ``factory.py guard`` before every Bash, PowerShell and file-writing tool
call. ``decide()`` is a pure function: given the tool call and a ``GuardContext``, it
returns allow or block. It enforces rules that must never depend on the model behaving:

* **No merge path, ever** (D1/S1): ``gh pr merge``, REST ``…/pulls/N/merge`` and
  ``…/merges``, GraphQL ``mergePullRequest`` / ``enablePullRequestAutoMerge`` / ``mergeBranch``,
  and API calls that move the default branch.
* **No push to the default branch**, in any refspec spelling, and no force-push to a
  branch that is already under review (S4).
* **No direct GitHub comments or reviews** (``gh pr|issue comment``, ``gh pr review``):
  comments must go through ``factory.py comment`` so they carry a marker (S14).
* **No repo-settings, secrets or branch-protection changes** (S5).
* **File writes**: with an active target, the factory repo is read-only except
  ``.factory-local/`` (S3), and nothing may be written outside the target, the temp/scratch
  directory and Claude's project memory (S12). Without a target (developing the factory),
  writes are limited to the factory repo, scratch and memory.

Commands are taken apart by small bash and PowerShell tokenizers, so chained commands
(``&&``, ``;``, ``|``), ``bash -c``/``pwsh -Command``/``eval``, env-var prefixes,
heredocs and ``$(…)`` substitutions are all inspected. Where a command cannot be
inspected (for example ``-EncodedCommand``, an executable name built at run time, or
code piped into ``iex``, a shell or an interpreter), the guard blocks it and says why.

PowerShell statements that start with a variable are expressions (``if ($?)``) or
assignments (``$T = "C:\\path"``), not command calls: an assignment's right-hand side is
checked as the command it is, and a quoted value is substituted wherever the variable is
used later in the same script, so ``git -C $T push`` is checked against the right repo.
The write cmdlets' named parameters (``-Encoding utf8``, ``-Value x``) are told apart
from the file they write to.
"""

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

# ----------------------------------------------------------------------------- results


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""


ALLOW = Decision(True)


class Blocked(Exception):
    """Raised internally to stop at the first blocked (sub)command."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _block(reason: str) -> None:
    raise Blocked(reason)


# ----------------------------------------------------------------------------- context


@dataclass
class GuardContext:
    factory_root: Path
    target_root: Path | None
    cwd: Path
    default_branch: str = "main"
    scratch_dirs: tuple[Path, ...] = ()
    extra_write_dirs: tuple[Path, ...] = ()  # e.g. ~/.claude/projects (Claude's memory)
    # I/O is injected, so decide() stays pure and testable.
    current_branch: Callable[[Path], str | None] = field(default=lambda repo_dir: None)
    is_reviewed: Callable[[str, Path], bool | None] = field(default=lambda branch, d: None)

    @property
    def protected_branches(self) -> frozenset[str]:
        return frozenset({self.default_branch.lower(), "main", "master"})


# ----------------------------------------------------------------------------- entry


SHELL_TOOLS = {"Bash": "bash", "PowerShell": "powershell"}
WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path",
               "NotebookEdit": "notebook_path"}


def decide(tool_name: str, tool_input: dict, ctx: GuardContext) -> Decision:
    try:
        if tool_name in SHELL_TOOLS:
            command = tool_input.get("command")
            if not isinstance(command, str):
                return ALLOW
            _check_script(command, SHELL_TOOLS[tool_name], ctx, ctx.cwd, depth=0)
        elif tool_name in WRITE_TOOLS:
            path = tool_input.get(WRITE_TOOLS[tool_name])
            if isinstance(path, str) and path:
                _check_write_path(path, ctx, ctx.cwd)
        return ALLOW
    except Blocked as blocked:
        return Decision(False, blocked.reason)


# ----------------------------------------------------------------------------- tokenizing

_SEP = "sep"
_WORD = "word"
_REDIR_OUT = "redir_out"
_REDIR_IN = "redir_in"
_DYNAMIC = "\x00"  # marks a word that contains a run-time substitution
_QUOTE = "\x01"  # marks where a quoted part of a word begins; _parse removes it


@dataclass
class _Command:
    words: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)       # output-redirect targets
    heredocs: list[str] = field(default_factory=list)     # bodies fed to this command
    after: str = ""  # the separator before it: "|" when piped into, "&" after a call operator
    raw: list[str] = field(default_factory=list)  # the words with their _QUOTE marks


@dataclass
class _Parsed:
    commands: list[_Command]
    substitutions: list[str]  # $(...) / `...` / <(...) contents, to be checked too


_HEREDOC_START = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def _extract_heredocs(text: str) -> tuple[str, list[str]]:
    """Remove bash heredoc bodies; leave a placeholder token where each started."""
    lines = text.split("\n")
    out: list[str] = []
    bodies: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        pending: list[tuple[str, bool]] = []
        rebuilt, last = [], 0
        for match in _HEREDOC_START.finditer(line):
            if match.start() > 0 and line[match.start() - 1] == "<":  # '<<<' here-string
                continue
            pending.append((match.group(3), match.group(1) == "-"))
            rebuilt.append(line[last:match.start()])
            rebuilt.append(f" __HEREDOC_{len(bodies) + len(pending) - 1}__ ")
            last = match.end()
        rebuilt.append(line[last:])
        out.append("".join(rebuilt))
        i += 1
        for delimiter, strip_tabs in pending:
            body: list[str] = []
            while i < len(lines):
                candidate = lines[i].lstrip("\t") if strip_tabs else lines[i]
                i += 1
                if candidate.rstrip("\r") == delimiter:
                    break
                body.append(lines[i - 1])
            bodies.append("\n".join(body))
    return "\n".join(out), bodies


def _read_balanced(text: str, i: int, open_ch: str = "(", close_ch: str = ")") -> tuple[str, int]:
    """``text[i]`` is just after an opening bracket; return (inner, index after close)."""
    depth, start = 1, i
    quote = None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"':
                i += 1
        elif ch in "'\"":
            quote = ch
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    return text[start:], len(text)


def _tokenize(text: str, dialect: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Tokens for bash (``dialect='bash'``) or PowerShell/cmd (``'powershell'``)."""
    tokens: list[tuple[str, str]] = []
    subs: list[str] = []
    word: list[str] = []
    in_word = False
    escape = "\\" if dialect == "bash" else "`"
    i, n = 0, len(text)

    def flush():
        nonlocal word, in_word
        if in_word:
            tokens.append((_WORD, "".join(word)))
        word, in_word = [], False

    def add(s: str):
        nonlocal in_word
        word.append(s)
        in_word = True

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch in " \t\r":
            flush()
            i += 1
        elif ch == "\n":
            flush()
            tokens.append((_SEP, "\n"))
            i += 1
        elif ch == "#" and not in_word:
            if dialect == "powershell" and nxt == "<":  # <# block comment #>
                end = text.find("#>", i + 2)
                i = n if end < 0 else end + 2
            else:
                while i < n and text[i] != "\n":
                    i += 1
        elif ch == escape:
            if nxt == "\n":
                i += 2
            elif nxt:
                add(nxt)
                i += 2
            else:
                i += 1
        elif ch == "@" and dialect == "powershell" and nxt in "'\"" and \
                text[i + 2:i + 3] in ("\n", "\r"):
            closer = "\n" + nxt + "@"
            end = text.find(closer, i + 2)
            end = n if end < 0 else end
            add(_QUOTE + text[i + 2:end].lstrip("\r\n"))
            i = n if end >= n else end + len(closer)
        elif ch == "'":
            end = text.find("'", i + 1)
            if dialect == "powershell":
                while end >= 0 and text[end + 1:end + 2] == "'":  # '' escape
                    end = text.find("'", end + 2)
            end = n if end < 0 else end
            add(_QUOTE + (text[i + 1:end].replace("''", "'") if dialect == "powershell"
                          else text[i + 1:end]))
            i = end + 1
        elif ch == '"':
            i += 1
            add(_QUOTE)
            while i < n and text[i] != '"':
                c = text[i]
                if c == escape and i + 1 < n:
                    add(text[i + 1] if text[i + 1] in '"$`\\\n' or dialect == "powershell"
                        else c + text[i + 1])
                    i += 2
                elif c == "$" and text[i + 1:i + 2] == "(":
                    inner, i = _read_balanced(text, i + 2)
                    subs.append(inner)
                    add(_DYNAMIC)
                elif c == "`" and dialect == "bash":
                    end = text.find("`", i + 1)
                    end = n if end < 0 else end
                    subs.append(text[i + 1:end])
                    add(_DYNAMIC)
                    i = end + 1
                else:
                    add(c)
                    i += 1
            i += 1
        elif ch == "$" and nxt == "(":
            inner, i = _read_balanced(text, i + 2)
            subs.append(inner)
            add(_DYNAMIC)
        elif ch == "`" and dialect == "bash":
            end = text.find("`", i + 1)
            end = n if end < 0 else end
            subs.append(text[i + 1:end])
            add(_DYNAMIC)
            i = end + 1
        elif ch in "<>" and nxt == "(" and dialect == "bash":  # process substitution
            inner, i = _read_balanced(text, i + 2)
            subs.append(inner)
            add(_DYNAMIC)
        elif ch in ";|&(){}" or (ch == "&" and dialect == "powershell"):
            if ch == "&" and nxt == ">":  # bash &> file
                flush()
                tokens.append((_REDIR_OUT, "&>"))
                i += 2
                if text[i:i + 1] == ">":
                    i += 1
                continue
            if ch == "&" and dialect == "powershell" and nxt != "&":
                flush()  # call operator: `& "gh.exe" pr merge`
                tokens.append((_SEP, "&"))
                i += 1
                continue
            if ch in "{}" and dialect == "bash" and in_word:
                add(ch)  # e.g. ${VAR} or a{b,c}
                i += 1
                continue
            flush()
            op = ch + nxt if nxt == ch or (ch == "|" and nxt == "&") else ch
            tokens.append((_SEP, op))
            i += len(op)
        elif ch == ">" or (ch == "<" and dialect == "bash"):
            fd = "".join(word) if in_word else ""
            if in_word and not re.fullmatch(r"\d|\*", fd):
                flush()
            else:
                word, in_word = [], False
            op = ch
            i += 1
            while i < n and text[i] in "<>|":
                op += text[i]
                i += 1
            if text[i:i + 1] == "&":  # 2>&1, >&2 : fd duplication, not a file
                i += 1
                while i < n and (text[i].isdigit() or text[i] == "-"):
                    i += 1
                continue
            tokens.append((_REDIR_OUT if ch == ">" else _REDIR_IN, op))
        else:
            add(ch)
            i += 1
    flush()
    return tokens, subs


def _parse(text: str, dialect: str) -> _Parsed:
    bodies: list[str] = []
    if dialect == "bash":
        text, bodies = _extract_heredocs(text)
    tokens, subs = _tokenize(text, dialect)
    commands: list[_Command] = []
    current = _Command()
    expect: str | None = None
    for kind, value in tokens:
        if kind == _SEP:
            if current.words or current.writes:
                commands.append(current)
            current, expect = _Command(after=value), None
        elif kind in (_REDIR_OUT, _REDIR_IN):
            expect = kind
        elif expect == _REDIR_OUT:
            current.writes.append(value.replace(_QUOTE, ""))
            expect = None
        elif expect == _REDIR_IN:
            expect = None
        else:
            match = re.fullmatch(r"__HEREDOC_(\d+)__", value)
            if match and int(match[1]) < len(bodies):
                current.heredocs.append(bodies[int(match[1])])
            else:
                current.words.append(value.replace(_QUOTE, ""))
                current.raw.append(value)
    if current.words or current.writes:
        commands.append(current)
    return _Parsed(commands, subs)


# ----------------------------------------------------------------------------- commands

_MAX_DEPTH = 8
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "git-bash"}
_POWERSHELLS = {"powershell", "pwsh"}
_INTERPRETERS = {"python", "python3", "py", "node", "deno", "bun", "ruby", "perl", "php"}
_HTTP_CLIENTS = {"curl", "wget", "http", "https", "invoke-webrequest", "invoke-restmethod",
                 "iwr", "irm"}
_WRAPPERS = {"command", "builtin", "exec", "nohup", "time", "sudo", "doas", "winpty",
             "stdbuf"}
_NULL_TARGETS = {"/dev/null", "/dev/stdout", "/dev/stderr", "nul", "$null", "con", "-"}


def _exe_name(word: str) -> str:
    base = re.split(r"[\\/]", word)[-1].lower()
    return re.sub(r"\.(exe|cmd|bat|ps1)$", "", base)


def _check_script(text: str, dialect: str, ctx: GuardContext, cwd: Path, depth: int) -> Path:
    """Check every command in ``text``. Returns the working directory after ``cd``s."""
    if depth > _MAX_DEPTH:
        _block("command nesting is too deep for the guard to inspect")
    parsed = _parse(text, dialect)
    for inner in parsed.substitutions:
        _check_script(inner, dialect, ctx, cwd, depth + 1)
    variables: dict[str, str | None] = {}  # PowerShell: assigned in this script
    for command in parsed.commands:
        cwd = _check_command(command, dialect, ctx, cwd, depth, variables)
    return cwd


def _strip_wrappers(words: list[str]) -> list[str]:
    i = 0
    while i < len(words):
        w, name = words[i], _exe_name(words[i])
        if _ASSIGNMENT.match(w):
            i += 1
        elif name == "env":
            i += 1
            while i < len(words) and (words[i].startswith("-") or _ASSIGNMENT.match(words[i])):
                i += 2 if words[i] in ("-u", "--unset", "-C", "--chdir") else 1
        elif name in _WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 1
        elif name == "nice":
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] == "-n" else 1
        elif name == "timeout":
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in ("-s", "--signal", "-k", "--kill-after") else 1
            i += 1  # the duration
        elif name == "xargs":
            i += 1
            while i < len(words) and words[i].startswith("-"):
                has_value = words[i] in ("-I", "-n", "-P", "-L", "-d", "-s", "-E", "-a")
                i += 2 if has_value else 1
        else:
            break
    return words[i:]


def _check_command(cmd: _Command, dialect: str, ctx: GuardContext, cwd: Path,
                   depth: int, variables: dict[str, str | None] | None = None) -> Path:
    variables = {} if variables is None else variables
    words, writes = cmd.words, cmd.writes
    if dialect == "powershell":
        assignment = _pwsh_assignment(cmd.raw or words)
        if assignment is not None:  # `$x = <pipeline>`: the right-hand side runs
            name, rhs_raw = assignment
            rhs = _pwsh_substitute([w.replace(_QUOTE, "") for w in rhs_raw], variables)
            for target in _pwsh_substitute(writes, variables):
                _check_redirect_target(target, ctx, cwd)
            # Only a quoted string is a known value: `$x = gh …` or `$x = Get-Thing` runs a
            # command, and `$x = 5` or `$x = "…$(…)"` is not worth tracking.
            literal = len(rhs_raw) == 1 and rhs_raw[0].startswith(_QUOTE) \
                and _DYNAMIC not in rhs[0] and not _PWSH_VAR.search(rhs[0])
            if rhs and not literal:
                cwd = _check_command(_Command(rhs, [], cmd.heredocs, "=", rhs_raw), dialect,
                                     ctx, cwd, depth, variables)
            if name not in _PWSH_AUTOMATIC:  # `$null = …` discards; `$null` stays $null
                variables[name] = rhs[0] if literal else None  # None: computed at run time
            return cwd
        words, writes = _pwsh_substitute(words, variables), _pwsh_substitute(writes, variables)
    for target in writes:
        _check_redirect_target(target, ctx, cwd)
    words = _strip_wrappers(words)
    if not words:
        return cwd
    exe = words[0]
    if _DYNAMIC in exe or (exe.startswith("$") and not exe.startswith("$null")):
        if _pwsh_expression(exe, cmd, dialect, depth):
            return cwd  # e.g. `if ($?)` or `$LASTEXITCODE -ne 0`: it runs no command
        _block(f"the command name {exe.replace(_DYNAMIC, '$(...)')!r} is computed at run "
               "time, so the guard cannot check it; run the command directly")
    name = _exe_name(exe)
    args = [w.replace(_DYNAMIC, "") for w in words[1:]]

    if cmd.after in ("|", "|&") and not cmd.heredocs and _runs_piped_code(name, args):
        _block(f"`{name}` would run code piped into it, which the guard cannot inspect; "
               "pass the code as an argument or a heredoc instead")

    if name in ("cd", "pushd", "set-location", "sl", "chdir"):
        dest = next((a for a in args if not a.startswith("-")), None)
        return _resolve(dest, cwd) if dest else cwd

    # Shells and eval: inspect the inner script.
    if name in _SHELLS:
        script = _flag_value(args, lambda a: re.fullmatch(r"-[a-z]*c[a-z]*", a) is not None)
        if script is not None:
            _check_script(script, "bash", ctx, cwd, depth + 1)
        for body in cmd.heredocs:
            _check_script(body, "bash", ctx, cwd, depth + 1)
        return cwd
    if name in _POWERSHELLS or name == "cmd":
        lowered = [a.lower() for a in args]
        if any(a in ("-encodedcommand", "-enc", "-ec", "-e") or a.startswith("-encodedc")
               for a in lowered):
            _block("encoded PowerShell commands cannot be inspected by the guard")
        for flag in ("-command", "-c", "/c", "/k"):
            if flag in lowered:
                script = " ".join(args[lowered.index(flag) + 1:])
                _check_script(script, "powershell", ctx, cwd, depth + 1)
                break
        for body in cmd.heredocs:
            _check_script(body, "powershell", ctx, cwd, depth + 1)
        return cwd
    if name == "eval":
        _check_script(" ".join(args), "bash", ctx, cwd, depth + 1)
        return cwd
    if name in ("invoke-expression", "iex"):
        _check_script(" ".join(args), "powershell", ctx, cwd, depth + 1)
        return cwd
    if name in ("start-process", "saps", "start"):
        rest = [a for a in args if a.lower() not in (
            "-filepath", "-argumentlist", "-wait", "-nonewwindow", "-passthru", "-verb",
            "-windowstyle", "-workingdirectory")]
        _check_script(" ".join(rest), "powershell", ctx, cwd, depth + 1)
        return cwd

    if name == "git":
        _check_git(args, ctx, cwd)
    elif name == "gh":
        _check_gh(args, cmd.heredocs)
    elif name in _HTTP_CLIENTS:
        _check_http(args)
    elif name in _INTERPRETERS:
        for text in _interpreter_code(args, cmd.heredocs):
            _scan_code(text)
    elif name in ("tee", "tee-object", "out-file", "set-content", "add-content"):
        for target in _write_command_targets(name, args):
            _check_redirect_target(target, ctx, cwd)
    return cwd


# ----------------------------------------------------------------------------- PowerShell
# In PowerShell a statement that starts with a variable is an expression or an assignment,
# never a command call (that needs `&` or a bare command name). A value assigned in the
# same script is substituted wherever the variable is used later, so a variable cannot
# hide a merge or a push from the guard; a value computed by a command is treated like a
# `$(...)` substitution.

_PWSH_VAR = re.compile(r"\$(?:\{(?P<braced>[^}]+)\}|(?P<name>[A-Za-z_]\w*(?::[A-Za-z_]\w*)?))")
_PWSH_PLAIN = re.compile(r"\$(?:[?^$]|\{[^}]+\}|[A-Za-z_]\w*(?::[A-Za-z_]\w*)?)")
_PWSH_ASSIGN_OPS = ("??=", "+=", "-=", "*=", "/=", "%=", "=")
_PWSH_AUTOMATIC = frozenset({"null", "true", "false", "_", "psitem", "this", "input", "args"})


def _pwsh_var_key(match: re.Match) -> str:
    return (match["braced"] or match["name"]).lower()


def _pwsh_assignment(words: list[str]) -> tuple[str, list[str]] | None:
    """``(variable, right-hand side words)`` for ``$x = …`` (in any spacing), else None."""
    match = _PWSH_VAR.match(words[0]) if words else None
    if match is None:
        return None
    rest, tail = words[0][match.end():], words[1:]
    if not rest and tail:
        rest, tail = tail[0], tail[1:]
    op = next((o for o in _PWSH_ASSIGN_OPS if rest.startswith(o)), None)
    if op is None or rest.startswith("=="):
        return None
    value = rest[len(op):]
    return _pwsh_var_key(match), ([value] if value else []) + tail


def _pwsh_substitute(words: list[str], variables: dict[str, str | None]) -> list[str]:
    """Replace the variables assigned earlier in this script: a literal by its value, a
    computed one by the run-time marker. Other variables (``$?``, ``$env:X``) stay."""
    if not variables:
        return words

    def value(match: re.Match) -> str:
        key = _pwsh_var_key(match)
        if key not in variables:
            return match[0]
        known = variables[key]
        return _DYNAMIC if known is None else known

    return [_PWSH_VAR.sub(value, w) for w in words]


def _pwsh_expression(exe: str, cmd: _Command, dialect: str, depth: int) -> bool:
    """True for a top-level PowerShell statement that only evaluates a variable, such as
    ``$?`` or ``$LASTEXITCODE -ne 0``. Not after the call operator ``&`` (which runs it),
    not with member access (``$x.Invoke()``), and not inside a nested script, whose text
    may itself have been computed at run time."""
    return (dialect == "powershell" and depth == 0 and cmd.after != "&"
            and _DYNAMIC not in exe and _PWSH_PLAIN.fullmatch(exe) is not None)


def _runs_piped_code(name: str, args: list[str]) -> bool:
    """True if the command would execute what is piped into it, which the guard cannot
    see (e.g. ``… | iex``, ``… | bash``, ``… | python``, ``… | gh api graphql --input -``)."""
    lowered = [a.lower() for a in args]
    if name in ("invoke-expression", "iex"):
        return not args
    if name in _SHELLS:
        if any(re.fullmatch(r"-[a-z]*c[a-z]*", a) for a in args):
            return False
        return "-s" in args or not any(not a.startswith("-") for a in args)
    if name in _POWERSHELLS or name == "cmd":
        for flag in ("-command", "-c", "-file", "-f", "/c", "/k"):
            if flag in lowered:
                index = lowered.index(flag)
                return index + 1 >= len(args) or args[index + 1] == "-"
        return not any(not a.startswith(("-", "/")) for a in args)
    if name in _INTERPRETERS:
        for a in args:
            if a in ("-c", "-e", "--eval", "-p", "--print", "-r", "-m"):
                return False
            if a == "-" or not a.startswith("-"):
                return a == "-"
        return True
    if name == "gh" and "--input" in args:
        index = args.index("--input")
        return index + 1 < len(args) and args[index + 1] == "-"
    return False


def _interpreter_code(args: list[str], heredocs: list[str]) -> list[str]:
    """The inline code an interpreter will run: ``-c``/``-e`` values, and heredocs when
    the script itself is read from stdin. Arguments to a script *file* are data."""
    code: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-c", "-e", "--eval", "-p", "--print", "-r") and i + 1 < len(args):
            code.append(args[i + 1])
            return code  # everything after the inline code is argv for it
        if a == "-m":
            return code  # running a module: its arguments are data
        if a == "-" or not a.startswith("-"):
            if a == "-":
                code.extend(heredocs)
            return code  # a script file (or stdin script) was named
        i += 1
    code.extend(heredocs)  # no script named: the interpreter reads its code from stdin
    return code


def _flag_value(args: list[str], is_flag: Callable[[str], bool]) -> str | None:
    for index, arg in enumerate(args):
        if is_flag(arg) and index + 1 < len(args):
            return args[index + 1]
    return None


# ----------------------------------------------------------------------------- git

_GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                   "--super-prefix", "--config-env"}
_DANGEROUS_CONFIG = re.compile(
    r"^(alias\..+|remote\..+\.push|branch\..+\.merge|push\.default)$", re.IGNORECASE)


def _check_git(args: list[str], ctx: GuardContext, cwd: Path) -> None:
    repo_dir = cwd
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            repo_dir = _resolve(args[i + 1], repo_dir)
            i += 2
        elif a == "-c" and i + 1 < len(args):
            key = args[i + 1].split("=", 1)[0]
            if _DANGEROUS_CONFIG.match(key):
                _block(f"`git -c {key}=…` could redirect pushes or define aliases the guard "
                       "cannot see (rules S1, S4)")
            i += 2
        elif a in _GIT_VALUE_OPTS:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            break
    if i >= len(args):
        return
    sub, rest = args[i], args[i + 1:]
    if sub == "push":
        _check_push(rest, ctx, repo_dir)
    elif sub in ("send-pack", "http-push"):
        _block(f"`git {sub}` bypasses the push checks; use `git push` (rule S1)")
    elif sub == "config":
        reading = any(a in ("--get", "--get-all", "--get-regexp", "--list", "-l",
                            "--show-origin", "get", "list") for a in rest)
        for a in rest:
            if _DANGEROUS_CONFIG.match(a.split("=", 1)[0]) and not reading:
                _block(f"setting git config {a!r} could redirect pushes or define aliases "
                       "the guard cannot see (rules S1, S4)")


_PUSH_VALUE_OPTS = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}


def _check_push(args: list[str], ctx: GuardContext, repo_dir: Path) -> None:
    force = delete = False
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in _PUSH_VALUE_OPTS:
            i += 2
            continue
        if a.startswith("--"):
            opt = a.split("=", 1)[0]
            if opt in ("--force", "--force-with-lease", "--force-if-includes"):
                force = True
            elif opt in ("--mirror", "--all", "--branches", "--prune"):
                _block(f"`git push {opt}` can overwrite or delete the default branch (rule S1)")
            elif opt == "--delete":
                delete = True
            elif opt in ("--dry-run",):
                return
        elif a.startswith("-") and len(a) > 1:
            letters = a[1:]
            force |= "f" in letters
            delete |= "d" in letters
            if "n" in letters:
                return  # dry run
            if letters.endswith("o"):
                i += 1  # -o <option>
        else:
            positional.append(a)
        i += 1

    refspecs = positional[1:]
    targets: list[tuple[str, bool, bool]] = []  # (destination branch, forced, deleting)
    if not refspecs:
        branch = ctx.current_branch(repo_dir)
        if not branch:
            _block("could not determine which branch `git push` would push; "
                   "name the branch explicitly, e.g. `git push origin story/12-x`")
        targets.append((branch, force, False))
    for spec in refspecs:
        forced = force or spec.startswith("+")
        spec = spec.lstrip("+")
        src, _, dst = spec.partition(":") if ":" in spec else (spec, "", spec)
        deleting = delete or (":" in spec and src == "")
        dst = dst or src
        if dst in ("HEAD", "@") or (not dst and not delete):
            dst = ctx.current_branch(repo_dir) or ""
            if not dst:
                _block("could not determine the branch behind HEAD; name it explicitly")
        if "*" in dst:
            _block(f"wildcard refspec {spec!r} could include the default branch (rule S1)")
        if dst.startswith("refs/"):
            if not dst.startswith("refs/heads/"):
                continue  # tags and other refs are not branches
            dst = dst[len("refs/heads/"):]
        targets.append((dst, forced, deleting))

    for branch, forced, deleting in targets:
        if branch.lower() in ctx.protected_branches:
            action = "delete" if deleting else "push to"
            _block(f"the factory must never {action} the default branch {branch!r}; "
                   "changes reach it only when the human merges a PR (rules S1, D1)")
        if forced:
            reviewed = ctx.is_reviewed(branch, repo_dir)
            if reviewed is None:
                _block(f"force-push to {branch!r} refused: could not confirm the branch has "
                       "no PR under review (rule S4)")
            if reviewed:
                _block(f"force-push to {branch!r} refused: it already has a PR under review. "
                       "Push new commits instead (rule S4)")


# ----------------------------------------------------------------------------- gh

_GH_VALUE_FLAGS = {
    "-R", "--repo", "-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field",
    "--input", "-q", "--jq", "-t", "--template", "--title", "-b", "--body", "--body-file",
    "-B", "--base", "--head", "-l", "--label", "-a", "--assignee", "-m", "--milestone",
    "-A", "--author", "-L", "--limit", "-s", "--state", "-S", "--search", "--json",
    "-r", "--reviewer", "-p", "--project", "-T", "-w", "--web-url",
    "--hostname", "-e", "--env", "--cache",
}
_MERGE_MUTATIONS = re.compile(
    r"\b(mergePullRequest|enablePullRequestAutoMerge|mergeBranch)\b")
_WRITE_MUTATIONS = re.compile(
    r"\b(addPullRequestReview|submitPullRequestReview|addPullRequestReviewComment|"
    r"addPullRequestReviewThread|addComment|updateIssueComment|updateRef|deleteRef|"
    r"createCommitOnBranch|updateRefs|updateRepository|deleteRepository|"
    r"createBranchProtectionRule|updateBranchProtectionRule|deleteBranchProtectionRule|"
    r"createRepositoryRuleset|updateRepositoryRuleset|deleteRepositoryRuleset)\b")
_REST_MERGE = re.compile(
    r"(?:^|/)repos/[^/\s]+/[^/\s]+/(?:pulls/[^/\s]+/merge|merges)/?(?:$|[?#\s\"'])")


def _gh_positionals(args: list[str]) -> list[str]:
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a in _GH_VALUE_FLAGS:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            out.append(a)
            i += 1
    return out


def _check_gh(args: list[str], heredocs: list[str]) -> None:
    pos = _gh_positionals(args)
    if not pos:
        return
    group, rest = pos[0], pos[1:]
    if group == "pr":
        for verb, rule in (("merge", "the human merges (D1, rule S1)"),
                           ("review", "reviews are the human's decision (D5)"),
                           ("comment", "post comments with `python scripts/factory.py comment` "
                                       "so they carry a factory marker (rule S14)")):
            if verb in rest:
                _block(f"`gh pr {verb}` is not allowed: {rule}")
    elif group == "issue" and "comment" in rest:
        _block("`gh issue comment` is not allowed: post comments with "
               "`python scripts/factory.py comment` so they carry a marker (rule S14)")
    elif group == "alias":
        _block("`gh alias` is not allowed: aliases could hide a merge from the guard")
    elif group == "extension" and rest[:1] in (["install"], ["exec"], ["upgrade"]):
        _block("installing or running gh extensions is not allowed")
    elif group == "repo" and rest[:1] in (["edit"], ["delete"], ["rename"], ["archive"],
                                          ["unarchive"], ["sync"]):
        _block(f"`gh repo {rest[0]}` changes the repository, which is not allowed (rule S5)")
    elif group == "secret" or (group == "variable" and rest[:1] in (["set"], ["delete"])):
        _block(f"`gh {group}` is not allowed: secrets and settings are off-limits (rule S5)")
    elif group == "api":
        _check_gh_api(args, rest, heredocs)


def _check_gh_api(args: list[str], rest: list[str], heredocs: list[str]) -> None:
    endpoint = (rest[0] if rest else "").strip()
    method = None
    texts: list[str] = [endpoint, *heredocs]
    has_fields = False
    input_file = None
    i = 0
    while i < len(args):
        a = args[i]
        value = args[i + 1] if i + 1 < len(args) else ""
        if a in ("-X", "--method"):
            method = value.upper()
            i += 2
        elif a.startswith("--method=") or (a.startswith("-X") and len(a) > 2):
            method = a.split("=", 1)[-1].removeprefix("-X").upper()
            i += 1
        elif a in ("-f", "-F", "--field", "--raw-field"):
            texts.append(value)
            has_fields = True
            i += 2
        elif a == "--input":
            input_file = value
            i += 2
        else:
            i += 1
    method = method or ("POST" if has_fields or input_file else "GET")
    path = endpoint.split("?", 1)[0].lstrip("/")
    path = re.sub(r"^https?://api\.github\.com/", "", path)

    if endpoint.lower() == "graphql" or path.lower() == "graphql":
        if input_file not in (None, "-"):
            _block("`gh api graphql --input <file>` cannot be inspected by the guard")
    for text in texts:
        _scan_code(text)
    if method == "DELETE":
        _block("`gh api` DELETE calls are not allowed")
    _check_rest_write(path, method, texts)


def _check_rest_write(path: str, method: str, texts: list[str]) -> None:
    """Block REST writes that would merge, review, comment, or change settings/branches."""
    if _REST_MERGE.search("/" + path + " "):
        _block("merging through the REST API is not allowed; the human merges (D1, rule S1)")
    if method == "GET":
        return
    repo = r"repos/[^/]+/[^/]+"
    rules = [
        (rf"^{repo}/?$", "changing repository settings is not allowed (rule S5)"),
        (rf"^{repo}/(branches/.+/protection|rulesets)", "branch protection and rulesets are "
                                                       "off-limits (rule S5)"),
        (rf"^{repo}/(actions/(secrets|variables)|environments/|dependabot/secrets)",
         "secrets and variables are off-limits (rule S5)"),
        (rf"^{repo}/(issues|pulls)/[^/]+/comments|^{repo}/(issues|pulls)/comments/",
         "post comments with `python scripts/factory.py comment` (rule S14)"),
        (rf"^{repo}/pulls/[^/]+/reviews", "reviews are the human's decision (D5)"),
        (rf"^{repo}/contents/", "writing files through the API bypasses branches and review"),
        (rf"^{repo}/git/(refs|ref)(/|$)", "moving branches through the API bypasses the push "
                                         "checks (rule S1)"),
    ]
    for pattern, reason in rules:
        if re.search(pattern, path, re.IGNORECASE):
            _block(f"`{method} {path}`: {reason}")


# ----------------------------------------------------------------------------- http / code


def _check_http(args: list[str]) -> None:
    text = " ".join(args)
    _scan_code(text)
    for match in re.finditer(r"https?://api\.github\.com/(\S+)", text):
        path = match.group(1).rstrip("'\"")
        lowered = [a.lower() for a in args]
        method = "GET"
        for flag in ("-x", "--request", "-method"):
            if flag in lowered:
                method = args[lowered.index(flag) + 1].upper()
        if any(a in ("-d", "--data", "--data-raw", "--data-binary", "--json", "-f",
                     "--form", "-body") or a.startswith("--data") for a in lowered) \
                and method == "GET":
            method = "POST"
        if method != "GET":
            _block(f"write calls to the GitHub API through {args[0] if args else 'HTTP'} are "
                   "not allowed; the factory uses gh and factory.py")
        _check_rest_write(path.split("?", 1)[0], method, [])


def _scan_code(text: str) -> None:
    """Scan script/API text for merge paths (used for interpreters, gh api and HTTP)."""
    if _MERGE_MUTATIONS.search(text):
        _block("GraphQL merge mutations are not allowed; the human merges (D1, rule S1)")
    if _WRITE_MUTATIONS.search(text) and re.search(r"\bmutation\b", text):
        _block("this GraphQL mutation would review, comment, move branches or change settings;"
               " not allowed (rules S1, S5, S14)")
    if _REST_MERGE.search(text):
        _block("merging through the REST API is not allowed; the human merges (D1, rule S1)")
    if re.search(r"\bgh\b[\s'\",\]\[]+pr[\s'\",\]\[]+merge\b", text):
        _block("this script runs `gh pr merge`; the human merges (D1, rule S1)")
    if re.search(r"\bgit\b[\s'\",\]\[]+push\b[^\n]*[\s'\":/]+(main|master)\b", text):
        _block("this script appears to push to the default branch (rule S1)")


# ----------------------------------------------------------------------------- paths


# Parameters of Out-File, Set-Content, Add-Content and Tee-Object (and the common ones):
# the ones naming the file, the ones that take a value (e.g. `-Encoding utf8`), and the
# switches. PowerShell accepts any unambiguous prefix (`-Enc`) and `-Name:value`.
_PS_PATH_PARAMS = ("filepath", "literalpath", "path", "pspath", "lp")
_PS_VALUE_PARAMS = (
    "encoding", "width", "inputobject", "value", "filter", "include", "exclude",
    "credential", "stream", "variable", "erroraction", "warningaction", "informationaction",
    "progressaction", "errorvariable", "warningvariable", "informationvariable",
    "outvariable", "outbuffer", "pipelinevariable")
_PS_SWITCH_PARAMS = ("append", "force", "noclobber", "nonewline", "passthru", "asbytestream",
                     "whatif", "confirm", "verbose", "debug")


def _ps_param_kind(name: str) -> str | None:
    """"path", "value" or "switch" for a parameter name or unambiguous prefix; else None."""
    kinds = {p: "path" for p in _PS_PATH_PARAMS} | {p: "value" for p in _PS_VALUE_PARAMS} \
        | {p: "switch" for p in _PS_SWITCH_PARAMS}
    if name in kinds:
        return kinds[name]
    matches = {kind for param, kind in kinds.items() if param.startswith(name)}
    return matches.pop() if name and len(matches) == 1 else None


def _write_command_targets(name: str, args: list[str]) -> list[str]:
    # Out-File / Set-Content / Add-Content / Tee-Object: the file is the -Path-like
    # parameter or the first positional argument. After a parameter the guard does not
    # know, every positional argument might be the file, so all are checked. `tee` (bash,
    # or PowerShell's alias of Tee-Object) writes to every positional argument.
    targets: list[str] = []
    positional: list[str] = []
    unknown = False
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-") and len(a) > 1:
            param, colon, inline = a[1:].partition(":")
            kind = _ps_param_kind(param.lower())
            takes_value = kind in ("path", "value") and not colon
            if kind == "path":
                targets.append(inline if colon else (args[i + 1] if i + 1 < len(args) else ""))
            elif kind is None:
                unknown = True
            i += 2 if takes_value else 1
            continue
        positional.append(a)
        i += 1
    if name == "tee":
        return targets + positional
    if not targets:
        targets = positional if unknown else positional[:1]
    return targets


def _check_redirect_target(target: str, ctx: GuardContext, cwd: Path) -> None:
    if target.lower() in _NULL_TARGETS or target.startswith("&"):
        return
    _check_write_path(target, ctx, cwd)


def _normalize(path: str, cwd: Path) -> str:
    expanded = os.path.expandvars(os.path.expanduser(path.replace(_DYNAMIC, "")))
    if "$" in expanded or "%" in expanded or _DYNAMIC in path:
        _block(f"cannot tell where {path!r} points (unexpanded variable or substitution); "
               "use a literal path")
    match = re.match(r"^/([a-zA-Z])(/|$)", expanded)  # Git Bash /c/Users → C:/Users
    if match and os.name == "nt":
        expanded = f"{match[1]}:/{expanded[3:]}"
    candidate = Path(expanded)
    if not candidate.is_absolute() and not PureWindowsPath(expanded).is_absolute():
        candidate = cwd / candidate
    return os.path.normcase(os.path.abspath(candidate))


def _resolve(path: str, cwd: Path) -> Path:
    try:
        return Path(_normalize(path, cwd))
    except Blocked:
        return cwd


def _within(path: str, root: Path | None) -> bool:
    if root is None:
        return False
    base = os.path.normcase(os.path.abspath(root))
    return path == base or path.startswith(base.rstrip("\\/") + os.sep)


def _check_write_path(path: str, ctx: GuardContext, cwd: Path) -> None:
    p = _normalize(path, cwd)
    shared = [*ctx.scratch_dirs, *ctx.extra_write_dirs]
    if ctx.target_root is not None:
        if _within(p, ctx.factory_root):
            if _within(p, ctx.factory_root / ".factory-local"):
                return
            _block(f"{path}: the factory repo is read-only while a target is active "
                   "(rule S3, D4)")
        if _within(p, ctx.target_root) or any(_within(p, d) for d in shared):
            return
        _block(f"{path}: writes are allowed only inside the target repo "
               f"({ctx.target_root}) or the scratch directory (rule S12)")
    if _within(p, ctx.factory_root) or any(_within(p, d) for d in shared):
        return
    _block(f"{path}: with no active target, writes are allowed only inside the factory repo "
           "or the scratch directory")
