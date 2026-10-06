"""
Shared security and Redis infrastructure for the Library Python
microservices (login, books/soap, users, authors, orders, payments).

The package name is deliberately unique: each service already has its own
top-level `config`, `db`, `utils`... modules, so a generic name here would
collide with them depending on the working directory.
"""

__version__ = "0.1.0"
