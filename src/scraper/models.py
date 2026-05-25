from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class MenuItemSchema(BaseModel):
    id: str = ""
    name: str = Field(..., description="Name of the menu item")
    description: Optional[str] = Field(None, description="Description of the menu item")
    image: Optional[str] = None
    imageFilename: Optional[str] = None
    price: float = Field(0.0, description="Price of the menu item")
    subSelections: List = []


class MenuSectionSchema(BaseModel):
    id: Optional[str] = None
    name: str = ""
    description: str = ""
    items: List[MenuItemSchema] = []


class MenuSchema(BaseModel):
    menuGroupId: Optional[str] = None
    type: List[str] = ["delivery"]
    description: str = ""
    sections: List[MenuSectionSchema] = []


class AddressSchema(BaseModel):
    city: str = ""
    firstLine: str = ""
    postalCode: str = ""
    location: Dict[str, Any] = {"type": "Point", "coordinates": [0.0, 0.0]}


class RatingSchema(BaseModel):
    count: int = 0
    starRating: float = 0.0


class VenueSchema(BaseModel):
    id: str = Field(..., description="Unique identifier for the venue")
    name: str = Field(..., description="Name of the restaurant")
    brand: Optional[str] = None
    uniqueName: str = ""
    address: AddressSchema = Field(default_factory=AddressSchema)
    rating: RatingSchema = Field(default_factory=RatingSchema)
    logoUrl: Optional[str] = None
    isTestRestaurant: bool = False
    cuisines: List[str] = []
    telephone: Optional[str] = None
    ghostStore: Optional[Any] = None
    url: str = Field(..., description="The source URL from which data was scraped")
    menus: Dict[str, MenuSchema] = {}


class JustEatScrapeResult(BaseModel):
    """Wrapper for the final scrape result to match expected JSON output format."""
    venue: VenueSchema
