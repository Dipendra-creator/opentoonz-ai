"""Reader/writer for OpenToonz's tagged text stream format (.tnz, .tpl, ...).

The format is produced by TOStream / consumed by TIStream
(toonz/sources/common/tstream/tstream.cpp). It looks like XML but is not:

* values between tags are whitespace separated tokens;
* strings that are not plain identifiers are double-quoted and escaped with
  backslashes (\\ and \"), never with XML entities;
* persistent objects are written once as ``<tag id='N'>...</tag>`` and later
  referenced as ``<tag id='N'/>``. Ids are shared across the whole file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Union

# --------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------


def _escape(v: str) -> str:
    out = []
    for ch in v:
        if ch in ('\\', '"'):
            out.append('\\')
        out.append(ch)
    return ''.join(out)


def format_value(v) -> str:
    """Formats a value like TOStream::operator<< does."""
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if abs(v) < 1e-12:  # TOStream zeroes almost-zero doubles
            v = 0.0
        s = '%.10g' % v
        return s
    s = str(v)
    if s == '':
        return '""'
    if all((ch.isascii() and ch.isalnum()) or ch in '_%' for ch in s):
        return s
    return '"' + _escape(s) + '"'


class TnzWriter:
    """Mimics TOStream's output layout (indentation is cosmetic)."""

    def __init__(self) -> None:
        self._out: list[str] = []
        self._tab = 0
        self._just_started = True
        self._stack: list[str] = []
        self._max_id = 0

    # -- layout -------------------------------------------------------------
    def cr(self) -> None:
        self._out.append('\n' + '  ' * self._tab)
        self._just_started = False

    def open(self, tag: str, attrs: dict | None = None) -> None:
        if not self._just_started:
            self.cr()
        self._out.append('<' + tag + _attrs(attrs) + '>')
        self._stack.append(tag)
        self._tab += 1
        self.cr()
        self._just_started = True

    def close(self) -> None:
        tag = self._stack.pop()
        self._tab -= 1
        if not self._just_started:
            self.cr()
        self._out.append('</' + tag + '>')
        self.cr()
        self._just_started = True

    def open_close(self, tag: str, attrs: dict | None = None) -> None:
        if not self._just_started:
            self.cr()
        self._out.append('<' + tag + _attrs(attrs) + '/>')
        self.cr()
        self._just_started = True

    def values(self, *vals) -> None:
        for v in vals:
            self._out.append(format_value(v) + ' ')
        self._just_started = False

    def child(self, tag: str, *vals) -> None:
        self.open(tag)
        self.values(*vals)
        self.close()

    # -- persistent objects ------------------------------------------------
    def new_id(self) -> int:
        self._max_id += 1
        return self._max_id

    def persist_open(self, tag: str) -> int:
        pid = self.new_id()
        self._out.append("<%s id='%d'>" % (tag, pid))
        self._stack.append(tag)
        self._tab += 1
        self.cr()
        return pid

    def persist_close(self) -> None:
        tag = self._stack.pop()
        self._tab -= 1
        self.cr()
        self._out.append('</' + tag + '>')
        self.cr()

    def persist_ref(self, tag: str, pid: int) -> None:
        self._out.append("<%s id='%d'/>" % (tag, pid))
        self._just_started = False

    def text(self) -> str:
        assert not self._stack, 'unclosed tags: %r' % self._stack
        return ''.join(self._out).rstrip() + '\n'


def _attrs(attrs: dict | None) -> str:
    if not attrs:
        return ''
    # TOStream iterates a std::map, i.e. sorted keys
    return ''.join(' %s="%s"' % (k, _escape(str(attrs[k]))) for k in sorted(attrs))


# --------------------------------------------------------------------------
# Reader
# --------------------------------------------------------------------------


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)  # Node | str
    self_closing: bool = False

    # helpers -------------------------------------------------------------
    def nodes(self, tag: str | None = None) -> Iterator['Node']:
        for c in self.children:
            if isinstance(c, Node) and (tag is None or c.tag == tag):
                yield c

    def find(self, tag: str) -> 'Node | None':
        return next(self.nodes(tag), None)

    def tokens(self) -> list[str]:
        return [c for c in self.children if isinstance(c, str)]

    def floats(self) -> list[float]:
        return [float(t) for t in self.tokens()]

    def ints(self) -> list[int]:
        return [int(float(t)) for t in self.tokens()]

    def text(self) -> str:
        toks = self.tokens()
        return toks[0] if toks else ''


Token = Union[Node, str]


class TnzParseError(Exception):
    pass


def parse(text: str) -> Node:
    """Parses a stream into a tree rooted at a synthetic '#root' node."""
    root = Node('#root')
    stack = [root]
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == '<':
            if text.startswith('<!--', i):
                j = text.find('-->', i)
                if j < 0:
                    raise TnzParseError('unterminated comment')
                i = j + 3
                continue
            j = i + 1
            closing = False
            if j < n and text[j] == '/':
                closing = True
                j += 1
            # tag name
            k = j
            while k < n and (text[k].isalnum() or text[k] in '_.-'):
                k += 1
            name = text[j:k]
            if not name:
                raise TnzParseError('expected identifier at %d' % i)
            attrs: dict[str, str] = {}
            self_closing = False
            while True:
                while k < n and text[k].isspace():
                    k += 1
                if k >= n:
                    raise TnzParseError('unterminated tag ' + name)
                if text[k] == '>':
                    k += 1
                    break
                if text[k] == '/':
                    self_closing = True
                    k += 1
                    continue
                a = k
                while k < n and (text[k].isalnum() or text[k] in '_.-'):
                    k += 1
                aname = text[a:k]
                if not aname:
                    raise TnzParseError('bad attribute near %d' % k)
                while k < n and text[k].isspace():
                    k += 1
                if k < n and text[k] == '=':
                    k += 1
                    while k < n and text[k].isspace():
                        k += 1
                    q = text[k]
                    if q not in '"\'':
                        raise TnzParseError('expected quoted value near %d' % k)
                    k += 1
                    buf = []
                    while k < n and text[k] != q:
                        if text[k] == '\\' and k + 1 < n:
                            k += 1
                        buf.append(text[k])
                        k += 1
                    k += 1
                    attrs[aname] = ''.join(buf)
            i = k
            if closing:
                if len(stack) == 1 or stack[-1].tag != name:
                    raise TnzParseError('unexpected </%s>' % name)
                stack.pop()
            else:
                node = Node(name, attrs, [], self_closing)
                stack[-1].children.append(node)
                if not self_closing:
                    stack.append(node)
            continue
        if ch == '"':
            k = i + 1
            buf = []
            while k < n and text[k] != '"':
                if text[k] == '\\' and k + 1 < n and text[k + 1] in '"\\\'':
                    k += 1
                buf.append(text[k])
                k += 1
            stack[-1].children.append(''.join(buf))
            i = k + 1
            continue
        k = i
        while k < n and not text[k].isspace() and text[k] not in '<"':
            k += 1
        stack[-1].children.append(text[i:k])
        i = k
    if len(stack) != 1:
        raise TnzParseError('unclosed tag <%s>' % stack[-1].tag)
    return root


def parse_file(path) -> Node:
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] in (b'TABc', b'TNZC'):
        raise TnzParseError(
            'compressed stream files are not supported; re-save the scene '
            'from OpenToonz with compression disabled')
    return parse(data.decode('utf-8', errors='replace'))
