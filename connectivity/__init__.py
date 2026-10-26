"""
Connectivity Module - External Communication Layer
Provides RPC and Webhook capabilities for external integrations.
"""
from .rpc import RPCServer, RPCClient
from .webhook import WebhookServer, WebhookClient

__all__ = ['RPCServer', 'RPCClient', 'WebhookServer', 'WebhookClient']
