"""Versioned preview layouts, projected without rewriting legacy preferences."""
import re

BREAKPOINTS = {'desktop': 12, 'tablet': 6, 'mobile': 1}


def default_grid_layout():
    return {'version': 1, 'theme': 'light', 'all': {key: [] for key in BREAKPOINTS}, 'locations': {}}


def validate_grid_layout(value, current=None):
    from .dashboard import DashboardError
    path = 'dashboard.grid_layout'
    def fail(message, suffix=''):
        raise DashboardError(message, path=path+suffix)
    if not isinstance(value, dict) or not {'version', 'theme', 'all'} <= set(value) or set(value)-{'version','theme','all','locations'}:
        fail('Provide version, theme and all layouts.')
    if type(value['version']) is not int or value['version'] != 1:
        fail('Unsupported grid layout version.', '.version')
    if value['theme'] not in ('light', 'dark'):
        fail('Choose light or dark.', '.theme')
    if not isinstance(value['all'], dict) or set(value['all']) != set(BREAKPOINTS):
        fail('Provide desktop, tablet and mobile layouts.', '.all')
    result = default_grid_layout(); result['theme'] = value['theme']
    def validate_items(items, columns, id_pattern, maximum, prefix):
        if not isinstance(items, list) or len(items) > maximum:
            fail(f'Use at most {maximum} tiles per layout.', prefix)
        seen, rectangles, normalized = set(), [], []
        for index, item in enumerate(items):
            suffix = f'{prefix}[{index}]'
            if not isinstance(item, dict) or set(item) != {'id', 'x', 'y', 'w', 'h'}:
                fail('Provide id, x, y, w and h.', suffix)
            identity = item['id']
            if not isinstance(identity, str) or not re.fullmatch(id_pattern, identity) or identity in seen:
                fail('Use each tile ID at most once.', suffix+'.id')
            if any(type(item[k]) is not int for k in ('x', 'y', 'w', 'h')):
                fail('Grid coordinates must be integers.', suffix)
            x, y, w, h = (item[k] for k in ('x', 'y', 'w', 'h'))
            if not (0 <= x < columns and 0 <= y <= 1000 and 1 <= w <= columns and x+w <= columns and 3 <= h <= 20):
                fail('Tile dimensions exceed the layout bounds.', suffix)
            if any(x < ax+aw and x+w > ax and y < ay+ah and y+h > ay for ax,ay,aw,ah in rectangles):
                fail('Tiles must not overlap.', suffix)
            seen.add(identity); rectangles.append((x,y,w,h));normalized.append(dict(item))
        return normalized
    for key, columns in BREAKPOINTS.items():
        result['all'][key] = validate_items(value['all'][key],columns,'[0-9a-f]{16}',50,'.all.'+key)
    locations=value.get('locations',(current or {}).get('locations',{}))
    if not isinstance(locations,dict) or len(locations)>50:
        fail('Use at most 50 location layouts.','.locations')
    for identity, layouts in locations.items():
        if not isinstance(identity,str) or not re.fullmatch('[a-zA-Z0-9-]{1,64}',identity) or not isinstance(layouts,dict) or set(layouts)!=set(BREAKPOINTS):
            fail('Provide valid location IDs and all screen layouts.','.locations')
        result['locations'][identity]={key:validate_items(layouts[key],columns,'[a-z][a-z0-9-]{0,63}',100,'.locations.'+identity+'.'+key) for key,columns in BREAKPOINTS.items()}
    return result
