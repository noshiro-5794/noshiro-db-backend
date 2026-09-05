from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.models import AIProposal
from apps.index.models import MatchCandidate, MatchDecision
from apps.index.services import EntityResolutionError, entity_resolution_service
from apps.sync.api.serializers.matching import MatchCandidateSerializer
from shared.api.pagination import DefaultPageNumberPagination


class MatchingCandidateListView(APIView):
    """Paginated cross-provider identity candidates for admin review."""

    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: MatchCandidateSerializer(many=True)})
    def get(self, request):
        queryset = MatchCandidate.objects.select_related(
            "left_entity", "right_entity"
        ).order_by("-score")
        if candidate_status := request.query_params.get("status"):
            queryset = queryset.filter(status=candidate_status)
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            MatchCandidateSerializer(page, many=True).data
        )


class MatchingCandidateDecideSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(
        choices=[value for value, _ in MatchDecision.Outcome.choices]
    )
    reason = serializers.CharField(max_length=2000, allow_blank=True)


class MatchingCandidateDecideView(APIView):
    """Admin decision that binds or rejects an identity candidate."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        request=MatchingCandidateDecideSerializer,
        responses={200: MatchCandidateSerializer},
    )
    def post(self, request, candidate_id):
        candidate = (
            MatchCandidate.objects.select_related("left_entity", "right_entity")
            .filter(pk=candidate_id)
            .first()
        )
        if candidate is None:
            return Response({"detail": "Match candidate not found."}, status=404)
        serializer = MatchingCandidateDecideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if candidate.status != MatchCandidate.Status.PENDING:
            return Response(
                {"detail": "Match candidate has already been decided."},
                status=409,
            )
        outcome = serializer.validated_data["outcome"]
        reason = serializer.validated_data["reason"]
        try:
            entity_resolution_service.decide_candidate(
                candidate=candidate,
                outcome=outcome,
                decided_by="admin_review",
                reason=reason,
            )
        except EntityResolutionError as exc:
            return Response({"detail": str(exc)}, status=409)
        latest = (
            AIProposal.objects.filter(match_candidate=candidate)
            .order_by("-created_at")
            .first()
        )
        if latest is not None and latest.status == AIProposal.Status.PENDING:
            latest.status = (
                AIProposal.Status.ACCEPTED
                if outcome == MatchDecision.Outcome.BIND
                else AIProposal.Status.REJECTED
            )
            latest.policy_reason = reason or "Admin review"
            latest.decided_at = timezone.now()
            latest.save(update_fields=["status", "policy_reason", "decided_at"])
        return Response(
            MatchCandidateSerializer(candidate).data,
            status=status.HTTP_200_OK,
        )
