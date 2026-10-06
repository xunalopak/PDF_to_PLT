#!/usr/bin/env python3
"""Convert the supplied vector logo PDF to explicit Lasertrace geometry.

Scoped PDF reader: one unencrypted page/content stream, opaque RGB paths,
translation matrices, cubic curves, round caps and smooth stroke joins.
Other PDF constructs fail explicitly. Python standard library only.
"""
import argparse
import copy
import math
import re
import zlib
from pathlib import Path

MM = 25.4 / 72


def cubic(points, tolerance):
    """De Casteljau subdivision with a control-polygon distance bound."""
    a, b, c, d = points
    dx, dy = d[0] - a[0], d[1] - a[1]
    length = math.hypot(dx, dy)
    error = (max(abs(dx * (p[1] - a[1]) - dy * (p[0] - a[0])) / length
                 for p in (b, c)) if length else max(math.dist(a, p) for p in (b, c)))
    # Projection test also catches collinear curves that reverse direction.
    ordered = all(0 <= (p[0] - a[0]) * dx + (p[1] - a[1]) * dy <= length ** 2
                  for p in (b, c))
    if error <= tolerance and ordered:
        return [d]
    midpoint = lambda p, q: ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    ab, bc, cd = midpoint(a, b), midpoint(b, c), midpoint(c, d)
    abc, bcd = midpoint(ab, bc), midpoint(bc, cd)
    mid = midpoint(abc, bcd)
    return cubic([a, ab, abc, mid], tolerance) + cubic([mid, bcd, cd, d], tolerance)


def closed(path):
    return path if path[0] == path[-1] else path + [path[0]]


def stroke_outline(path, width, round_caps, tolerance):
    """Expand smooth centerlines into actual closed boundaries, in mm."""
    clean = [path[0]]
    for p in path[1:]:
        if math.dist(p, clean[-1]) > 1e-10:
            clean.append(p)
    is_closed = math.dist(clean[0], clean[-1]) < 1e-9
    if is_closed:
        clean.pop()
    radius = width / 2
    segments = list(zip(clean, clean[1:] + ([clean[0]] if is_closed else [])))
    normals = []
    for a, b in segments:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        normals.append((-dy / length, dx / length))
    left, right = [], []
    for i, p in enumerate(clean):
        if not is_closed and i in (0, len(clean) - 1):
            n = normals[0 if i == 0 else -1]
            offset = (radius * n[0], radius * n[1])
        else:
            prev, nxt = normals[i - 1], normals[i % len(normals)]
            divisor = 1 + prev[0] * nxt[0] + prev[1] * nxt[1]
            if divisor < .5:
                raise ValueError('Angle de trait trop aigu pour cet expanseur de courbes lisses')
            offset = (radius * (prev[0] + nxt[0]) / divisor,
                      radius * (prev[1] + nxt[1]) / divisor)
        left.append((p[0] + offset[0], p[1] + offset[1]))
        right.append((p[0] - offset[0], p[1] - offset[1]))
    if is_closed:
        return [closed(left), closed(right)]
    if not round_caps:
        return [closed(left + right[::-1])]
    count = max(8, math.ceil(math.pi / math.acos(1 - min(tolerance / radius, .5))))
    def cap(center, normal):
        angle = math.atan2(normal[1], normal[0])
        return [(center[0] + radius * math.cos(angle - math.pi * i / count),
                 center[1] + radius * math.sin(angle - math.pi * i / count))
                for i in range(1, count)]
    return [closed(left + cap(clean[-1], normals[-1]) + right[::-1]
                   + cap(clean[0], (-normals[0][0], -normals[0][1])))]


def read_logo_pdf(filename, tolerance=.0002):
    data = Path(filename).read_bytes()
    if b'/Encrypt' in data:
        raise ValueError('PDF chiffré non pris en charge')
    objects = {int(m[1]): m[2] for m in re.finditer(
        rb'(\d+)\s+0\s+obj\b(.*?)endobj', data, re.S)}
    pages = [body for body in objects.values() if re.search(rb'/Type\s*/Page\b', body)]
    if len(pages) != 1:
        raise ValueError('Un PDF à une seule page est requis')
    page = pages[0]
    box = re.search(rb'/MediaBox\s*\[([^]]+)\]', page)
    x0, y0, x1, y1 = map(float, box[1].split())
    if x0 or y0 or b'/Rotate' in page:
        raise ValueError('Origine ou rotation de page non prise en charge')
    ref = re.search(rb'/Contents\s+(\d+)\s+0\s+R', page)
    if ref is None:
        raise ValueError('Un seul flux de contenu direct est requis')
    body = objects[int(ref[1])]
    if b'/FlateDecode' not in body:
        raise ValueError('Le flux doit être compressé avec FlateDecode')
    content = zlib.decompress(body.split(b'stream', 1)[1].lstrip(b'\r\n').split(b'endstream')[0])
    gs_refs = re.findall(rb'/(GS\d+)\s+(\d+)\s+0\s+R', page)
    for _, obj in gs_refs:
        state = objects[int(obj)]
        if not re.search(rb'/CA\s+1(?:\.0)?\b', state) or not re.search(rb'/ca\s+1(?:\.0)?\b', state):
            raise ValueError('Transparence PDF non prise en charge')
        if b'/BM/Normal' not in state or b'/SMask/None' not in state:
            raise ValueError('Mode de fusion PDF non pris en charge')
    state = dict(offset=(0., 0.), fill=(0., 0., 0.), stroke=(0., 0., 0.), width=1., cap=0, join=0)
    stack, args, path, regions = [], [], [], []
    clip_pending = False
    for token in content.decode('ascii').split():
        try:
            args.append(float(token))
            continue
        except ValueError:
            pass
        if token.startswith('/'):
            args.append(token)
            continue
        def p(x, y):
            return ((x + state['offset'][0]) * MM, (y + state['offset'][1]) * MM)
        if token == 'q':
            stack.append(copy.deepcopy(state))
        elif token == 'Q':
            state = stack.pop()
        elif token == 'cm':
            a, b, c, d, tx, ty = args
            if (a, b, c, d) != (1, 0, 0, 1):
                raise ValueError('Seules les translations PDF sont prises en charge')
            ox, oy = state['offset']
            state['offset'] = (ox + tx, oy + ty)
        elif token in ('rg', 'RG'):
            state['fill' if token == 'rg' else 'stroke'] = tuple(args)
        elif token in ('w', 'J', 'j'):
            state[{'w': 'width', 'J': 'cap', 'j': 'join'}[token]] = args[0]
        elif token == 'm':
            if path:
                raise ValueError('Sous-chemins multiples non pris en charge')
            path = [p(*args)]
        elif token == 'l':
            path.append(p(*args))
        elif token in ('c', 'y'):
            a = path[-1]
            b = p(*args[:2])
            c = p(*args[2:4]) if token == 'c' else p(*args[2:])
            d = p(*args[4:]) if token == 'c' else c
            path.extend(cubic([a, b, c, d], tolerance))
        elif token == 'h':
            path = closed(path)
        elif token == 're':
            x, y, w, h = args
            path = [p(x, y), p(x + w, y), p(x + w, y + h), p(x, y + h), p(x, y)]
        elif token == 'W':
            clip_pending = True
        elif token == 'n':
            if clip_pending:
                expected = sorted([(0., 0.), (x1 * MM, y1 * MM)])
                bounds = sorted([(min(v[0] for v in path), min(v[1] for v in path)),
                                 (max(v[0] for v in path), max(v[1] for v in path))])
                if any(math.dist(a, b) > .001 for a, b in zip(expected, bounds)):
                    raise ValueError('Découpage PDF autre que la page non pris en charge')
            clip_pending = False
            path = []
        elif token in ('f', 'S', 'B'):
            if token in ('f', 'B'):
                regions.append(([closed(path)], state['fill']))
            if token in ('S', 'B'):
                if state['cap'] not in (0, 1) or state['join'] not in (0, 1):
                    raise ValueError('Style de trait non pris en charge')
                regions.append((stroke_outline(path, state['width'] * MM,
                                               state['cap'] == 1, tolerance), state['stroke']))
            path = []
        elif token == 'gs':
            if args != ['/GS0']:
                raise ValueError('État graphique PDF inconnu')
        elif token not in ('BDC', 'EMC'):
            raise ValueError(f'Opérateur PDF non pris en charge : {token}')
        args = []
    if stack or path or not regions:
        raise ValueError('Flux PDF incomplet')
    return regions, (x1 * MM, y1 * MM)


def intervals(loops, y):
    xs = sorted(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                for polygon in loops for a, b in zip(polygon, polygon[1:])
                if min(a[1], b[1]) <= y < max(a[1], b[1]))
    if len(xs) % 2:
        raise ValueError('Nombre impair de croisements de contour')
    return list(zip(xs[::2], xs[1::2]))


def visible_intervals(regions, y):
    result = []
    for loops, rgb in regions:
        spans = intervals(loops, y)
        if min(rgb) > .99:
            for left, right in spans:
                result = [(a, b) for x, z in result for a, b in
                          [(x, min(z, left)), (max(x, right), z)] if b > a]
        else:
            merged = []
            for left, right in sorted(result + spans):
                if merged and left <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
                else:
                    merged.append((left, right))
            result = merged
    return result


def write_simple_plt(strokes, filename, integer=False):
    commands = ['IN;PA;SP1;']
    for path in strokes:
        coords = []
        for x, y in path:
            p = ((round(x * 40), round(y * 40)) if integer else
                 (round(x * 40, 4), round(y * 40, 4)))
            if not coords or p != coords[-1]:
                coords.append(p)
        if len(coords) < 2:
            continue
        commands.append(f'PU{coords[0][0]:.4f},{coords[0][1]:.4f};' if not integer else
                        f'PU{coords[0][0]},{coords[0][1]};')
        for i in range(1, len(coords), 80):
            commands.append('PD' + ','.join((f'{x},{y}' if integer else f'{x:.4f},{y:.4f}')
                                           for x, y in coords[i:i + 80]) + ';')
    commands.append('PU;SP0;')
    Path(filename).write_text('\n'.join(commands) + '\n', encoding='ascii')


def write_surface_pdf(regions, size, filename):
    """Minimal vector PDF: filled polygons only, no stroked paths or fonts."""
    commands = []
    for loops, rgb in regions:
        commands.append(' '.join(f'{v:.6f}' for v in rgb) + ' rg')
        for path in loops:
            commands.append(f'{path[0][0] / MM:.6f} {path[0][1] / MM:.6f} m')
            commands.extend(f'{x / MM:.6f} {y / MM:.6f} l' for x, y in path[1:])
            commands.append('h')
        commands.append('f*')
    content = ('\n'.join(commands) + '\n').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               (f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {size[0] / MM:.6f} '
                f'{size[1] / MM:.6f}] /Resources << >> /Contents 4 0 R >>').encode('ascii'),
               f'<< /Length {len(content)} >>\nstream\n'.encode('ascii') + content + b'endstream']
    data = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f'{i} 0 obj\n'.encode('ascii') + obj + b'\nendobj\n')
    xref = len(data)
    data.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode('ascii'))
    data.extend(''.join(f'{offset:010d} 00000 n \n' for offset in offsets[1:]).encode('ascii'))
    data.extend((f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n'
                 f'startxref\n{xref}\n%%EOF\n').encode('ascii'))
    Path(filename).write_bytes(data)


def export(regions, size, folder, spacing=.025, prefix='KHEIRON'):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    dark = [(loops, rgb) for loops, rgb in regions if min(rgb) < .99]
    outlines = [path for loops, _ in dark for path in loops]
    # White paint in this PDF does not mask any earlier dark geometry.
    # Refuse overlapping white paint rather than exporting incorrect contours.
    for loops, rgb in regions:
        if min(rgb) > .99:
            earlier = regions[:regions.index((loops, rgb))]
            for i in range(math.ceil(size[1] / .005)):
                y = (i + .5) * .005
                if any(min(b, d) - max(a, c) > 1e-7
                       for a, b in intervals(loops, y)
                       for c, d in visible_intervals(earlier, y)):
                    raise ValueError('Un masque blanc chevauche les contours ; opération booléenne requise')
    write_simple_plt(outlines, folder / f'{prefix}_lasertrace_contours.plt')
    write_simple_plt(outlines, folder / f'{prefix}_lasertrace_contours_entiers.plt', integer=True)
    fill = []
    for i in range(math.ceil(size[1] / spacing)):
        y = (i + .5) * spacing
        for left, right in visible_intervals(regions, y):
            fill.append([(left, y), (right, y)] if i % 2 == 0 else [(right, y), (left, y)])
    write_simple_plt(outlines + fill, folder / f'{prefix}_lasertrace_rempli.plt')
    # R12 closed polylines, with no lineweight or hatch dependency.
    dxf = ['0', 'SECTION', '2', 'HEADER', '9', '$ACADVER', '1', 'AC1009',
           '0', 'ENDSEC', '0', 'SECTION', '2', 'ENTITIES']
    for path in outlines:
        dxf += ['0', 'POLYLINE', '8', 'LOGO', '66', '1', '70', '1', '10', '0', '20', '0', '30', '0']
        for x, y in path[:-1]:
            dxf += ['0', 'VERTEX', '8', 'LOGO', '10', f'{x:.6f}', '20', f'{y:.6f}', '30', '0']
        dxf += ['0', 'SEQEND', '8', 'LOGO']
    dxf += ['0', 'ENDSEC', '0', 'EOF']
    (folder / f'{prefix}_lasertrace_contours.dxf').write_text('\n'.join(dxf) + '\n', encoding='ascii')
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size[0]}mm" height="{size[1]}mm" '
           f'viewBox="0 0 {size[0]} {size[1]}">', f'<g transform="translate(0,{size[1]}) scale(1,-1)">']
    for loops, rgb in regions:
        commands = ' '.join('M ' + ' L '.join(f'{x:.6f},{y:.6f}' for x, y in path[:-1]) + ' Z'
                            for path in loops)
        color = ','.join(str(round(v * 255)) for v in rgb)
        svg.append(f'<path d="{commands}" fill="rgb({color})" fill-rule="evenodd"/>')
    svg.append('</g></svg>')
    (folder / f'{prefix}_surfaces.svg').write_text('\n'.join(svg), encoding='utf-8')
    write_surface_pdf(regions, size, folder / f'{prefix}_surfaces.pdf')
    print(f'PDF {size[0]:.4f} × {size[1]:.4f} mm : {len(outlines)} contours fermés, '
          f'{sum(len(p) for p in outlines)} points, {len(fill)} segments de remplissage.')
    return outlines, fill


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('lasertrace'))
    parser.add_argument('--spacing', type=float, default=.025, help='Pas de balayage en mm')
    args = parser.parse_args()
    if not math.isfinite(args.spacing) or args.spacing < .001:
        parser.error('Le pas doit être fini et au moins égal à 0,001 mm')
    try:
        regions, size = read_logo_pdf(args.pdf)
        export(regions, size, args.output_dir, args.spacing)
    except (ValueError, OSError, KeyError, IndexError, zlib.error) as error:
        parser.exit(1, f'Conversion impossible : {error}\n')


if __name__ == '__main__':
    main()
