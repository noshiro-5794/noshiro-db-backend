from http import HTTPStatus

from shared.exceptions import ApplicationError


class CommunityError(ApplicationError):
    default_code = "community_error"
    default_message = "The community operation could not be completed."


class CommunityPostNotFound(CommunityError):
    default_code = "community.post_not_found"
    default_message = "Community post not found."
    default_status = HTTPStatus.NOT_FOUND


class CommunityCommentNotFound(CommunityError):
    default_code = "community.comment_not_found"
    default_message = "Community comment not found."
    default_status = HTTPStatus.NOT_FOUND


class CommunityPermissionDenied(CommunityError):
    default_code = "community.permission_denied"
    default_message = "You do not have permission to perform this action."
    default_status = HTTPStatus.FORBIDDEN


class CommunityTargetLocked(CommunityError):
    default_code = "community.target_locked"
    default_message = "The community target is locked."
    default_status = HTTPStatus.CONFLICT


class CannotFollowSelf(CommunityError):
    default_code = "community.cannot_follow_self"
    default_message = "can not follow yourself"


class FollowRelationNotFound(CommunityError):
    default_code = "community.follow_not_found"
    default_message = "Follow relation not found."
    default_status = HTTPStatus.NOT_FOUND


class CannotFollowBlockedUser(CommunityError):
    default_code = "community.cannot_follow_blocked_user"
    default_message = "can not follow blocked user"


class CannotBlockSelf(CommunityError):
    default_code = "community.cannot_block_self"
    default_message = "can not block yourself"


class BlockRelationNotFound(CommunityError):
    default_code = "community.block_not_found"
    default_message = "Block relation not found."
    default_status = HTTPStatus.NOT_FOUND


class CannotMuteSelf(CommunityError):
    default_code = "community.cannot_mute_self"
    default_message = "can not mute yourself"


class MuteRelationNotFound(CommunityError):
    default_code = "community.mute_not_found"
    default_message = "Mute relation not found."
    default_status = HTTPStatus.NOT_FOUND


class CommunityTargetInvalid(CommunityError):
    default_code = "community.invalid_target"
    default_message = "invalid community target"


class CommunityTargetNotFound(CommunityError):
    default_code = "community.target_not_found"
    default_message = "Community target not found."
    default_status = HTTPStatus.NOT_FOUND


class CommunityReactionNotFound(CommunityError):
    default_code = "community.reaction_not_found"
    default_message = "Community reaction not found."
    default_status = HTTPStatus.NOT_FOUND


class CommunityBookmarkNotFound(CommunityError):
    default_code = "community.bookmark_not_found"
    default_message = "Community bookmark not found."
    default_status = HTTPStatus.NOT_FOUND


class CommunityInteractionBlocked(CommunityError):
    default_code = "community.interaction_blocked"
    default_message = "The community interaction is blocked."
    default_status = HTTPStatus.FORBIDDEN


class NotificationNotFound(CommunityError):
    default_code = "community.notification_not_found"
    default_message = "Notification not found."
    default_status = HTTPStatus.NOT_FOUND


class CommunityReportNotFound(CommunityError):
    default_code = "community.report_not_found"
    default_message = "Community report not found."
    default_status = HTTPStatus.NOT_FOUND


class CommunityReportAlreadyResolved(CommunityError):
    default_code = "community.report_already_resolved"
    default_message = "The community report is already resolved."
    default_status = HTTPStatus.CONFLICT
