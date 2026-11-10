"""Placeholder for channel adapters. WhatsApp arrives as a webhook behind the same normalisation."""

from app.channels.chat import ChatInbound, to_submission

__all__ = ["ChatInbound", "to_submission"]
