from http import HTTPStatus

from shared.exceptions import ApplicationError


class UserError(ApplicationError):
    default_code = "user_error"
    default_message = "The user operation could not be completed."


class EmailSendTooFrequent(UserError):
    default_code = "users.email_send_too_frequent"
    default_message = "Email was requested too frequently."
    default_status = HTTPStatus.TOO_MANY_REQUESTS


class InvalidVerifyCode(UserError):
    default_code = "users.invalid_verification_code"
    default_message = "The verification code is invalid."


class VerifyCodeExpired(UserError):
    default_code = "users.verification_code_expired"
    default_message = "The verification code has expired."


class InvalidCaptcha(UserError):
    default_code = "users.invalid_captcha"
    default_message = "Captcha validation failed."


class EmailAlreadyExists(UserError):
    default_code = "users.email_already_exists"
    default_message = "The email address is already registered."
    default_status = HTTPStatus.CONFLICT


class NicknameAlreadyExists(UserError):
    default_code = "users.nickname_already_exists"
    default_message = "The nickname is already in use."
    default_status = HTTPStatus.CONFLICT


class InvalidEmailOrPassword(UserError):
    default_code = "users.invalid_credentials"
    default_message = "The email address or password is invalid."
    default_status = HTTPStatus.UNAUTHORIZED


class UserNotFound(UserError):
    default_code = "users.user_not_found"
    default_message = "User not found."
    default_status = HTTPStatus.NOT_FOUND


class AvatarUploadFailed(UserError):
    default_code = "users.avatar_upload_failed"
    default_message = "The avatar could not be uploaded."
    default_status = HTTPStatus.BAD_GATEWAY


class UserSubjectNotFound(UserError):
    default_code = "users.library_entry_not_found"
    default_message = "Library entry not found."
    default_status = HTTPStatus.NOT_FOUND


class InvalidWatchDateRange(UserError):
    default_code = "users.invalid_watch_date_range"
    default_message = "watch end date must not be earlier than watch start date"


class TagNotFound(UserError):
    default_code = "users.tag_not_found"
    default_message = "Tag not found."
    default_status = HTTPStatus.NOT_FOUND


class TagAlreadyExists(UserError):
    default_code = "users.tag_already_exists"
    default_message = "The tag already exists."
    default_status = HTTPStatus.CONFLICT


class InvalidTagIds(UserError):
    default_code = "users.invalid_tag_ids"
    default_message = "One or more tag IDs are invalid."


class ReviewNotFound(UserError):
    default_code = "users.review_not_found"
    default_message = "Review not found."
    default_status = HTTPStatus.NOT_FOUND


class CollectionNotFound(UserError):
    default_code = "users.collection_not_found"
    default_message = "Collection not found."
    default_status = HTTPStatus.NOT_FOUND


class CollectionItemNotFound(UserError):
    default_code = "users.collection_item_not_found"
    default_message = "Collection item not found."
    default_status = HTTPStatus.NOT_FOUND


class InvalidUserSubjectIds(UserError):
    default_code = "users.invalid_library_entry_ids"
    default_message = "One or more library entry IDs are invalid."
