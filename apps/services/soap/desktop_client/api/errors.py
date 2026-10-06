"""
Single translation table from backend errors to user-facing messages.
The UI never shows stack traces, SQL, hosts or tokens: only these texts
(plus the backend's own `message` for codes not listed here).
"""

from __future__ import annotations

from api.http import ApiError, ServiceUnreachableError, SessionExpiredError, SERVICE_LABELS


CODE_MESSAGES = {
    # Auth / session
    "INVALID_CREDENTIALS": "Correo o contraseña incorrectos (o la cuenta está inactiva).",
    "SESSION_EXPIRED": "Tu sesión expiró. Inicia sesión nuevamente.",
    "NOT_LOGGED_IN": "Inicia sesión para continuar.",
    "FORBIDDEN": "No tienes permisos para realizar esta operación.",
    "AUTH_BACKEND_UNAVAILABLE": "El servicio de autenticación (Redis) no está disponible. Intenta más tarde.",
    "DATABASE_UNAVAILABLE": "La base de datos no está disponible en este momento. Intenta más tarde.",
    "USER_INACTIVE": "Tu usuario está inactivo. Contacta al administrador.",
    # Users
    "EMAIL_ALREADY_EXISTS": "Ya existe un usuario con ese correo.",
    "ADMIN_ALREADY_EXISTS": "Ya existe un administrador. Solo se permite uno.",
    "ADMIN_MUST_BE_ACTIVE": "Un administrador debe estar activo.",
    "LAST_ADMIN_REQUIRED": "No se puede dejar el sistema sin un administrador activo.",
    "USER_HAS_ORDER_HISTORY": "El usuario tiene pedidos y no se puede eliminar. Desactívalo en su lugar.",
    "USER_NOT_FOUND": "El usuario no existe.",
    # Books / Authors
    "BOOK_NOT_FOUND": "El libro no existe.",
    "BOOK_ALREADY_EXISTS": "Ya existe un libro con ese ISBN.",
    "BOOK_HAS_ORDER_HISTORY": "El libro aparece en pedidos y no se puede eliminar.",
    "BOOK_IN_USE": "El libro está referenciado por otros registros y no se puede eliminar.",
    "INVALID_REFERENCE": "El formato o la categoría indicados no existen.",
    "AUTHOR_NOT_FOUND": "El autor no existe.",
    "AUTHOR_HAS_BOOKS": "El autor tiene libros asociados. Elimina primero las relaciones.",
    "RELATION_ALREADY_EXISTS": "El autor ya está asociado a ese libro.",
    "RELATION_NOT_FOUND": "El autor no está asociado a ese libro.",
    # Orders
    "ORDER_NOT_FOUND": "El pedido no existe.",
    "INSUFFICIENT_STOCK": "No hay stock suficiente para uno o más libros.",
    "INVALID_STATUS_TRANSITION": "Ese cambio de estado no está permitido para el pedido.",
    "ORDER_ALREADY_CANCELLED": "El pedido ya estaba cancelado.",
    "TRANSACTION_CONFLICT": "La operación coincidió con otra al mismo tiempo. Vuelve a intentarlo.",
    # Payments
    "PAYMENT_NOT_FOUND": "El pago no existe.",
    "ORDER_NOT_PAYABLE": "El pedido ya no se puede pagar (no está pendiente).",
    "PAYMENT_ALREADY_APPROVED": "El pago ya fue aprobado.",
    "PAYMENT_ALREADY_REFUNDED": "El pago ya fue reembolsado.",
    "INVALID_PAYMENT_TRANSITION": "Ese cambio de estado no está permitido para el pago.",
    "REFUND_NOT_ALLOWED": "Este pago no se puede reembolsar.",
    "PAYMENT_AMOUNT_MISMATCH": "El monto del pago ya no coincide con el total del pedido.",
    "PAYMENT_REFERENCE_EXISTS": "Ya existe un pago con esa referencia.",
}

STATUS_MESSAGES = {
    400: "Los datos enviados no son válidos.",
    401: "Tu sesión expiró. Inicia sesión nuevamente.",
    403: "No tienes permisos para realizar esta operación.",
    404: "El recurso solicitado no existe.",
    409: "La operación entra en conflicto con el estado actual.",
    503: "El servicio no está disponible temporalmente.",
}

# For validation errors (400) the backend's message is the useful part.
_SHOW_BACKEND_MESSAGE = {"INVALID_INPUT", "UNKNOWN_FIELDS", "FIELDS_NOT_ALLOWED"}


def friendly_message(exc: BaseException) -> str:
    if isinstance(exc, ServiceUnreachableError):
        label = SERVICE_LABELS.get(exc.service, exc.service)
        return f"El servicio {label} no está disponible en este momento."
    if isinstance(exc, SessionExpiredError):
        return CODE_MESSAGES["SESSION_EXPIRED"]
    if isinstance(exc, ApiError):
        if exc.code in _SHOW_BACKEND_MESSAGE:
            fields = (exc.details or {}).get("fields")
            suffix = f" ({', '.join(fields)})" if fields else ""
            return f"Datos inválidos: {exc.message}{suffix}"
        text = CODE_MESSAGES.get(exc.code)
        if text is None:
            text = STATUS_MESSAGES.get(exc.status or 0, exc.message)
            if exc.status and exc.status >= 500:
                label = SERVICE_LABELS.get(exc.service, exc.service)
                text = f"El servicio {label} no está disponible temporalmente."
        return text + _detail_suffix(exc)
    if isinstance(exc, ValueError):
        return str(exc)
    return "Ocurrió un error inesperado."


def _detail_suffix(exc: ApiError) -> str:
    details = exc.details or {}
    if exc.code == "INSUFFICIENT_STOCK" and details.get("items"):
        lines = [f"\n  • {i['isbn']}: pediste {i['requested']}, disponibles {i['available']}" for i in details["items"]]
        return "".join(lines)
    if exc.code == "BOOK_NOT_FOUND" and details.get("isbns"):
        return "\n  ISBN: " + ", ".join(details["isbns"])
    if exc.code == "AUTHOR_HAS_BOOKS" and "books_count" in details:
        return f" (libros asociados: {details['books_count']})"
    return ""
