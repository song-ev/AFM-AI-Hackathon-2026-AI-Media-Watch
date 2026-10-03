"""Shared DRF renderers."""
from rest_framework.renderers import BaseRenderer


class PlainTextRenderer(BaseRenderer):
    """Render `?format=text` responses as text/plain.

    Registering this renderer also makes DRF accept `format=text` during
    content negotiation (otherwise it 404s on an unknown format).
    """

    media_type = "text/plain"
    format = "text"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, bytes):
            return data
        return str(data).encode(self.charset)
