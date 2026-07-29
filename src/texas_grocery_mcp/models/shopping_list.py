"""Shopping list data models."""

from pydantic import BaseModel, Field


class ShoppingListSummary(BaseModel):
    """Summary of an HEB shopping list (from the lists index)."""

    id: str = Field(description="Shopping list UUID")
    name: str = Field(description="List name")
    total_item_count: int = Field(default=0, description="Number of items in the list")
    store_number: str | None = Field(default=None, description="Associated HEB store number")
    store_name: str | None = Field(default=None, description="Associated HEB store name")
    updated: str | None = Field(default=None, description="Last-updated timestamp")


class ShoppingListsResult(BaseModel):
    """Result of listing all shopping lists."""

    lists: list[ShoppingListSummary] = Field(default_factory=list)
    total: int = Field(default=0, description="Total number of shopping lists")


class ShoppingListItem(BaseModel):
    """An item within a shopping list."""

    item_id: str = Field(description="Item ID within the list (used to remove the item)")
    product_id: str | None = Field(default=None, description="HEB product ID")
    sku_id: str | None = Field(default=None, description="HEB SKU ID")
    name: str | None = Field(default=None, description="Product display name")
    brand: str | None = Field(default=None, description="Brand name")
    size: str | None = Field(default=None, description="Customer-friendly size")
    quantity: int | None = Field(default=None, description="Quantity")
    category: str | None = Field(default=None, description="Category/group header")
    checked: bool | None = Field(default=None, description="Whether the item is checked off")
    note: str | None = Field(default=None, description="Note attached to the item")
    price: float | None = Field(default=None, description="List price")
    total_price: float | None = Field(default=None, description="Total price for the quantity")
    on_sale: bool = Field(default=False, description="Whether the item is on sale")
    in_stock: bool | None = Field(default=None, description="Inventory status")
    aisle: str | None = Field(default=None, description="Aisle/location in store")


class ShoppingListDetail(BaseModel):
    """Full contents of a single shopping list."""

    id: str = Field(description="Shopping list UUID")
    name: str = Field(description="List name")
    total_item_count: int = Field(default=0, description="Number of items in the list")
    total_price: str | None = Field(default=None, description="Formatted total price")
    items: list[ShoppingListItem] = Field(default_factory=list)
