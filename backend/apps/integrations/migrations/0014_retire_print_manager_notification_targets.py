from django.db import migrations


def retarget_print_manager_mutes(apps, schema_editor):
    EmailNotificationMute = apps.get_model("integrations", "EmailNotificationMute")

    print_mutes = list(
        EmailNotificationMute.objects.select_for_update().filter(target="print_manager")
    )
    for mute in print_mutes:
        duplicate = (
            EmailNotificationMute.objects.select_for_update()
            .filter(
                makerspace_id=mute.makerspace_id,
                target="machine_manager",
                stream=mute.stream,
                event=mute.event,
            )
            .exists()
        )
        if duplicate:
            mute.delete()
        else:
            mute.target = "machine_manager"
            mute.save(update_fields=["target"])


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0013_notificationfeature_members"),
        ("makerspaces", "0046_retire_print_manager"),
    ]

    operations = [
        migrations.RunPython(retarget_print_manager_mutes, migrations.RunPython.noop),
    ]
