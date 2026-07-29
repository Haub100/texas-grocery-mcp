"""Shopping-list MCP tools with human-in-the-loop confirmation."""

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from texas_grocery_mcp.auth.session import ensure_session, is_authenticated
from texas_grocery_mcp.state import StateManager

if TYPE_CHECKING:
    from texas_grocery_mcp.clients.graphql import HEBGraphQLClient

_AUTH_ERROR_MESSAGE = (
    "Authentication required for shopping lists. Use session_save_instructions to log in."
)


def _get_client() -> "HEBGraphQLClient":
    """Get or create GraphQL client."""
    return StateManager.get_graphql_client_sync()


def _auth_error(**extra: Any) -> dict[str, Any]:
    return {"error": True, "code": "AUTH_REQUIRED", "message": _AUTH_ERROR_MESSAGE, **extra}


@ensure_session
async def shopping_list_list() -> dict[str, Any]:
    """List all of your HEB shopping lists.

    Returns each list's ID, name, item count, and associated store. Use
    shopping_list_get with a list's ID to see its items.
    """
    if not is_authenticated():
        return _auth_error(lists=[], count=0)

    client = _get_client()
    result = await client.get_shopping_lists()

    return {
        "lists": [
            {
                "id": lst.id,
                "name": lst.name,
                "total_item_count": lst.total_item_count,
                "store_number": lst.store_number,
                "store_name": lst.store_name,
                "updated": lst.updated,
            }
            for lst in result.lists
        ],
        "count": len(result.lists),
        "total": result.total,
    }


@ensure_session
async def shopping_list_get(
    list_id: Annotated[str, Field(description="Shopping list UUID (from shopping_list_list)")],
    page: Annotated[int, Field(description="Page number for item pagination", ge=0)] = 0,
    size: Annotated[int, Field(description="Items per page", ge=1, le=500)] = 500,
) -> dict[str, Any]:
    """Get the full contents of a single shopping list.

    Returns item names, prices, quantities, categories, stock status, and
    aisle locations.
    """
    if not is_authenticated():
        return _auth_error(items=[], count=0)

    client = _get_client()
    detail = await client.get_shopping_list(list_id, page=page, size=size)
    if detail is None:
        return {
            "error": True,
            "code": "NOT_FOUND",
            "message": f"Shopping list {list_id} not found.",
            "items": [],
            "count": 0,
        }

    return {
        "id": detail.id,
        "name": detail.name,
        "total_item_count": detail.total_item_count,
        "total_price": detail.total_price,
        "items": [
            {
                "item_id": item.item_id,
                "product_id": item.product_id,
                "sku_id": item.sku_id,
                "name": item.name,
                "brand": item.brand,
                "size": item.size,
                "quantity": item.quantity,
                "category": item.category,
                "checked": item.checked,
                "note": item.note,
                "price": item.price,
                "total_price": item.total_price,
                "on_sale": item.on_sale,
                "in_stock": item.in_stock,
                "aisle": item.aisle,
            }
            for item in detail.items
        ],
        "count": len(detail.items),
    }


@ensure_session
async def shopping_list_create(
    name: Annotated[str, Field(description="Name for the new list", min_length=1)],
    store_id: Annotated[
        str | None,
        Field(
            description="HEB store number to associate with the list (defaults to your set store)"
        ),
    ] = None,
    confirm: Annotated[bool, Field(description="Set to true to confirm the action")] = False,
) -> dict[str, Any]:
    """Create a new HEB shopping list.

    Without confirm=true, returns a preview of the action.
    With confirm=true, creates the list (requires authentication).
    """
    if not is_authenticated():
        return _auth_error()

    name = name.strip()
    if not name:
        return {"error": True, "code": "INVALID_NAME", "message": "List name cannot be empty."}

    resolved_store_id = store_id or StateManager.get_default_store_id()
    if not resolved_store_id:
        return {
            "error": True,
            "code": "NO_STORE",
            "message": "No store set. Provide store_id or call store_change first.",
        }

    if not confirm:
        return {
            "preview": True,
            "name": name,
            "store_id": resolved_store_id,
            "message": "Ready to create this list. Set confirm=true to proceed.",
        }

    client = _get_client()
    return await client.create_shopping_list(name, resolved_store_id)


@ensure_session
async def shopping_list_add_item(
    list_id: Annotated[str, Field(description="Shopping list UUID (from shopping_list_list)")],
    product_ids: Annotated[
        list[str],
        Field(description="Product IDs to add (from product_search)", min_length=1),
    ],
    confirm: Annotated[bool, Field(description="Set to true to confirm the action")] = False,
) -> dict[str, Any]:
    """Add products to an HEB shopping list.

    Without confirm=true, returns a preview of the action.
    With confirm=true, adds the items (requires authentication).
    """
    if not is_authenticated():
        return _auth_error()

    if not confirm:
        return {
            "preview": True,
            "list_id": list_id,
            "product_ids": product_ids,
            "message": (
                f"Ready to add {len(product_ids)} item(s) to this list. "
                "Set confirm=true to proceed."
            ),
        }

    client = _get_client()
    return await client.add_to_shopping_list(list_id, product_ids)


@ensure_session
async def shopping_list_remove_item(
    list_id: Annotated[str, Field(description="Shopping list UUID")],
    item_ids: Annotated[
        list[str],
        Field(
            description=(
                "Item IDs to remove (from shopping_list_get's item_id field, "
                "NOT product IDs)"
            ),
            min_length=1,
        ),
    ],
    confirm: Annotated[bool, Field(description="Set to true to confirm the action")] = False,
) -> dict[str, Any]:
    """Remove items from an HEB shopping list.

    Without confirm=true, returns a preview of the action.
    With confirm=true, removes the items (requires authentication).
    """
    if not is_authenticated():
        return _auth_error()

    if not confirm:
        return {
            "preview": True,
            "list_id": list_id,
            "item_ids": item_ids,
            "message": (
                f"Ready to remove {len(item_ids)} item(s) from this list. "
                "Set confirm=true to proceed."
            ),
        }

    client = _get_client()
    return await client.remove_from_shopping_list(list_id, item_ids)


@ensure_session
async def shopping_list_delete(
    list_id: Annotated[str, Field(description="Shopping list UUID to delete")],
    confirm: Annotated[bool, Field(description="Set to true to confirm the action")] = False,
) -> dict[str, Any]:
    """Delete an entire HEB shopping list.

    Without confirm=true, returns a preview showing the list's name and item
    count so you know what you're about to delete. With confirm=true,
    permanently deletes the list (requires authentication).
    """
    if not is_authenticated():
        return _auth_error()

    client = _get_client()

    if not confirm:
        detail = await client.get_shopping_list(list_id)
        if detail is None:
            return {
                "error": True,
                "code": "NOT_FOUND",
                "message": f"Shopping list {list_id} not found.",
            }
        return {
            "preview": True,
            "list_id": list_id,
            "name": detail.name,
            "total_item_count": detail.total_item_count,
            "message": (
                f'Ready to permanently delete "{detail.name}" '
                f"({detail.total_item_count} item(s)). Set confirm=true to proceed."
            ),
        }

    return await client.delete_shopping_list(list_id)


@ensure_session
async def shopping_list_add_to_cart(
    list_id: Annotated[str, Field(description="Shopping list UUID")],
    confirm: Annotated[bool, Field(description="Set to true to confirm the action")] = False,
) -> dict[str, Any]:
    """Add all items from a shopping list to your cart.

    Without confirm=true, returns a preview of the items that would be added.
    With confirm=true, adds each item to the cart individually and reports
    which succeeded/failed (items missing a sku_id, e.g. out-of-stock
    products, are skipped and reported as failures).
    """
    if not is_authenticated():
        return _auth_error()

    client = _get_client()
    detail = await client.get_shopping_list(list_id)
    if detail is None:
        return {
            "error": True,
            "code": "NOT_FOUND",
            "message": f"Shopping list {list_id} not found.",
        }

    if not confirm:
        return {
            "preview": True,
            "list_id": list_id,
            "name": detail.name,
            "items": [
                {"name": item.name, "product_id": item.product_id, "quantity": item.quantity}
                for item in detail.items
            ],
            "count": len(detail.items),
            "message": (
                f"Ready to add {len(detail.items)} item(s) to your cart. "
                "Set confirm=true to proceed."
            ),
        }

    added_items = []
    failed_items = []
    for item in detail.items:
        if not item.product_id or not item.sku_id:
            failed_items.append({"name": item.name, "reason": "missing product_id or sku_id"})
            continue
        try:
            result = await client.add_to_cart(
                product_id=item.product_id,
                sku_id=item.sku_id,
                quantity=item.quantity or 1,
            )
            if result.get("error"):
                failed_items.append({"name": item.name, "reason": result.get("message")})
            else:
                added_items.append({"name": item.name, "product_id": item.product_id})
        except Exception as e:  # noqa: BLE001
            failed_items.append({"name": item.name, "reason": str(e)})

    return {
        "success": not failed_items,
        "list_id": list_id,
        "added_count": len(added_items),
        "added_items": added_items,
        "failed_count": len(failed_items),
        "failed_items": failed_items,
    }
