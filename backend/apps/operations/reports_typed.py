def typed_report_rows(report_key, rows):
    field_map = {
        "taken-items": {"product": "product", "issued_quantity": "issued_quantity"},
        "active-loans": {
            "id": "id",
            "requester": "requester",
            "status": "status",
            "issued_at": "issued_at",
        },
        "returns": {
            "id": "id",
            "requester": "requester",
            "status": "status",
            "closed_at": "closed_at",
        },
        "damaged-missing": {
            "product": "product",
            "damaged_quantity": "damaged_quantity",
            "missing_quantity": "missing_quantity",
        },
        "damaged-lost": {
            "product_name": "product_name",
            "damaged_quantity": "damaged_quantity",
            "lost_quantity": "lost_quantity",
        },
        "qr-scans": {"context": "context", "count": "count"},
        "most-lent": {
            "product_name": "product_name",
            "times_lent": "times_lent",
            "total_quantity_lent": "total_quantity_lent",
        },
        "top-borrowers": {
            "holder": "holder",
            "requests": "requests",
            "items_borrowed": "items_borrowed",
        },
        "recently-added": {
            "product_name": "product_name",
            "created_at": "created_at",
            "total_quantity": "total_quantity",
        },
    }.get(report_key)
    if not field_map or not rows:
        return []

    header = [str(cell) for cell in rows[0]]
    typed = []
    for raw_row in rows[1:]:
        item = {}
        if "makerspace_id" in header:
            item["makerspace_id"] = raw_row[header.index("makerspace_id")]
        for column, field in field_map.items():
            if column in header:
                item[field] = raw_row[header.index(column)]
        typed.append(item)
    return typed