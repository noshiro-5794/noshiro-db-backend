from shared.errors import ApplicationError


class UserException(ApplicationError):
    default_code = 10000
    default_message = "user error"


class EmailSendTooFrequent(UserException):
    default_code = 11000
    default_message = "email send too frequent"


class InvalidVerifyCode(UserException):
    default_code = 11001
    default_message = "invalid verify code"


class VerifyCodeExpired(UserException):
    default_code = 11002
    default_message = "verify code expired"


class InvalidCaptcha(UserException):
    default_code = 11003
    default_message = "invalid captcha"


class EmailAlreadyExists(UserException):
    default_code = 11100
    default_message = "email already exists"


class NicknameAlreadyExists(UserException):
    default_code = 11101
    default_message = "nickname already exists"


class InvalidEmailOrPassword(UserException):
    default_code = 11200
    default_message = "invalid email or password"


class UserNotFound(UserException):
    default_code = 11201
    default_message = "user not found"


class AvatarUploadFailed(UserException):
    default_code = 12000
    default_message = "avatar upload failed"


class UserSubjectNotFound(UserException):
    default_code = 12100
    default_message = "user subject not found"


class InvalidWatchDateRange(UserException):
    default_code = 12101
    default_message = "watch end date must not be earlier than watch start date"


class TagNotFound(UserException):
    default_code = 12200
    default_message = "tag not found"


class TagAlreadyExists(UserException):
    default_code = 12201
    default_message = "tag already exists"


class InvalidTagIds(UserException):
    default_code = 12202
    default_message = "invalid tag ids"


class ReviewNotFound(UserException):
    default_code = 12300
    default_message = "review not found"


class CollectionNotFound(UserException):
    default_code = 12400
    default_message = "collection not found"


class CollectionItemNotFound(UserException):
    default_code = 12401
    default_message = "collection item not found"


class InvalidUserSubjectIds(UserException):
    default_code = 12402
    default_message = "invalid user subject ids"
