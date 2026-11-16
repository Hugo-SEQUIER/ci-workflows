#!/usr/bin/env python3
"""Fail when a pull request removes something from the code that a test or a doc still uses.

A reference is stale when all three hold:
1. a test or doc file at the PR head contains it (a name, a CSS class, a route, a quoted UI string),
2. the base version of a source file this PR changed contained it,
3. no source file at the PR head contains it any more.

So it only flags what this PR removed; drift that was already there does not fail the check.
Changelogs and decision logs are skipped: they keep old names on purpose.
Silence one line by writing `stale-refs: ignore` on it.

Usage: stale_refs.py [--fail] <base-ref> [<head-ref>]   (run from the repository root)
Without --fail it reports warnings and exits 0; with --fail a stale reference fails the run.
"""

import re
import subprocess
import sys

CONSUMER = re.compile(
    r"(^|/)(tests?|__tests__|e2e|spec|specs|docs?)/"
    r"|\.(test|spec|e2e)\.[cm]?[jt]sx?$|(^|/)test_[^/]*\.py$|_test\.(py|go)$"
    r"|\.(md|mdx|rst)$",
    re.I,
)
SKIP = re.compile(
    r"(^|/)(node_modules|dist|build|\.next|vendor|coverage)/"
    r"|(\.lock|lock\.json|lock\.yaml|\.min\.js|\.map|\.svg|\.snap)$"
    r"|\.(png|jpe?g|gif|webp|ico|pdf|woff2?|ttf|mp4|mp3|zip|gz)$",
    re.I,
)
WORD = re.compile(r"(?<![\w-])[A-Za-z_][\w-]*[\w](?![\w-])")
QUOTED = re.compile(r"""(["'`])([^"'`\n]{4,120}?)\1""")
PHRASE = re.compile(r"/[\w/?=&#.-]+|[A-Z][\w'’.,!?:-]*( [\w'’.,!?:|&-]+)+")
FILENAME = re.compile(r"\.?[\w-]+(\.[\w-]+)*")  # ".gitignore" is a file, not a CSS selector
# Lines that assert something is absent, or say it used to exist.
NEGATION = re.compile(
    r"\.not\.|\bnot\b|NotIn|NotContain|notContains|toHaveCount\(0\)|doesNotMatch|!==?|\bno longer\b"
    r"|\bnever\b|\bformer(ly)?\b|\bpreviously\b|\bremoved\b|\bdeprecated\b|\binstead of\b|\brenamed\b",
    re.I,
)
SELECTOR = re.compile(r"(?<![\w-])\.([A-Za-z][\w-]{2,})")
COMMON = {
    "true", "false", "null", "none", "undefined", "return", "const", "import", "export", "from",
    "function", "class", "self", "this", "async", "await", "default", "string", "number",
}
DOC = re.compile(r"\.(md|mdx|rst)$", re.I)
# Records of the past keep old names on purpose.
HISTORY = re.compile(r"(^|/)(CHANGELOG|CHANGES|HISTORY|DECISIONS|RELEASES?)[^/]*$|(^|/)(adr|decisions|changelog)/", re.I)
IGNORE = "stale-refs: ignore"
MAX_BYTES = 1_000_000  # bigger files are data or generated, not code a person keeps in sync


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def read_all(ref, paths):
    """{path: text} for the files at ref, read through one `git cat-file --batch` process."""
    if not paths:
        return {}
    request = "".join(f"{ref}:{p}\n" for p in paths).encode()
    out = subprocess.run(["git", "cat-file", "--batch"], input=request, capture_output=True, check=True).stdout
    texts, pos = {}, 0
    for path in paths:
        header_end = out.index(b"\n", pos)
        header = out[pos:header_end].split()
        pos = header_end + 1
        if header[-1] == b"missing":
            texts[path] = ""
            continue
        size = int(header[2])
        texts[path] = out[pos:pos + size].decode("utf-8", "replace") if header[1] == b"blob" else ""
        pos += size + 1
    return texts


def is_source(path):
    return not CONSUMER.search(path) and not SKIP.search(path)


def compound(word):
    """camelCase or snake_case: reads as code even in prose. Kebab-case only counts when quoted,
    because prose is full of words like "read-only"."""
    return bool(re.search(r"_|[a-z][A-Z]", word))


def tokens(line, is_test):
    """(kind, value) pairs a line refers to. A plain word never counts on its own, so prose like
    "see below" or a fixture called "Later" never matches a removed comment."""
    if NEGATION.search(line):
        return set()  # a test that checks the old thing is gone must keep naming it
    found = {("name", w) for w in WORD.findall(line) if compound(w) and len(w) >= 4}
    for _, text in QUOTED.findall(line):
        text = text.strip()
        if PHRASE.fullmatch(text) and len(text) >= 8:  # UI copy and routes
            found.add(("text", text))
        if is_test and not FILENAME.fullmatch(text):
            found.update(("class", cls) for cls in SELECTOR.findall(text))
        if WORD.fullmatch(text) and (compound(text) or "-" in text) and len(text) >= 4:
            found.add(("name", text))
    return found


class Corpus:
    """Source text indexed three ways: words, CSS classes (words inside string literals and
    stylesheets) and raw text for UI copy."""

    def __init__(self, texts):
        self.text = "\n".join(texts.values())
        self.words = set(WORD.findall(self.text))
        self.classes = set()
        for path, text in texts.items():
            if path.endswith((".css", ".scss", ".sass", ".less")):
                self.classes.update(SELECTOR.findall(text))
            for _, literal in QUOTED.findall(text):
                self.classes.update(WORD.findall(literal))

    def __contains__(self, token):
        kind, value = token
        if kind == "class":
            return value in self.classes
        if kind == "name":
            return value in self.words
        return value in self.text


def main():
    args = sys.argv[1:]
    fail = "--fail" in args
    refs = [a for a in args if a != "--fail"]
    if not refs:
        sys.exit(__doc__)
    head = refs[1] if len(refs) > 1 else "HEAD"
    base = git("merge-base", refs[0], head).strip()

    changed = [p for p in git("diff", "--name-only", "--no-renames", base, head).splitlines() if is_source(p)]
    if not changed:
        print("stale-refs: no source file changed")
        return 0
    removed_from = Corpus(read_all(base, changed))

    files = []
    for entry in git("ls-tree", "-r", "-l", head).splitlines():
        meta, path = entry.split("\t", 1)
        size = meta.split()[3]
        if not SKIP.search(path) and size != "-" and int(size) <= MAX_BYTES:
            files.append(path)
    text = read_all(head, files)
    head_source = Corpus({p: t for p, t in text.items() if is_source(p)})

    findings = []
    for path in files:
        if not CONSUMER.search(path) or HISTORY.search(path):
            continue
        is_test = not DOC.search(path)
        for number, line in enumerate(text[path].splitlines(), 1):
            if IGNORE in line:
                continue
            for token in sorted(tokens(line, is_test)):
                if token in removed_from and token not in head_source:
                    findings.append((path, number, token[1]))

    level = "error" if fail else "warning"
    for path, number, token in findings:
        print(f"::{level} file={path},line={number}::'{token}' was removed from the code in this "
              f"pull request but {path} still uses it. Update this line, or add '{IGNORE}' to it.")
    print(f"stale-refs: {len(findings)} stale reference(s), {len(changed)} changed source file(s)")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
