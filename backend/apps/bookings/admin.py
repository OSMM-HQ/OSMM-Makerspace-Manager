from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.bookings.models import BookableSpace, Booking
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(BookableSpace)
class BookableSpaceAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = (
        'name',
        'makerspace',
        'is_active',
        'is_public',
        'show_public_availability',
        'show_public_booker_names',
    )
    list_filter = (
        'is_active',
        'is_public',
        'show_public_availability',
        'show_public_booker_names',
    )
    readonly_fields = tuple(field.name for field in BookableSpace._meta.fields)
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ('booker_name', 'space', 'starts_at', 'ends_at', 'status')
    list_filter = ('status',)
    readonly_fields = tuple(field.name for field in Booking._meta.fields)
    fields = readonly_fields

    @admin.display(description='Name')
    def booker_name(self, obj):
        return obj.name

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
