from apps.hardware_requests.asset_link_models import HardwareRequestItemAsset
from apps.hardware_requests.display import requester_label
from apps.hardware_requests.models import HardwareRequest
from apps.hardware_requests.self_checkout_models import PublicToolLoan
from apps.inventory.models import InventoryAsset

EXPORT_HEADER = [
    "source",
    "item_name",
    "container",
    "holder",
    "quantity",
    "units",
    "target_label",
    "since",
    "due",
    "makerspace_id",
    "reference_id",
    "status",
]


def materialize_rows(queryset):
    rows = [dict(row) for row in queryset]
    if not rows:
        return []
    holder_map = _request_holder_map(row["ledger_request_id"] for row in rows)
    unit_map = _unit_map(rows)
    return [_public_row(row, holder_map, unit_map) for row in rows]


def export_rows(rows):
    exported = [EXPORT_HEADER]
    for row in rows:
        exported.append(
            [
                row["source"],
                row["item_name"],
                row.get("container") or "",
                row["holder"],
                row["quantity"],
                _unit_export_label(row["units"]),
                row.get("target_label") or "",
                row.get("since"),
                row.get("due"),
                row["makerspace_id"],
                row["reference_id"],
                row["status"],
            ]
        )
    return exported


def _public_row(row, holder_map, unit_map):
    return {
        "source": row["ledger_source"],
        "item_name": row["ledger_item_name"],
        "container": row["ledger_container"],
        "holder": holder_map.get(row["ledger_request_id"], "Member"),
        "quantity": row["quantity"],
        "units": unit_map.get(_row_key(row), []),
        "target_label": row["ledger_target_label"],
        "since": row["since"],
        "due": row["due"],
        "makerspace_id": row["ledger_makerspace_id"],
        "reference_id": row["reference_id"],
        "status": row["ledger_status"],
    }


def _request_holder_map(request_ids):
    unique_ids = {request_id for request_id in request_ids if request_id}
    if not unique_ids:
        return {}
    return {
        request.id: requester_label(request, fallback="Member", allow_internal_fallback=True)
        for request in HardwareRequest.objects.filter(pk__in=unique_ids).select_related("requester")
    }


def _unit_map(rows):
    units = {}
    units.update(_linked_asset_units(row for row in rows if row["ledger_item_id"] and not row["loan_id"]))
    units.update(_loan_asset_units(row for row in rows if row["ledger_item_id"] and row["loan_id"]))
    return units


def _linked_asset_units(rows):
    rows = list(rows)
    item_ids = [row["ledger_item_id"] for row in rows]
    if not item_ids:
        return {}
    unit_map = {_row_key(row): [] for row in rows}
    key_by_item = {row["ledger_item_id"]: _row_key(row) for row in rows}
    links = (
        HardwareRequestItemAsset.objects.filter(
            request_item_id__in=item_ids,
            outcome=HardwareRequestItemAsset.Outcome.ISSUED,
        )
        .select_related("asset")
        .order_by("id")
    )
    for link in links:
        unit_map[key_by_item[link.request_item_id]].append(_asset_unit(link.asset))
    return unit_map


def _loan_asset_units(rows):
    rows = list(rows)
    loan_ids = {row["loan_id"] for row in rows}
    if not loan_ids:
        return {}
    loans = {loan.id: loan.asset_ids or [] for loan in PublicToolLoan.objects.filter(pk__in=loan_ids)}
    asset_ids = {asset_id for ids in loans.values() for asset_id in ids}
    if not asset_ids:
        return {_row_key(row): [] for row in rows}
    makerspace_ids = {row["ledger_makerspace_id"] for row in rows}
    assets = {
        asset.id: asset
        for asset in InventoryAsset.objects.filter(
            pk__in=asset_ids,
            makerspace_id__in=makerspace_ids,
        )
    }
    return {_row_key(row): _loan_units(row, loans, assets) for row in rows}


def _loan_units(row, loans, assets):
    row_units = []
    for asset_id in loans.get(row["loan_id"], []):
        asset = assets.get(asset_id)
        if asset and asset.product_id == row["ledger_product_id"] and asset.makerspace_id == row["ledger_makerspace_id"]:
            row_units.append(_asset_unit(asset))
    return row_units


def _asset_unit(asset):
    return {"asset_tag": asset.asset_tag, "serial_number": asset.serial_number}


def _row_key(row):
    return (row["ledger_source"], row["ledger_request_id"], row["ledger_item_id"], row["loan_id"])


def _unit_export_label(units):
    return "; ".join(
        f"{unit['asset_tag']} ({unit['serial_number']})" if unit.get("serial_number") else unit["asset_tag"]
        for unit in units
    )
