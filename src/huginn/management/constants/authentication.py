"""Authentication and credential policy constants."""

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 1024
PASSWORD_HASH_METHOD = "scrypt"
SESSION_TOKEN_BYTES = 32
SESSION_TTL_SECONDS = 12 * 60 * 60
GENERIC_AUTHENTICATION_FAILURE = "invalid username or password"
