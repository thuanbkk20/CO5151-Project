"""Errors the use cases raise; the API layer maps each one to an HTTP status."""


class DomainError(Exception):
    pass


class InvalidCredentials(DomainError):
    pass


class Unauthenticated(DomainError):
    pass


class NotFound(DomainError):
    """Also raised for another user's conversation, so its existence is not revealed."""


class InvalidRequest(DomainError):
    pass


class LLMError(DomainError):
    """An LLM call failed (network, quota, refused parameter) or its reply could not be used."""
