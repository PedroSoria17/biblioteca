"""
Local, temporary shopping cart (in memory, per session).

Only WHAT to buy is kept (isbn, title for display, quantity). Prices and
totals are not computed here: the order total is the one Orders returns.
"""

from __future__ import annotations

from dataclasses import dataclass


MAX_CANTIDAD = 10_000  # same limit Orders validates (UX only; the backend decides)


@dataclass
class CartLine:
    isbn: str
    titulo: str
    cantidad: int


class Cart:
    def __init__(self) -> None:
        self._lines: dict[str, CartLine] = {}

    def add(self, isbn: str, titulo: str, cantidad) -> CartLine:
        if isinstance(cantidad, bool) or not isinstance(cantidad, int):
            raise ValueError("La cantidad debe ser un número entero.")
        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que cero.")
        isbn = isbn.strip().upper()
        line = self._lines.get(isbn)
        if line is None:
            line = self._lines[isbn] = CartLine(isbn, titulo, 0)
        if line.cantidad + cantidad > MAX_CANTIDAD:
            raise ValueError(f"La cantidad máxima por libro es {MAX_CANTIDAD}.")
        line.cantidad += cantidad  # same ISBN twice -> one line, like Orders
        return line

    def remove(self, isbn: str) -> None:
        self._lines.pop(isbn.strip().upper(), None)

    def clear(self) -> None:
        self._lines.clear()

    @property
    def lines(self) -> list[CartLine]:
        return sorted(self._lines.values(), key=lambda line: line.isbn)

    def is_empty(self) -> bool:
        return not self._lines

    def to_order_items(self) -> list[dict]:
        """Exactly the body Orders expects: [{"isbn", "cantidad"}]."""
        return [{"isbn": line.isbn, "cantidad": line.cantidad} for line in self.lines]


def parse_quantity(text: str) -> int:
    """UX validation of a quantity typed in the UI."""
    try:
        value = int(str(text).strip())
    except ValueError as exc:
        raise ValueError("La cantidad debe ser un número entero.") from exc
    if value <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")
    return value
