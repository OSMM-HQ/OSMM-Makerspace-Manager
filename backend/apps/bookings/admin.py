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
    readonly_fields = ('public_token', 'image_key', 'created_at', 'updated_at')


@admin.register(Booking)
class BookingAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ('name', 'space', 'starts_at', 'ends_at', 'status')
    list_filter = ('status',)
    readonly_fields = ('public_token', 'created_at')
