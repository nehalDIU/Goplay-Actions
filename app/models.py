from dataclasses import dataclass, field
from typing import Dict, Optional, Any

@dataclass
class Category:
    id: str
    name: str
    sort_order: int = 1
    icon: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Category instance to a dictionary for Supabase."""
        return {
            "id": self.id,
            "name": self.name,
            "sort_order": self.sort_order,
            "icon": self.icon
        }

@dataclass
class Channel:
    id: str
    name: str
    stream_url: str
    sort_order: int
    logo: Optional[str] = None
    category: str = "test-category"
    country: str = "Bangladesh"
    language: str = "Bangla"
    is_live: bool = True
    is_trending: bool = False
    quality: str = "HD"
    headers: Dict[str, Any] = field(default_factory=dict)
    proxy: bool = False
    drm: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Channel instance to a dictionary for Supabase."""
        return {
            "id": self.id,
            "name": self.name,
            "logo": self.logo,
            "category": self.category,
            "country": self.country,
            "language": self.language,
            "is_live": self.is_live,
            "is_trending": self.is_trending,
            "quality": self.quality,
            "stream_url": self.stream_url,
            "headers": self.headers,
            "sort_order": self.sort_order,
            "proxy": self.proxy,
            "drm": self.drm
        }
