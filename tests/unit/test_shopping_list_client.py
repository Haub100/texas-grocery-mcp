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


# ---------------------------------------------------------------------------
# Bearer/mobile routing
#
# Shopping-list ops prefer the mobile bearer path (no Incapsula/reese84). The
# mobile variable shapes differ from web — sort is STORE_LOCATION and adds
# carry an explicit quantity — so these assert the request side, not just that
# a call happened. Hashes/op names captured from live MyHEB traffic 2026-07-29.
# ---------------------------------------------------------------------------


def _bearer(client, monkeypatch, data: dict) -> AsyncMock:
    """Force the bearer path and capture what it was called with."""
    spy = AsyncMock(return_value=data)
    monkeypatch.setattr(client, "_bearer_available", lambda: True)
    monkeypatch.setattr(client, "_execute_bearer_query", spy)
    return spy


def test_mobile_ops_cover_all_shopping_list_operations():
    from texas_grocery_mcp.clients.graphql import MOBILE_OPS

    for web_op in (
        "getShoppingListsV2",
        "getShoppingListV2",
        "createShoppingList",
        "addToShoppingListV2",
        "deleteShoppingListItems",
        "deleteShoppingLists",
    ):
        mobile_op, mobile_hash = MOBILE_OPS[web_op]
        assert mobile_op and len(mobile_hash) == 64


@pytest.mark.asyncio
async def test_get_shopping_lists_prefers_bearer(client, monkeypatch):
    data = {
        "getShoppingListsV2": {
            "thisPage": {"totalCount": 1},
            "lists": [
                {
                    "id": "list-1",
                    "name": "Weekly Items",
                    "totalItemCount": 3,
                    "updated": "2026-07-29T00:00:00Z",
                    "fulfillment": {"store": {"storeNumber": 373, "name": "620 H-E-B"}},
                }
            ],
        }
    }
    spy = _bearer(client, monkeypatch, data)
    # The web client must never be consulted when bearer tokens exist.
    with patch.object(client, "_get_authenticated_client") as web:
        result = await client.get_shopping_lists()

    web.assert_not_called()
    spy.assert_awaited_once_with("getShoppingListsV2", {"page": {}})
    assert result.lists[0].id == "list-1"


@pytest.mark.asyncio
async def test_get_shopping_list_bearer_sorts_by_store_location(client, monkeypatch):
    data = {
        "getShoppingListV2": {
            "id": "list-1",
            "name": "Weekly Items",
            "totalItemCount": 0,
            "itemPage": {"items": []},
        }
    }
    spy = _bearer(client, monkeypatch, data)
    await client.get_shopping_list("list-1")

    variables = spy.await_args.args[1]
    assert variables["input"]["page"]["sort"] == "STORE_LOCATION"


@pytest.mark.asyncio
async def test_add_to_shopping_list_bearer_sends_quantity(client, monkeypatch):
    data = {
        "addShoppingListItemsV2": {
            "id": "list-1",
            "name": "Weekly Items",
            "totalItemCount": 1,
            "total": {"formattedPrice": "$4.29"},
        }
    }
    spy = _bearer(client, monkeypatch, data)
    result = await client.add_to_shopping_list("list-1", ["314125"])

    variables = spy.await_args.args[1]
    assert variables["input"]["listItems"] == [
        {"item": {"productId": "314125"}, "quantityOrWeight": {"quantity": 1}}
    ]
    assert variables["input"]["page"]["sort"] == "STORE_LOCATION"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_shopping_list_bearer_token_failure_is_auth_error(client, monkeypatch):
    """A missing/unrefreshable token must not be parsed as list data."""
    _bearer(
        client,
        monkeypatch,
        {"error": True, "code": "NOT_AUTHENTICATED", "message": "Login required"},
    )
    result = await client.create_shopping_list("Weekly Items", "373")

    assert result["error"] is True
    assert result["code"] == "NOT_AUTHENTICATED"


# ---------------------------------------------------------------------------
# Persisted-query miss retry on the bearer path
# ---------------------------------------------------------------------------


def _pq_miss() -> dict:
    return {
        "errors": [
            {
                "message": "PersistedQueryNotFound",
                "extensions": {"code": "PERSISTED_QUERY_NOT_FOUND"},
            }
        ]
    }


def _bearer_http(client, monkeypatch, responses: list[dict]) -> AsyncMock:
    """Drive _execute_bearer_query against a scripted sequence of HTTP bodies."""
    post = AsyncMock(
        side_effect=[
            MagicMock(json=MagicMock(return_value=body), raise_for_status=MagicMock())
            for body in responses
        ]
    )
    monkeypatch.setattr(client, "_get_bearer_client", AsyncMock(return_value=MagicMock(post=post)))
    monkeypatch.setattr(
        "texas_grocery_mcp.auth.oauth.ensure_access_token", lambda _dir: "token-abc"
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    return post


@pytest.mark.asyncio
async def test_bearer_retries_persisted_query_miss(client, monkeypatch):
    """A hash miss should resolve itself without the caller invoking the tool twice."""
    post = _bearer_http(
        client,
        monkeypatch,
        [_pq_miss(), {"data": {"getShoppingListsV2": {"lists": [], "thisPage": {}}}}],
    )
    result = await client._execute_bearer_query("getShoppingListsV2", {"page": {}})

    assert post.await_count == 2
    assert result == {"getShoppingListsV2": {"lists": [], "thisPage": {}}}


@pytest.mark.asyncio
async def test_bearer_gives_up_after_max_attempts(client, monkeypatch):
    """A genuinely rotated hash never recovers — fail rather than retry forever."""
    from texas_grocery_mcp.clients.graphql import MOBILE_PQ_MAX_ATTEMPTS, GraphQLError

    post = _bearer_http(client, monkeypatch, [_pq_miss()] * MOBILE_PQ_MAX_ATTEMPTS)
    with pytest.raises(GraphQLError):
        await client._execute_bearer_query("getShoppingListsV2", {"page": {}})

    assert post.await_count == MOBILE_PQ_MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_bearer_does_not_retry_other_graphql_errors(client, monkeypatch):
    """Only hash misses are safe to replay; a real error must surface immediately."""
    from texas_grocery_mcp.clients.graphql import GraphQLError

    post = _bearer_http(client, monkeypatch, [{"errors": [{"message": "Item not found"}]}])
    with pytest.raises(GraphQLError):
        await client._execute_bearer_query("deleteShoppingLists", {"input": {"ids": ["x"]}})

    assert post.await_count == 1
