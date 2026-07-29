"""Tests for HEBGraphQLClient shopping list methods."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from texas_grocery_mcp.clients.graphql import HEBGraphQLClient


@pytest.fixture
def client():
    return HEBGraphQLClient()


def _mock_auth_client(response_json: dict) -> MagicMock:
    mock_auth_client = MagicMock()
    mock_auth_client.post = AsyncMock(
        return_value=MagicMock(
            json=MagicMock(return_value=response_json),
            raise_for_status=MagicMock(),
        )
    )
    return mock_auth_client


@pytest.mark.asyncio
async def test_get_shopping_lists_success(client):
    response = {
        "data": {
            "getShoppingListsV2": {
                "thisPage": {"totalCount": 1},
                "lists": [
                    {
                        "id": "list-1",
                        "name": "Weekly Items",
                        "totalItemCount": 13,
                        "updated": "2026-07-28T00:00:00Z",
                        "fulfillment": {"store": {"storeNumber": 373, "name": "620 H-E-B"}},
                    }
                ],
            }
        }
    }
    mock_client = _mock_auth_client(response)
    with patch.object(client, "_get_authenticated_client", return_value=mock_client):
        result = await client.get_shopping_lists()

    assert result.total == 1
    assert len(result.lists) == 1
    assert result.lists[0].id == "list-1"
    assert result.lists[0].store_number == "373"


@pytest.mark.asyncio
async def test_get_shopping_lists_no_auth(client):
    with patch.object(client, "_get_authenticated_client", return_value=None):
        result = await client.get_shopping_lists()

    assert result.lists == []
    assert result.total == 0


@pytest.mark.asyncio
async def test_get_shopping_list_success(client):
    response = {
        "data": {
            "getShoppingListV2": {
                "id": "list-1",
                "name": "Weekly Items",
                "totalItemCount": 1,
                "total": {"formattedPrice": "$5.00"},
                "itemPage": {
                    "items": [
                        {
                            "id": "item-1",
                            "quantity": 1,
                            "groupHeader": "Dairy",
                            "checked": False,
                            "note": None,
                            "itemPrice": {
                                "listPrice": 5.0,
                                "totalAmount": 5.0,
                                "onSale": False,
                            },
                            "product": {
                                "id": "123456",
                                "fullDisplayName": "Whole Milk",
                                "brand": {"name": "H-E-B"},
                                "SKUs": [
                                    {"id": "654321", "customerFriendlySize": "1 gal"}
                                ],
                                "inventory": {"inventoryState": "IN_STOCK"},
                                "productLocation": {"location": "Aisle 3"},
                            },
                        }
                    ]
                },
            }
        }
    }
    mock_client = _mock_auth_client(response)
    with patch.object(client, "_get_authenticated_client", return_value=mock_client):
        detail = await client.get_shopping_list("list-1")

    assert detail is not None
    assert detail.id == "list-1"
    assert detail.total_item_count == 1
    assert len(detail.items) == 1
    assert detail.items[0].name == "Whole Milk"
    assert detail.items[0].sku_id == "654321"
    assert detail.items[0].in_stock is True


@pytest.mark.asyncio
async def test_get_shopping_list_not_found(client):
    response = {"data": {"getShoppingListV2": None}}
    mock_client = _mock_auth_client(response)
    with patch.object(client, "_get_authenticated_client", return_value=mock_client):
        detail = await client.get_shopping_list("missing")

    assert detail is None


@pytest.mark.asyncio
async def test_create_shopping_list_success(client):
    response = {
        "data": {"createShoppingListV2": {"id": "new-list", "name": "Test List"}}
    }
    mock_client = _mock_auth_client(response)
    with patch.object(client, "_get_authenticated_client", return_value=mock_client):
        result = await client.create_shopping_list("Test List", "373")

    assert result["success"] is True
    assert result["id"] == "new-list"


@pytest.mark.asyncio
async def test_add_to_shopping_list_success(client):
    response = {
        "data": {
            "addShoppingListItemsV2": {
                "id": "list-1",
                "name": "Weekly Items",
                "totalItemCount": 2,
                "total": {"formattedPrice": "$10.00"},
            }
        }
    }
    mock_client = _mock_auth_client(response)
    with patch.object(client, "_get_authenticated_client", return_value=mock_client):
        result = await client.add_to_shopping_list("list-1", ["123456"])

    assert result["success"] is True
    assert result["total_item_count"] == 2


@pytest.mark.asyncio
async def test_remove_from_shopping_list_success(client):
    response = {
        "data": {
            "deleteShoppingListItemsV2": {
                "id": "list-1",
                "name": "Weekly Items",
                "totalItemCount": 0,
                "total": {"formattedPrice": "$0.00"},
            }
        }
    }
    mock_client = _mock_auth_client(response)
    with patch.object(client, "_get_authenticated_client", return_value=mock_client):
        result = await client.remove_from_shopping_list("list-1", ["item-1"])

    assert result["success"] is True
    assert result["total_item_count"] == 0


@pytest.mark.asyncio
async def test_delete_shopping_list_success(client):
    response = {"data": {"deleteShoppingLists": {}}}
    mock_client = _mock_auth_client(response)
    with patch.object(client, "_get_authenticated_client", return_value=mock_client):
        result = await client.delete_shopping_list("list-1")

    assert result["success"] is True
    assert result["list_id"] == "list-1"


@pytest.mark.asyncio
async def test_delete_shopping_list_no_auth(client):
    with patch.object(client, "_get_authenticated_client", return_value=None):
        result = await client.delete_shopping_list("list-1")

    assert result["error"] is True
    assert result["code"] == "NOT_AUTHENTICATED"
