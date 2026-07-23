from rest_framework import serializers


class MemberSignUpSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=200, trim_whitespace=True)
    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")
    password = serializers.CharField(max_length=128, write_only=True)
    website = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_display_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value


class EmailVerificationConfirmSerializer(serializers.Serializer):
    # Code-only: the endpoint is authenticated, so the caller's active challenge is
    # resolved from request.user + their current email. No challenge_id is exposed
    # (signup/resend return generic acks and the email carries only the code), and we
    # never touch another user's challenge.
    code = serializers.CharField(max_length=6)
