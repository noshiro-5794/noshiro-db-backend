from django.db.models import Count
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.models import AIClaim
from apps.sync.api.serializers.campaigns import (
    AIClaimSerializer,
    SyncCampaignCreateSerializer,
    SyncCampaignSerializer,
    SyncWorkItemSerializer,
)
from apps.sync.models import SyncCampaign, SyncWorkItem
from apps.sync.services.campaign_service import sync_campaign_service
from apps.sync.tasks.campaign import run_sync_campaign_task
from shared.api.pagination import DefaultPageNumberPagination


def _campaign_or_404(campaign_id):
    try:
        return SyncCampaign.objects.get(pk=campaign_id)
    except SyncCampaign.DoesNotExist:
        from rest_framework.exceptions import NotFound

        raise NotFound("Sync campaign not found.") from None


@extend_schema_view(
    get=extend_schema(responses={200: SyncCampaignSerializer(many=True)}),
    post=extend_schema(
        request=SyncCampaignCreateSerializer, responses={202: SyncCampaignSerializer}
    ),
)
class SyncCampaignListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        queryset = SyncCampaign.objects.all()
        if provider := request.query_params.get("provider"):
            queryset = queryset.filter(provider_slug=provider)
        if campaign_status := request.query_params.get("status"):
            queryset = queryset.filter(status=campaign_status)
        return Response(SyncCampaignSerializer(queryset[:100], many=True).data)

    def post(self, request):
        serializer = SyncCampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        campaign = sync_campaign_service.create_campaign(
            provider_slug=values["provider"],
            campaign_type=values["campaign_type"],
            ai_mode=values["ai_mode"],
            parameters=values.get("parameters"),
            idempotency_key=values.get("idempotency_key") or None,
        )
        if campaign.status in {SyncCampaign.Status.QUEUED, SyncCampaign.Status.FAILED}:
            run_sync_campaign_task.delay(str(campaign.pk))
        return Response(
            SyncCampaignSerializer(campaign).data, status=status.HTTP_202_ACCEPTED
        )


class SyncCampaignDetailView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        request=None,
        responses={200: SyncCampaignSerializer},
        parameters=[],
    )
    def get(self, request, campaign_id):
        return Response(SyncCampaignSerializer(_campaign_or_404(campaign_id)).data)


class SyncCampaignItemsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: SyncWorkItemSerializer(many=True)})
    def get(self, request, campaign_id):
        campaign = _campaign_or_404(campaign_id)
        queryset = campaign.work_items.order_by("shard", "id")
        if item_status := request.query_params.get("status"):
            queryset = queryset.filter(status=item_status)
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            SyncWorkItemSerializer(page, many=True).data
        )


class SyncCampaignClaimsView(APIView):
    """Paginated AI claims produced for one campaign (admin decision display)."""

    permission_classes = [IsAdminUser]

    @extend_schema(responses={200: AIClaimSerializer(many=True)})
    def get(self, request, campaign_id):
        campaign = _campaign_or_404(campaign_id)
        if campaign.agent_run_id is None:
            return Response({"count": 0, "results": []})
        queryset = (
            AIClaim.objects.filter(step__run_id=campaign.agent_run_id)
            .select_related("step__run")
            .prefetch_related("evidence_links__artifact")
            .order_by("-created_at")
        )
        if claim_status := request.query_params.get("status"):
            queryset = queryset.filter(status=claim_status)
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(AIClaimSerializer(page, many=True).data)


class SyncCampaignSummaryView(APIView):
    """Operational summary for monitoring all sync campaigns."""

    permission_classes = [IsAdminUser]

    @extend_schema(
        responses={
            200: inline_serializer(
                "SyncCampaignSummary",
                fields={
                    "campaigns_by_status": OpenApiTypes.OBJECT,
                    "campaigns_by_provider": OpenApiTypes.OBJECT,
                    "stale_leases": OpenApiTypes.INT,
                    "queued_items": OpenApiTypes.INT,
                    "failed_items": OpenApiTypes.INT,
                    "pending_ai_claims": OpenApiTypes.INT,
                },
            )
        }
    )
    def get(self, request):
        now = timezone.now()
        by_status = dict(
            SyncCampaign.objects.values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )
        by_provider = dict(
            SyncCampaign.objects.values("provider_slug")
            .annotate(count=Count("id"))
            .values_list("provider_slug", "count")
        )
        stale_leases = SyncCampaign.objects.filter(
            status__in={
                SyncCampaign.Status.QUEUED,
                SyncCampaign.Status.DISCOVERING,
                SyncCampaign.Status.FETCHING,
                SyncCampaign.Status.MAPPING,
                SyncCampaign.Status.NORMALIZING,
                SyncCampaign.Status.RECONCILING,
                SyncCampaign.Status.ENRICHING,
                SyncCampaign.Status.REVIEWING,
            },
            lease_expires_at__lt=now,
        ).count()
        pending_ai_claims = AIClaim.objects.filter(
            status=AIClaim.Status.PROPOSED,
            step__run__sync_campaign__isnull=False,
        ).count()
        return Response(
            {
                "campaigns_by_status": by_status,
                "campaigns_by_provider": by_provider,
                "stale_leases": stale_leases,
                "queued_items": SyncWorkItem.objects.filter(
                    status=SyncWorkItem.Status.QUEUED
                ).count(),
                "failed_items": SyncWorkItem.objects.filter(
                    status=SyncWorkItem.Status.FAILED
                ).count(),
                "pending_ai_claims": pending_ai_claims,
            }
        )


class SyncCampaignActionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(request=None, responses={200: SyncCampaignSerializer})
    def post(self, request, campaign_id, action):
        campaign = _campaign_or_404(campaign_id)
        if action == "pause":
            campaign = sync_campaign_service.pause(campaign)
        elif action == "resume":
            campaign = sync_campaign_service.resume_paused(campaign)
            if campaign.status not in {
                SyncCampaign.Status.PAUSED,
                SyncCampaign.Status.CANCELLED,
            }:
                run_sync_campaign_task.delay(str(campaign.pk))
        elif action == "cancel":
            campaign = sync_campaign_service.cancel(campaign)
        else:
            from rest_framework.exceptions import NotFound

            raise NotFound("Unsupported campaign action.")
        return Response(SyncCampaignSerializer(campaign).data)
