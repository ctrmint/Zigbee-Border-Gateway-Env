"""Per-profile All overview layout; default projection needs no database rewrite."""
import re


def default_all_layout():
    return {'columns': 0, 'min_tile_width': 240, 'order': []}


def validate_all_layout(value):
    from .dashboard import DashboardError
    path = 'dashboard.all_layout'
    if not isinstance(value, dict) or set(value) != {'columns', 'min_tile_width', 'order'}:
        raise DashboardError('Provide columns, min_tile_width and order.', path=path)
    if type(value['columns']) is not int or not 0 <= value['columns'] <= 6:
        raise DashboardError('Choose Auto (0) or 1–6 columns.', path=path+'.columns')
    width = value['min_tile_width']
    if type(width) is not int or not 200 <= width <= 640 or width % 20:
        raise DashboardError('Minimum tile width must be 200–640 pixels in steps of 20.', path=path+'.min_tile_width')
    order = value['order']
    if not isinstance(order, list) or len(order) > 50 or any(
            not isinstance(ieee, str) or not re.fullmatch('[0-9a-f]{16}', ieee) for ieee in order):
        raise DashboardError('Tile order must contain at most 50 sensor addresses.', path=path+'.order')
    if len(set(order)) != len(order):
        raise DashboardError('Each sensor may appear in the tile order once.', path=path+'.order')
    # Retain absent addresses: a device returning later recovers its saved position.
    return dict(columns=value['columns'], min_tile_width=width, order=list(order))
