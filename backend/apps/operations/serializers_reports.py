from rest_framework import serializers
from apps.operations.serializers_reports_base import ReportRowsFieldMixin, TypedReportBaseSerializer


class TakenItemsReportRowSerializer(TypedReportBaseSerializer):
    product = serializers.CharField()
    issued_quantity = serializers.IntegerField()


class ActiveLoansReportRowSerializer(TypedReportBaseSerializer):
    id = serializers.IntegerField()
    requester = serializers.CharField()
    status = serializers.CharField()
    issued_at = serializers.DateTimeField(allow_null=True)


class ReturnsReportRowSerializer(TypedReportBaseSerializer):
    id = serializers.IntegerField()
    requester = serializers.CharField()
    status = serializers.CharField()
    closed_at = serializers.DateTimeField(allow_null=True)


class DamagedMissingReportRowSerializer(TypedReportBaseSerializer):
    product = serializers.CharField()
    damaged_quantity = serializers.IntegerField()
    missing_quantity = serializers.IntegerField()


class DamagedLostReportRowSerializer(TypedReportBaseSerializer):
    product_name = serializers.CharField()
    damaged_quantity = serializers.IntegerField()
    lost_quantity = serializers.IntegerField()


class QrScansReportRowSerializer(TypedReportBaseSerializer):
    context = serializers.CharField()
    count = serializers.IntegerField()


class MostLentReportRowSerializer(TypedReportBaseSerializer):
    product_name = serializers.CharField()
    times_lent = serializers.IntegerField()
    total_quantity_lent = serializers.IntegerField()


class TopBorrowersReportRowSerializer(TypedReportBaseSerializer):
    holder = serializers.CharField()
    requests = serializers.IntegerField()
    items_borrowed = serializers.IntegerField()


class RecentlyAddedReportRowSerializer(TypedReportBaseSerializer):
    product_name = serializers.CharField()
    created_at = serializers.DateTimeField()
    total_quantity = serializers.IntegerField()


class TakenItemsReportSerializer(ReportRowsFieldMixin):
    typed_rows = TakenItemsReportRowSerializer(many=True)


class ActiveLoansReportSerializer(ReportRowsFieldMixin):
    typed_rows = ActiveLoansReportRowSerializer(many=True)


class ReturnsReportSerializer(ReportRowsFieldMixin):
    typed_rows = ReturnsReportRowSerializer(many=True)


class DamagedMissingReportSerializer(ReportRowsFieldMixin):
    typed_rows = DamagedMissingReportRowSerializer(many=True)


class DamagedLostReportSerializer(ReportRowsFieldMixin):
    typed_rows = DamagedLostReportRowSerializer(many=True)


class QrScansReportSerializer(ReportRowsFieldMixin):
    typed_rows = QrScansReportRowSerializer(many=True)


class MostLentReportSerializer(ReportRowsFieldMixin):
    typed_rows = MostLentReportRowSerializer(many=True)


class TopBorrowersReportSerializer(ReportRowsFieldMixin):
    typed_rows = TopBorrowersReportRowSerializer(many=True)


class RecentlyAddedReportSerializer(ReportRowsFieldMixin):
    typed_rows = RecentlyAddedReportRowSerializer(many=True)


from apps.operations.serializers_reports_fablab import (  # noqa: E402
    BookingUtilizationReportSerializer,
    EventAttendanceReportSerializer,
    FabLabHealthReportSerializer,
    MachineUsageReportSerializer,
    MaintenanceActivityReportSerializer,
    MemberActivityReportSerializer,
    ReportErrorSerializer,
)
