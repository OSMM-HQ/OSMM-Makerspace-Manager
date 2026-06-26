from django.db.models import F, Q


def apply_inventory_list_filters(queryset, query_params):
    archived = query_params.get("archived")
    if archived in {"true", "false"}:
        queryset = queryset.filter(is_archived=(archived == "true"))
    q = (query_params.get("q") or "").strip()
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(tracking_mode__icontains=q)
            | Q(storage_location__icontains=q)
            | Q(category__name__icontains=q)
        )
    if query_params.get("low_stock") == "true":
        queryset = queryset.annotate(available_x5=F("available_quantity") * 5).filter(
            available_x5__lte=F("total_quantity")
        )
    return queryset
