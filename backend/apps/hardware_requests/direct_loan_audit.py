from apps.audit import services as audit


def record_item_logs(actor, action, makerspace, request, loan):
    items = list(request.items.select_related("product"))
    if not items and loan.container_id:
        audit.record(
            actor,
            action,
            makerspace=makerspace,
            target=loan.container,
            meta={
                "loan_id": loan.id,
                "request_id": request.id,
                "container_id": loan.container_id,
                "source": loan.source,
            },
        )
        return

    for item in items:
        audit.record(
            actor,
            action,
            makerspace=makerspace,
            target=item.product,
            meta={
                "loan_id": loan.id,
                "request_id": request.id,
                "product_id": item.product_id,
                "quantity": item.issued_quantity,
                "source": loan.source,
            },
        )
