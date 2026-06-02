from apps.core.exceptions import BusinessException


class UserException(BusinessException):

    default_code = 10000
    default_detail = "user error"


class EmailSendTooFrequent(UserException):

    default_code = 11000
    default_detail = "email send too frequent"


class InvalidVerifyCode(UserException):

    default_code = 11001
    default_detail = "invalid verify code"


class VerifyCodeExpired(UserException):

    default_code = 11002
    default_detail = "verify code expired"


class InvalidCaptcha(UserException):

    default_code = 11003
    default_detail = "invalid captcha"


class EmailAlreadyExists(UserException):

    default_code = 11100
    default_detail = "email already exists"


class InvalidEmailOrPassword(UserException):

    default_code = 11200
    default_detail = "invalid email or password"


class UserNotFound(UserException):

    default_code = 11201
    default_detail = "user not found"


class AvatarUploadFailed(UserException):

    default_code = 12000
    default_detail = "avatar upload failed"


class UserSubjectNotFound(UserException):

    default_code = 12100
    default_detail = "user subject not found"


class TagNotFound(UserException):

    default_code = 12200
    default_detail = "tag not found"


class TagAlreadyExists(UserException):

    default_code = 12201
    default_detail = "tag already exists"


class InvalidTagIds(UserException):

    default_code = 12202
    default_detail = "invalid tag ids"


class ReviewNotFound(UserException):

    default_code = 12300
    default_detail = "review not found"


class CollectionNotFound(UserException):

    default_code = 12400
    default_detail = "collection not found"


class CollectionItemNotFound(UserException):

    default_code = 12401
    default_detail = "collection item not found"


class InvalidUserSubjectIds(UserException):

    default_code = 12402
    default_detail = "invalid user subject ids"
