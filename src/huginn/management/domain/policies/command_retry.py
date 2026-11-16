from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.command_identity import CommandIdentity


def validate_command_retry(
    receipt: CommandReceipt,
    requested_scope: str,
    requested_identity: CommandIdentity,
) -> bool:
    """Compare committed intent only after key-only receipt lookup."""
    if receipt.identity.key != requested_identity.key:
        raise ConflictError(
            "Command receipt lookup returned a different idempotency key"
        )
    if (
        receipt.scope != requested_scope
        or receipt.identity.payload_fingerprint
        != requested_identity.payload_fingerprint
    ):
        raise ConflictError(
            "Idempotency key was already used for different command intent"
        )
    return True
