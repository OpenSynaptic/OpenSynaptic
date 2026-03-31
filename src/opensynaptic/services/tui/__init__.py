from .main import TUIService

try:
    from .textual_app import TextualTUIApp
    __all__ = ['TUIService', 'TextualTUIApp']
except ImportError:
    # Textual not installed, export only TUIService
    __all__ = ['TUIService']


