from http import HTTPStatus

from shared.exceptions import ApplicationError


class IndexDomainError(ApplicationError):
    default_code = "index_error"
    default_message = "The index operation could not be completed."


class SubjectNotFound(IndexDomainError):
    default_code = "index.subject_not_found"
    default_message = "Subject not found."
    default_status = HTTPStatus.NOT_FOUND


class SubjectTypeNotSupported(IndexDomainError):
    default_code = "index.subject_type_not_supported"
    default_message = "Subject type is not supported."


class InvalidEpisodeIds(IndexDomainError):
    default_code = "index.invalid_episode_ids"
    default_message = "One or more episode IDs are invalid."


class EpisodeNotFound(IndexDomainError):
    default_code = "index.episode_not_found"
    default_message = "Episode not found."
    default_status = HTTPStatus.NOT_FOUND


class EntityResolutionError(IndexDomainError):
    default_code = "index.entity_resolution_failed"
    default_message = "The entity resolution operation could not be completed."
    default_status = HTTPStatus.CONFLICT
