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


class AnswerFailed(DomainError):
    """The answer could not be produced; its trace (with the error) is saved under `trace_id`."""

    def __init__(self, trace_id: str):
        super().__init__(trace_id)
        self.trace_id = trace_id
