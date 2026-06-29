from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.models import User
from apps.hardware_requests.models import (
    HardwareRequest,
    PublicToolLoan,
    RequesterAccountability,
)


def accountability_data(makerspace_id, *, limit=200):
    repeat_offenders, repeat_truncated = _repeat_offenders(makerspace_id, limit)
    overdue, overdue_truncated = _overdue_loans(makerspace_id, limit)
    return {
        "repeat_offenders": repeat_offenders,
        "overdue": overdue,
        "restrictions": _restricted_requesters(makerspace_id),
        "truncated": {
            "repeat_offenders": repeat_truncated,
            "overdue": overdue_truncated,
        },
    }


def _repeat_offenders(makerspace_id, limit):
    rows = list(
        RequesterAccountability.objects.filter(makerspace_id=makerspace_id)
        .values(
            "requester_id",
            "requester__username",
            "requester__access_status",
            "requester__restriction_reason",
        )
        .annotate(
            damaged=Count("id", filter=Q(issue_type=RequesterAccountability.IssueType.DAMAGED)),
            missing=Count("id", filter=Q(issue_type=RequesterAccountability.IssueType.MISSING)),
            total_issues=Count("id"),
            total_quantity=Coalesce(Sum("quantity"), 0),
        )
        .order_by("-total_issues", "-total_quantity")[: limit + 1]
    )
    return [
        {
            "requester_id": row["requester_id"],
            "username": row["requester__username"],
            "access_status": row["requester__access_status"],
            "restriction_reason": row["requester__restriction_reason"],
            "damaged": row["damaged"],
            "missing": row["missing"],
            "total_issues": row["total_issues"],
            "total_quantity": row["total_quantity"],
        }
        for row in rows[:limit]
    ], len(rows) > limit


def _overdue_loans(makerspace_id, limit):
    now = timezone.now()
    rows = _overdue_requests(makerspace_id, now) + _overdue_direct_loans(makerspace_id, now)
    rows.sort(key=lambda row: row["due_at"])
    truncated = len(rows) > limit
    return [
        {
            **row,
            "due_at": row["due_at"].isoformat(),
            "days_overdue": (now - row["due_at"]).days,
        }
        for row in rows[:limit]
    ], truncated


def _overdue_requests(makerspace_id, now):
    queryset = (
        HardwareRequest.objects.filter(
            makerspace_id=makerspace_id,
            status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ],
            return_due_at__lt=now,
            public_tool_loan__isnull=True,
        )
        .select_related("requester")
        .prefetch_related("items__product")
    )
    return [
        {
            "type": "request",
            "reference_id": request.id,
            "requester_username": request.requester.username,
            "label": _request_label(request),
            "due_at": request.return_due_at,
        }
        for request in queryset
    ]


def _overdue_direct_loans(makerspace_id, now):
    queryset = PublicToolLoan.objects.filter(
        makerspace_id=makerspace_id,
        status=PublicToolLoan.Status.CHECKED_OUT,
        due_at__lt=now,
    ).select_related("requester")
    return [
        {
            "type": "direct",
            "reference_id": loan.id,
            "requester_username": loan.requester.username,
            "label": loan.target_label,
            "due_at": loan.due_at,
        }
        for loan in queryset
    ]


def _request_label(request):
    names = [item.product.name for item in request.items.all()]
    label = ", ".join(names[:5])
    if len(names) > 5:
        label = f"{label}, ..."
    return label


def _restricted_requesters(makerspace_id):
    return [
        {
            "requester_id": user.id,
            "username": user.username,
            "access_status": user.access_status,
            "restriction_reason": user.restriction_reason,
        }
        for user in User.objects.filter(
            accountability_records__makerspace_id=makerspace_id,
            access_status__in=[
                User.AccessStatus.RESTRICTED,
                User.AccessStatus.SUSPENDED,
            ],
        )
        .distinct()
        .order_by("username")
    ]
