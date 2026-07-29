"""Unit tests for shopping list tools."""

from unittest.mock import AsyncMock, patch

import pytest

from texas_grocery_mcp.models.shopping_list import (
    ShoppingListDetail,
    ShoppingListItem,
    ShoppingListsResult,
    ShoppingListSummary,
)
from texas_grocery_mcp.tools.shopping_list import (
    shopping_list_add_item,
    shopping_list_add_to_cart,
    shopping_list_create,
    shopping_list_delete,
    shopping_list_get,
    shopping_list_list,
    shopping_list_remove_item,
)

MODULE = "texas_grocery_mcp.tools.shopping_list"


def _patched_client():
    return patch(f"{MODULE}._get_client")


class TestShoppingListList:
    @pytest.mark.asyncio
    async def test_requires_auth(self):
        with patch(f"{MODULE}.is_authenticated", return_value=False):
            result = await shopping_list_list()
        assert result["error"] is True
        assert result["code"] == "AUTH_REQUIRED"
        assert result["lists"] == []

    @pytest.mark.asyncio
    async def test_returns_lists(self):
        mock_result = ShoppingListsResult(
            lists=[
                ShoppingListSummary(
                    id="list-1",
                    name="Weekly Items",
                    total_item_count=13,
                    store_number="373",
                    store_name="620 and O'Connor H-E-B",
                    updated="2026-07-28T00:00:00Z",
                )
            ],
            total=1,
        )
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.get_shopping_lists.return_value = mock_result
            mock_get_client.return_value = mock_client

            result = await shopping_list_list()

        assert result["count"] == 1
        assert result["total"] == 1
        assert result["lists"][0]["id"] == "list-1"
        assert result["lists"][0]["name"] == "Weekly Items"


class TestShoppingListGet:
    @pytest.mark.asyncio
    async def test_requires_auth(self):
        with patch(f"{MODULE}.is_authenticated", return_value=False):
            result = await shopping_list_get(list_id="list-1")
        assert result["error"] is True
        assert result["code"] == "AUTH_REQUIRED"

    @pytest.mark.asyncio
    async def test_returns_detail(self):
        mock_detail = ShoppingListDetail(
            id="list-1",
            name="Weekly Items",
            total_item_count=1,
            total_price="$5.00",
            items=[
                ShoppingListItem(
                    item_id="item-1",
                    product_id="123456",
                    sku_id="654321",
                    name="Whole Milk",
                    quantity=1,
                    price=5.0,
                )
            ],
        )
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.get_shopping_list.return_value = mock_detail
            mock_get_client.return_value = mock_client

            result = await shopping_list_get(list_id="list-1")

        assert result["id"] == "list-1"
        assert result["count"] == 1
        assert result["items"][0]["name"] == "Whole Milk"
        mock_client.get_shopping_list.assert_called_once_with("list-1", page=0, size=500)

    @pytest.mark.asyncio
    async def test_not_found(self):
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.get_shopping_list.return_value = None
            mock_get_client.return_value = mock_client

            result = await shopping_list_get(list_id="missing")

        assert result["error"] is True
        assert result["code"] == "NOT_FOUND"


class TestShoppingListCreate:
    @pytest.mark.asyncio
    async def test_requires_auth(self):
        with patch(f"{MODULE}.is_authenticated", return_value=False):
            result = await shopping_list_create(name="Test List")
        assert result["error"] is True
        assert result["code"] == "AUTH_REQUIRED"

    @pytest.mark.asyncio
    async def test_preview_without_confirm(self):
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            patch(f"{MODULE}.StateManager.get_default_store_id", return_value="373"),
        ):
            result = await shopping_list_create(name="Test List")

        assert result["preview"] is True
        assert result["name"] == "Test List"
        assert result["store_id"] == "373"

    @pytest.mark.asyncio
    async def test_no_store_available(self):
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            patch(f"{MODULE}.StateManager.get_default_store_id", return_value=None),
        ):
            result = await shopping_list_create(name="Test List")

        assert result["error"] is True
        assert result["code"] == "NO_STORE"

    @pytest.mark.asyncio
    async def test_confirm_creates_list(self):
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            patch(f"{MODULE}.StateManager.get_default_store_id", return_value="373"),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.create_shopping_list.return_value = {
                "success": True,
                "id": "new-list",
                "name": "Test List",
            }
            mock_get_client.return_value = mock_client

            result = await shopping_list_create(name="Test List", confirm=True)

        assert result["success"] is True
        mock_client.create_shopping_list.assert_called_once_with("Test List", "373")

    @pytest.mark.asyncio
    async def test_empty_name_rejected(self):
        with patch(f"{MODULE}.is_authenticated", return_value=True):
            result = await shopping_list_create(name="   ", confirm=True)
        assert result["error"] is True
        assert result["code"] == "INVALID_NAME"


class TestShoppingListAddItem:
    @pytest.mark.asyncio
    async def test_preview_without_confirm(self):
        with patch(f"{MODULE}.is_authenticated", return_value=True):
            result = await shopping_list_add_item(list_id="list-1", product_ids=["123"])
        assert result["preview"] is True
        assert result["product_ids"] == ["123"]

    @pytest.mark.asyncio
    async def test_confirm_adds_items(self):
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.add_to_shopping_list.return_value = {
                "success": True,
                "list_id": "list-1",
                "total_item_count": 2,
            }
            mock_get_client.return_value = mock_client

            result = await shopping_list_add_item(
                list_id="list-1", product_ids=["123"], confirm=True
            )

        assert result["success"] is True
        mock_client.add_to_shopping_list.assert_called_once_with("list-1", ["123"])


class TestShoppingListRemoveItem:
    @pytest.mark.asyncio
    async def test_preview_without_confirm(self):
        with patch(f"{MODULE}.is_authenticated", return_value=True):
            result = await shopping_list_remove_item(list_id="list-1", item_ids=["item-1"])
        assert result["preview"] is True
        assert result["item_ids"] == ["item-1"]

    @pytest.mark.asyncio
    async def test_confirm_removes_items(self):
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.remove_from_shopping_list.return_value = {
                "success": True,
                "list_id": "list-1",
                "total_item_count": 0,
            }
            mock_get_client.return_value = mock_client

            result = await shopping_list_remove_item(
                list_id="list-1", item_ids=["item-1"], confirm=True
            )

        assert result["success"] is True
        mock_client.remove_from_shopping_list.assert_called_once_with("list-1", ["item-1"])


class TestShoppingListDelete:
    @pytest.mark.asyncio
    async def test_preview_shows_name_and_count(self):
        mock_detail = ShoppingListDetail(id="list-1", name="Weekly Items", total_item_count=13)
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.get_shopping_list.return_value = mock_detail
            mock_get_client.return_value = mock_client

            result = await shopping_list_delete(list_id="list-1")

        assert result["preview"] is True
        assert result["name"] == "Weekly Items"
        assert result["total_item_count"] == 13
        mock_client.delete_shopping_list.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_deletes_list(self):
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.delete_shopping_list.return_value = {
                "success": True,
                "list_id": "list-1",
            }
            mock_get_client.return_value = mock_client

            result = await shopping_list_delete(list_id="list-1", confirm=True)

        assert result["success"] is True
        mock_client.delete_shopping_list.assert_called_once_with("list-1")


class TestShoppingListAddToCart:
    @pytest.mark.asyncio
    async def test_preview_without_confirm(self):
        mock_detail = ShoppingListDetail(
            id="list-1",
            name="Weekly Items",
            items=[
                ShoppingListItem(
                    item_id="item-1", product_id="123", sku_id="456", name="Milk", quantity=1
                )
            ],
        )
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.get_shopping_list.return_value = mock_detail
            mock_get_client.return_value = mock_client

            result = await shopping_list_add_to_cart(list_id="list-1")

        assert result["preview"] is True
        assert result["count"] == 1
        mock_client.add_to_cart.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_reports_partial_failure(self):
        mock_detail = ShoppingListDetail(
            id="list-1",
            name="Weekly Items",
            items=[
                ShoppingListItem(
                    item_id="item-1", product_id="123", sku_id="456", name="Milk", quantity=1
                ),
                ShoppingListItem(
                    item_id="item-2", product_id="789", sku_id=None, name="Bad Item", quantity=1
                ),
            ],
        )
        with (
            patch(f"{MODULE}.is_authenticated", return_value=True),
            _patched_client() as mock_get_client,
        ):
            mock_client = AsyncMock()
            mock_client.get_shopping_list.return_value = mock_detail
            mock_client.add_to_cart.return_value = {"success": True}
            mock_get_client.return_value = mock_client

            result = await shopping_list_add_to_cart(list_id="list-1", confirm=True)

        assert result["success"] is False
        assert result["added_count"] == 1
        assert result["failed_count"] == 1
        assert result["failed_items"][0]["name"] == "Bad Item"
        mock_client.add_to_cart.assert_called_once_with(
            product_id="123", sku_id="456", quantity=1
        )
