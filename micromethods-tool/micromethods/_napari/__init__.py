"""napari integration (optional import)."""

__all__ = ["methods_widget"]


def methods_widget(viewer=None):
    from .widget import MethodsWidget
    return MethodsWidget(viewer)
