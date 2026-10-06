"""
Role ids as stored in the `roles` table (data/07_microservices_auth_orders_payments.sql)
and carried in the JWT `role_id` claim.
"""

ROLE_USER = 1
ROLE_ADMIN = 2

ROLE_CODES = {
    ROLE_USER: "USER",
    ROLE_ADMIN: "ADMIN",
}
