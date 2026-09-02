from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sync.api.serializers.campaigns import (
    SyncCampaignCreateSerializer,
    SyncCampaignSerializer,
    SyncWorkItemSerializer,
)
from apps.sync.models import SyncCampaign
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
