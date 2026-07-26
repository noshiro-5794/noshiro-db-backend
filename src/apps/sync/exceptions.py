from shared.errors import ApplicationError


class SyncException(ApplicationError):
    default_code = 30000
    default_message = "sync error"


class SyncSubjectNotFound(SyncException):
    default_code = 31000
    default_message = "sync subject not found"


class SyncSubjectNotSupported(SyncException):
    default_code = 31001
    default_message = "subject cannot be synced"


class SyncTaskDispatchFailed(SyncException):
    default_code = 31002
    default_message = "sync task dispatch failed"


class SyncTaskAlreadyRunning(SyncException):
    default_code = 31003
    default_message = "sync task already running"


class SyncJobNotFound(SyncException):
    default_code = 31004
    default_message = "sync job not found"
