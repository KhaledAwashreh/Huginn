"""A delivery failure proven to precede any SMTP transport attempt."""


class MailPreTransportError(ValueError):
    pass
