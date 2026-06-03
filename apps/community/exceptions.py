from apps.core.exceptions import BusinessException


class CommunityException(BusinessException):

    default_code = 30000
    default_detail = "community error"


class CommunityPostNotFound(CommunityException):

    default_code = 31000
    default_detail = "community post not found"


class CommunityCommentNotFound(CommunityException):

    default_code = 31100
    default_detail = "community comment not found"


class CommunityPermissionDenied(CommunityException):

    default_code = 31110
    default_detail = "community permission denied"


class CommunityTargetLocked(CommunityException):

    default_code = 31111
    default_detail = "community target is locked"


class CannotFollowSelf(CommunityException):

    default_code = 31200
    default_detail = "can not follow yourself"


class FollowRelationNotFound(CommunityException):

    default_code = 31201
    default_detail = "follow relation not found"


class CannotFollowBlockedUser(CommunityException):

    default_code = 31202
    default_detail = "can not follow blocked user"


class CannotBlockSelf(CommunityException):

    default_code = 31210
    default_detail = "can not block yourself"


class BlockRelationNotFound(CommunityException):

    default_code = 31211
    default_detail = "block relation not found"


class CannotMuteSelf(CommunityException):

    default_code = 31220
    default_detail = "can not mute yourself"


class MuteRelationNotFound(CommunityException):

    default_code = 31221
    default_detail = "mute relation not found"


class CommunityTargetInvalid(CommunityException):

    default_code = 31300
    default_detail = "invalid community target"


class CommunityTargetNotFound(CommunityException):

    default_code = 31301
    default_detail = "community target not found"


class CommunityReactionNotFound(CommunityException):

    default_code = 31302
    default_detail = "community reaction not found"


class CommunityBookmarkNotFound(CommunityException):

    default_code = 31303
    default_detail = "community bookmark not found"


class NotificationNotFound(CommunityException):

    default_code = 31400
    default_detail = "notification not found"


class CommunityReportNotFound(CommunityException):

    default_code = 31500
    default_detail = "community report not found"
