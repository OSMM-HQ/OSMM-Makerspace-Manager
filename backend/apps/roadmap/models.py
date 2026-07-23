from django.db import models


class RoadmapItem(models.Model):
    class Status(models.TextChoices):
        SHIPPED = "shipped", "Shipped"
        IN_PROGRESS = "in_progress", "In progress"
        PLANNED = "planned", "Planned"

    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    category = models.CharField(max_length=100, blank=True)
    order = models.IntegerField(default=0)
    is_public = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "-published_at", "id"]

    def __str__(self):
        return self.title
