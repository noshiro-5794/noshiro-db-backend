from apps.core.exceptions import BusinessException


class SyncException(BusinessException):

    default_code = 30000
    default_detail = "sync error"


class SyncSubjectNotFound(SyncException):

    default_code = 31000
    default_detail = "sync subject not found"


class SyncSubjectNotSupported(SyncException):

    default_code = 31001
    default_detail = "subject cannot be synced"


class SyncTaskDispatchFailed(SyncException):

    default_code = 31002
    default_detail = "sync task dispatch failed"


class SyncTaskAlreadyRunning(SyncException):

    default_code = 31003
    default_detail = "sync task already running"


class SyncJobNotFound(SyncException):

    default_code = 31004
    default_detail = "sync job not found"
