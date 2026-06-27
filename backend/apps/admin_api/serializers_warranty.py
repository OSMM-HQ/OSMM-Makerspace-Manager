from django.utils import timezone
from rest_framework import serializers

from apps.warranty.models import Warranty, WarrantyDocument
from apps.warranty.status import warranty_status


class WarrantyDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WarrantyDocument
        fields = [
            "id",
            "original_filename",
            "content_type",
            "size_bytes",
            "created_at",
        ]
        read_only_fields = fields


class WarrantySerializer(serializers.ModelSerializer):
    host_kind = serializers.SerializerMethodField()
    host_id = serializers.SerializerMethodField()
    host_label = serializers.SerializerMethodField()
    asset_id = serializers.SerializerMethodField()
    asset_tag = serializers.SerializerMethodField()
    serial_number = serializers.SerializerMethodField()
    printer_id = serializers.SerializerMethodField()
    printer_name = serializers.SerializerMethodField()
    printer_model = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    documents = WarrantyDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Warranty
        fields = [
            "id",
            "host_kind",
            "host_id",
            "host_label",
            "asset_id",
            "asset_tag",
            "serial_number",
            "printer_id",
            "printer_name",
            "printer_model",
            "purchased_on",
            "warranty_expires_on",
            "vendor_name",
            "vendor_contact",
            "status",
            "documents",
        ]
        read_only_fields = fields

    def get_host_kind(self, obj) -> str:
        return "asset" if obj.asset_id else "printer"

    def get_host_id(self, obj) -> int:
        return obj.asset_id or obj.printer_id

    def get_host_label(self, obj) -> str:
        if obj.asset_id:
            return obj.asset.asset_tag
        return obj.printer.name

    def get_asset_id(self, obj) -> int | None:
        return obj.asset_id

    def get_asset_tag(self, obj) -> str | None:
        return obj.asset.asset_tag if obj.asset_id else None

    def get_serial_number(self, obj) -> str | None:
        return obj.asset.serial_number if obj.asset_id else None

    def get_printer_id(self, obj) -> int | None:
        return obj.printer_id

    def get_printer_name(self, obj) -> str | None:
        return obj.printer.name if obj.printer_id else None

    def get_printer_model(self, obj) -> str | None:
        return obj.printer.model if obj.printer_id else None

    def get_status(self, obj) -> str:
        return warranty_status(obj, timezone.localdate())


class WarrantyUpsertSerializer(serializers.Serializer):
    purchased_on = serializers.DateField(allow_null=True, required=False)
    warranty_expires_on = serializers.DateField(allow_null=True, required=False)
    vendor_name = serializers.CharField(max_length=200, allow_blank=True, required=False)
    vendor_contact = serializers.CharField(max_length=200, allow_blank=True, required=False)


class WarrantyDocumentPresignSerializer(serializers.Serializer):
    filename = serializers.CharField(allow_blank=False, max_length=255)
    content_type = serializers.CharField(allow_blank=False, max_length=100)


class WarrantyDocumentFinalizeSerializer(serializers.Serializer):
    object_key = serializers.CharField(allow_blank=False, max_length=300)
    original_filename = serializers.CharField(allow_blank=False, max_length=255)


class WarrantyDocumentUploadResponseSerializer(serializers.Serializer):
    object_key = serializers.CharField()
    upload = serializers.DictField()


class WarrantyDocumentUrlSerializer(serializers.Serializer):
    url = serializers.URLField()


class WarrantyReportRowSerializer(serializers.Serializer):
    host_kind = serializers.CharField()
    host_id = serializers.IntegerField()
    host_label = serializers.CharField()
    serial_number = serializers.CharField(allow_null=True)
    vendor_name = serializers.CharField(allow_blank=True)
    purchased_on = serializers.DateField(allow_null=True)
    warranty_expires_on = serializers.DateField(allow_null=True)
    status = serializers.CharField()
    document_count = serializers.IntegerField()
