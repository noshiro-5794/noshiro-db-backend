from http import HTTPStatus

from shared.exceptions import ApplicationError


class AIError(ApplicationError):
    default_code = "ai_error"
    default_message = "The AI operation could not be completed."


class AIInputNotAllowed(AIError):
    default_code = "ai.input_not_allowed"
    default_message = "The supplied input is not eligible for AI processing."
    default_status = HTTPStatus.FORBIDDEN


class InvalidAIProposal(AIError):
    default_code = "ai.invalid_proposal"
    default_message = "The AI provider returned an invalid proposal."
    default_status = HTTPStatus.BAD_GATEWAY


__all__ = ["AIError", "AIInputNotAllowed", "InvalidAIProposal"]
