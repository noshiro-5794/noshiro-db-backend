from http import HTTPStatus

from shared.exceptions import ApplicationError


class SyncOperationError(ApplicationError):
    default_code = "sync_error"
    default_message = "The synchronization operation could not be completed."


class SyncSubjectNotFound(SyncOperationError):
    default_code = "sync.subject_not_found"
    default_message = "The subject to synchronize was not found."
    default_status = HTTPStatus.NOT_FOUND


class SyncSubjectNotSupported(SyncOperationError):
    default_code = "sync.subject_not_supported"
    default_message = "The subject cannot be synchronized."


class SyncTaskDispatchFailed(SyncOperationError):
    default_code = "sync.task_dispatch_failed"
    default_message = "The synchronization task could not be dispatched."
    default_status = HTTPStatus.SERVICE_UNAVAILABLE


class SyncTaskAlreadyRunning(SyncOperationError):
    default_code = "sync.task_already_running"
    default_message = "The synchronization task is already running."
    default_status = HTTPStatus.CONFLICT


class SyncJobNotFound(SyncOperationError):
    default_code = "sync.job_not_found"
    default_message = "Synchronization job not found."
    default_status = HTTPStatus.NOT_FOUND


class SourceCatalogConflict(SyncOperationError):
    default_code = "sync.source_catalog_conflict"
    default_message = "The source catalog contains conflicting records."
    default_status = HTTPStatus.CONFLICT


class SyncAIRequiredError(SyncOperationError):
    default_code = "sync.ai_required"
    default_message = "Required AI normalization did not produce a usable result."
    default_status = HTTPStatus.SERVICE_UNAVAILABLE
