"""
Integrations Module

External system integrations for Cthulu trading system.
Includes:
- Vector Studio (Hecktor) for semantic trade memory
- Discord notifications for trade alerts
"""

from .vector_studio import VectorStudioAdapter, VectorStudioConfig
from .embedder import TradeEmbedder
from .retriever import ContextRetriever, SimilarContext
from .data_layer import UnifiedDataLayer
from .discord_notifier import (
    DiscordNotifier,
    DiscordNotification,
    NotificationChannel,
    NotificationPriority,
    get_discord_notifier,
    initialize_discord_notifier,
    stop_discord_notifier,
)

__all__ = [
    "VectorStudioAdapter",
    "VectorStudioConfig",
    "TradeEmbedder",
    "ContextRetriever",
    "SimilarContext",
    "UnifiedDataLayer",
    "DiscordNotifier",
    "DiscordNotification",
    "NotificationChannel",
    "NotificationPriority",
    "get_discord_notifier",
    "initialize_discord_notifier",
    "stop_discord_notifier",
]
