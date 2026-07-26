from shared.errors import ApplicationError


class CommunityException(ApplicationError):
    default_code = 30000
    default_message = "community error"


class CommunityPostNotFound(CommunityException):
    default_code = 31000
    default_message = "community post not found"


class CommunityCommentNotFound(CommunityException):
    default_code = 31100
    default_message = "community comment not found"


class CommunityPermissionDenied(CommunityException):
    default_code = 31110
    default_message = "community permission denied"


class CommunityTargetLocked(CommunityException):
    default_code = 31111
    default_message = "community target is locked"


class CannotFollowSelf(CommunityException):
    default_code = 31200
    default_message = "can not follow yourself"


class FollowRelationNotFound(CommunityException):
    default_code = 31201
    default_message = "follow relation not found"


class CannotFollowBlockedUser(CommunityException):
    default_code = 31202
    default_message = "can not follow blocked user"


class CannotBlockSelf(CommunityException):
    default_code = 31210
    default_message = "can not block yourself"


class BlockRelationNotFound(CommunityException):
    default_code = 31211
    default_message = "block relation not found"


class CannotMuteSelf(CommunityException):
    default_code = 31220
    default_message = "can not mute yourself"


class MuteRelationNotFound(CommunityException):
    default_code = 31221
    default_message = "mute relation not found"


class CommunityTargetInvalid(CommunityException):
    default_code = 31300
    default_message = "invalid community target"


class CommunityTargetNotFound(CommunityException):
    default_code = 31301
    default_message = "community target not found"


class CommunityReactionNotFound(CommunityException):
    default_code = 31302
    default_message = "community reaction not found"


class CommunityBookmarkNotFound(CommunityException):
    default_code = 31303
    default_message = "community bookmark not found"


class CommunityInteractionBlocked(CommunityException):
    default_code = 31304
    default_message = "community interaction is blocked"


class NotificationNotFound(CommunityException):
    default_code = 31400
    default_message = "notification not found"


class CommunityReportNotFound(CommunityException):
    default_code = 31500
    default_message = "community report not found"


class CommunityReportAlreadyResolved(CommunityException):
    default_code = 31501
    default_message = "community report is already resolved"
