from shared.errors import ApplicationError


class IndexException(ApplicationError):
    default_code = 20000
    default_message = "index error"


class SubjectNotFound(IndexException):
    default_code = 21000
    default_message = "subject not found"


class SubjectTypeNotSupported(IndexException):
    default_code = 21001
    default_message = "subject type not supported"


class InvalidEpisodeIds(IndexException):
    default_code = 21100
    default_message = "invalid episode ids"


class EpisodeNotFound(IndexException):
    default_code = 21101
    default_message = "episode not found"
