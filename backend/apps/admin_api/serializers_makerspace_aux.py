from rest_framework import serializers

from apps.makerspaces.models import Makerspace


class MakerspaceSwitcherSerializer(serializers.ModelSerializer):
    """Minimal makerspace row for the staff console switcher."""

    class Meta:
        model = Makerspace
        fields = [
            "id",
            "name",
            "public_code",
            "slug",
            "telegram_group_chat_id",
            # Module flags are frontend-safe (already in the public bootstrap) and are
            # required so the console can gate module tabs (Machines, Events, ...) for a
            # switcher-slim role such as machine_manager / print_manager.
            "enabled_modules",
        ]
        read_only_fields = fields


class MakerspaceDisabledRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Makerspace
        fields = [
            "id",
            "name",
            "slug",
            "public_code",
            "location",
            "superadmin_access_enabled",
        ]
        read_only_fields = fields


class ReturnPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Makerspace
        fields = ["id", "default_loan_days"]
        read_only_fields = ["id"]

    def validate_default_loan_days(self, value):
        if value < 1:
            raise serializers.ValidationError("Default loan days must be at least 1.")
        return value