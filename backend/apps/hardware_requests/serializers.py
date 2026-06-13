from rest_framework import serializers


class RequestItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class RequestSubmitSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    contact_email = serializers.EmailField(
        required=False,
        allow_blank=True,
        default="",
    )
    contact_phone = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=32,
    )
    requested_for = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )
    items = RequestItemInputSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        product_ids = [item["product_id"] for item in attrs["items"]]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError(
                {"items": "Duplicate product_id values are not allowed."}
            )
        if not attrs["contact_email"].strip() and not attrs["contact_phone"].strip():
            raise serializers.ValidationError(
                {"contact": "Email or phone number is required."}
            )
        return attrs


class RequestSubmitResponseSerializer(serializers.Serializer):
    public_token = serializers.UUIDField(read_only=True)
    status = serializers.CharField(read_only=True)


class PublicRequestItemStatusSerializer(serializers.Serializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    requested_quantity = serializers.IntegerField(read_only=True)


class PublicRequestStatusSerializer(serializers.Serializer):
    # Public + token-addressable: deliberately omits requester_username. The check-in
    # identity may be a name / email / badge / student id (PII), and the requester does
    # not need their own identity echoed back to learn a request's status.
    status = serializers.CharField(read_only=True)
    rejection_reason = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    items = PublicRequestItemStatusSerializer(many=True, read_only=True)


class PublicRequestLookupSerializer(serializers.Serializer):
    identifier = serializers.CharField()


class PublicRequestListItemSerializer(PublicRequestStatusSerializer):
    public_token = serializers.UUIDField(read_only=True)
    requested_for = serializers.CharField(read_only=True)


class CheckinVerifyRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()


class CheckinVerifyResponseSerializer(serializers.Serializer):
    username = serializers.CharField()


class AdminRequestItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    product_id = serializers.IntegerField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    requested_quantity = serializers.IntegerField(read_only=True)
    accepted_quantity = serializers.IntegerField(read_only=True)
    issued_quantity = serializers.IntegerField(read_only=True)
    returned_quantity = serializers.IntegerField(read_only=True)
    damaged_quantity = serializers.IntegerField(read_only=True)
    missing_quantity = serializers.IntegerField(read_only=True)


class AdminRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    makerspace_id = serializers.IntegerField(read_only=True)
    requester_username = serializers.CharField(read_only=True)
    requester_contact_email = serializers.EmailField(read_only=True)
    requester_contact_phone = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    requested_for = serializers.CharField(read_only=True)
    rejection_reason = serializers.CharField(read_only=True)
    assigned_box_label = serializers.CharField(
        source="assigned_box.label",
        read_only=True,
        allow_null=True,
    )
    accepted_at = serializers.DateTimeField(read_only=True)
    issued_at = serializers.DateTimeField(read_only=True)
    return_due_at = serializers.DateTimeField(read_only=True)
    return_reminder_sent_at = serializers.DateTimeField(read_only=True)
    closed_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    items = AdminRequestItemSerializer(many=True, read_only=True)


class RejectRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class AssignBoxSerializer(serializers.Serializer):
    box_code = serializers.CharField()


class IssueRequestSerializer(serializers.Serializer):
    evidence_id = serializers.IntegerField()
    remark = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class ReturnDueSerializer(serializers.Serializer):
    return_due_at = serializers.DateTimeField(allow_null=True)


class ReturnItemResolutionSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    returned = serializers.IntegerField(min_value=0, default=0)
    damaged = serializers.IntegerField(min_value=0, default=0)
    missing = serializers.IntegerField(min_value=0, default=0)


class ReturnRequestSerializer(serializers.Serializer):
    evidence_id = serializers.IntegerField()
    box_code = serializers.CharField()
    remark = serializers.CharField(allow_blank=False, trim_whitespace=True)
    resolutions = ReturnItemResolutionSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        item_ids = [resolution["item_id"] for resolution in attrs["resolutions"]]
        if len(item_ids) != len(set(item_ids)):
            raise serializers.ValidationError(
                {"resolutions": "Duplicate item_id values are not allowed."}
            )
        for resolution in attrs["resolutions"]:
            if (
                resolution["returned"]
                + resolution["damaged"]
                + resolution["missing"]
            ) == 0:
                raise serializers.ValidationError(
                    {"resolutions": "Each resolution must resolve at least one item."}
                )
        return attrs
