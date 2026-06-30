"""
Tool: calculate

A safe arithmetic evaluator for the agent.

Safety: Uses a strict whitelist parser — no eval(), no exec().
Only supports +, -, *, / and parentheses over numeric literals.
"""

import re
from typing import Any

# Tokeniser — only digits, decimal points, operators, parens, and whitespace
_ALLOWED = re.compile(r"^[\d\s\+\-\*/\.\(\)]+$")
_TOKEN = re.compile(r"\d+\.?\d*|[+\-*/()]")

# Maximum expression length to guard against DoS
_MAX_LEN = 200


class _Parser:
    """Recursive-descent parser for +, -, *, / with correct precedence."""

    def __init__(self, tokens: list[str]):
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _consume(self, expected: str | None = None) -> str:
        tok = self._tokens[self._pos]
        if expected and tok != expected:
            raise ValueError(f"Expected '{expected}', got '{tok}'")
        self._pos += 1
        return tok

    def parse(self) -> float:
        val = self._expr()
        if self._peek() is not None:
            raise ValueError(f"Unexpected token '{self._peek()}' after expression")
        return val

    def _expr(self) -> float:
        val = self._term()
        while self._peek() in ("+", "-"):
            op = self._consume()
            right = self._term()
            val = val + right if op == "+" else val - right
        return val

    def _term(self) -> float:
        val = self._factor()
        while self._peek() in ("*", "/"):
            op = self._consume()
            right = self._factor()
            if op == "/" and right == 0:
                raise ValueError("Division by zero")
            val = val * right if op == "*" else val / right
        return val

    def _factor(self) -> float:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")
        if tok == "(":
            self._consume("(")
            val = self._expr()
            self._consume(")")
            return val
        if tok == "-":
            self._consume()
            return -self._factor()
        # Must be a number
        try:
            self._pos += 1
            return float(tok)
        except ValueError:
            raise ValueError(f"Expected number, got '{tok}'")


def calculate(expression: str) -> dict:
    """
    Safely evaluate a basic arithmetic expression.

    Parameters
    ----------
    expression : a string like "89 * 2 + 115 * 2"

    Returns
    -------
    dict with keys:
        "ok"         : bool
        "expression" : str  – the sanitised expression
        "result"     : float | None
        "error"      : str | None
    """
    if not isinstance(expression, str):
        return {
            "ok": False,
            "expression": repr(expression),
            "result": None,
            "error": "expression must be a string",
        }

    expr = expression.strip()

    if len(expr) > _MAX_LEN:
        return {
            "ok": False,
            "expression": expr[:50] + "…",
            "result": None,
            "error": f"expression too long (max {_MAX_LEN} chars)",
        }

    if not expr:
        return {"ok": False, "expression": "", "result": None, "error": "empty expression"}

    # Whitelist check — rejects any character outside our safe set
    if not _ALLOWED.match(expr):
        bad = sorted({c for c in expr if not re.match(r"[\d\s\+\-\*/\.\(\)]", c)})
        return {
            "ok": False,
            "expression": expr,
            "result": None,
            "error": f"disallowed characters in expression: {bad}",
        }

    tokens = _TOKEN.findall(expr)
    if not tokens:
        return {"ok": False, "expression": expr, "result": None, "error": "no tokens found"}

    try:
        result = _Parser(tokens).parse()
    except ValueError as exc:
        return {"ok": False, "expression": expr, "result": None, "error": str(exc)}

    return {"ok": True, "expression": expr, "result": round(result, 2), "error": None}
