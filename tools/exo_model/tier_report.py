"""Build the Russian delivery report from the audits of the reopened scenes."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMITS = {2: (18000, 6500), 3: (22000, 8000)}
POSES = {
    'rest': 'Исходная стойка',
    'crouch': 'Присед, бедро 60°, колено 95°',
    'knee120': 'Колено 120°',
    'elbow110': 'Локоть 110°',
    'down60': 'Руки вниз на 60°',
    'twist30': 'Поворот корпуса на 30°',
}


def count(value):
    return f'{value:,}'.replace(',', ' ')


def mm(value):
    return f'{value:.2f}'.replace('.', ',')


def pose_cell(parts, lod):
    rows = [row for row in parts.values() if row['lod'] == lod]
    gaps = [row['closest_surface_gap_mm'] for row in rows]
    found = [gap for gap in gaps if gap is not None]
    hits = sum(sum(row['surface_intersection_triangle_pairs'].values()) for row in rows)
    outside = sum(gap is None or not 5 <= gap <= 25 for gap in gaps)
    distance = f'{mm(min(found))}–{mm(max(found))}' if found else 'нет пары'
    return hits, distance, outside


def render_report():
    audits = {t: json.loads((ROOT/f'tier_qa_t{t}.json').read_text(encoding='utf8')) for t in LIMITS}
    lines = [
        '# Экзоскелеты T2 и T3',
        '',
        '[Модель T2](exo_t2.blend) · [Модель T3](exo_t3.blend) · [Сравнение T1, T2 и T3](previews_tiers.png)',
        '',
        'T2 получил коробчатые направляющие, открытые цилиндры с полированными штоками, болтовые крышки редукторов и две съёмные батареи. У T3 удлинённые кожухи приводов, плечевые рычаги, центральный силовой блок на продольной опоре и бирюзовая маркировка. Куртка, брюки и ворот остаются открытыми.',
        '',
        'Ножные манжеты образуют жёсткие эллиптические дуги в 200° с параллельными краями и боковым замком. У манжет рук вырез обращён к туловищу, чтобы дать рукам опуститься.',
        '',
        '## Модели и текстуры',
        '',
        '| Модель | LOD0, треугольников / лимит | LOD1, треугольников / лимит | Деталей в каждом LOD |',
        '|---|---:|---:|---:|',
    ]
    for tier, data in audits.items():
        totals = data['triangles']
        parts = sum(name.startswith('EXO_') for name in data['parts'])
        lines.append(f"| T{tier} | {count(totals['LOD0'])} / {count(LIMITS[tier][0])} | {count(totals['LOD1'])} / {count(LIMITS[tier][1])} | {parts} |")
    lines += [
        '',
        'Обе сцены сохранены в REST. Включён LOD0. Коллекции обоих LOD содержат модели с единственным материалом `exo_mat` и модификатором Armature, который указывает на `EFT_Bind`. При повторном открытии проверены матрицы привязки, имена, родители и положения концов костей относительно исходной сцены. На вершину приходится от одного до четырёх нормализованных весов.',
        '',
        'У каждого уровня свой комплект из трёх PNG 2048 × 2048. Альбедо хранится в sRGB с непрозрачной альфой. Нормали заданы в касательном пространстве OpenGL (+Y). Нормали и серый gloss загружаются как Non-Color. Шероховатость материала равна `1 − gloss`. Пути к текстурам относительные. [Текстуры T2](textures_t2/) · [Текстуры T3](textures_t3/)',
        '',
        '| Проверка общего атласа LOD0 и LOD1 | T2 | T3 |', '|---|---:|---:|',
    ]
    for key,label in [('positive_overlap_pairs','Перекрытия UV положительной площади'),('degenerate_uv_triangles','Вырожденные UV-треугольники'),('outside_unit_square','Треугольники за границами атласа')]:
        lines.append(f"| {label} | {audits[2]['uv']['combined'][key]} | {audits[3]['uv']['combined'][key]} |")
    for tier,data in audits.items():
        if data['errors']:
            lines.append(f"Ошибки проверки T{tier} — {', '.join(data['errors'])}.")
    lines += [
        '', '## Посадка в шести позах', '',
        'В каждой позе Blender вычислял поверхности экзоскелета и одежды после скиннинга. Проверены пересечения треугольников с `REF_top` и `REF_pants`. Минимальное расстояние каждой детали до одежды вычислено по парам вершина–грань и ребро–ребро в радиусе 26 мм. Таблица показывает диапазон этих минимумов от ближайшей детали до самой удалённой.',
        '',
        '| Модель и поза | Пересечения LOD0 / LOD1 | Зазоры LOD0, мм | Зазоры LOD1, мм | Деталей вне 5–25 мм, оба LOD |',
        '|---|---:|---:|---:|---:|',
    ]
    for tier,data in audits.items():
        for pose,label in POSES.items():
            parts = data['poses'][pose]['parts']
            ah,ag,ao = pose_cell(parts,'LOD0')
            bh,bg,bo = pose_cell(parts,'LOD1')
            lines.append(f'| T{tier} · {label} | {ah} / {bh} | {ag} | {bg} | {ao+bo} |')
    lines += ['', 'Наружные стенки и крышки выступают дальше монтажных поверхностей. Наибольшие расстояния от проверенных вершин, середин рёбер и центров треугольников до одежды составили ' +
              ' и '.join(f'{mm(max(v["distance_mm"]["max"] for pose in data["poses"].values() for v in pose["parts"].values()))} мм у T{t}' for t,data in audits.items()) +
              '. Значения для каждой детали и позы сохранены отдельно. [Измерения T2](tier_qa_t2.json) · [Измерения T3](tier_qa_t3.json)', '',
              '## Привязка по деталям', '',
              'Имена деталей даны после `EXO_` и `EXO1_`. У каждой указанной кости префикс `Base Human`, например `Base HumanLThigh1`. В таблице перечислены группы с ненулевыми весами.']
    for tier,data in audits.items():
        lines += ['',f'### T{tier}','','| Деталь | Треугольники LOD0 / LOD1 | Кости |','|---|---:|---|']
        stems = sorted(n[4:] for n in data['parts'] if n.startswith('EXO_'))
        for stem in stems:
            a,b = (data['parts'][prefix+stem] for prefix in ('EXO_','EXO1_'))
            groups = [', '.join(f'`{name.removeprefix("Base Human")}`' for name in row['bones']) for row in (a,b)]
            bones = groups[0] if groups[0]==groups[1] else 'LOD0 — '+groups[0]+'<br>LOD1 — '+groups[1]
            lines.append(f"| `{stem}` | {count(a['triangles'])} / {count(b['triangles'])} | {bones} |")
    lines += [
        '', '## Границы проверки', '',
        'Концы штоков привязаны к направляющей цилиндра и к эксцентрику на соседнем звене. Ход воспроизводится скиннингом на штатных костях. В сцене нет отдельного физического решателя или игровой системы IK.',
        '',
        'Проверены шесть поз с предоставленным комплектом одежды в Blender 5.3. Меши одежды имеют открытые края, поэтому пересечения измерены по поверхностям. Проверка других комплектов и переходов между игровыми анимациями остаётся этапом интеграции.',
        '', '## Рендеры и повторная сборка', '',
        'В каждой папке семь изображений, включая глубокий присед, сгибание локтей на 110° и вид рамы без одежды. [Рендеры T2](previews_t2/) · [Рендеры T3](previews_t3/)',
        '', 'Команды выполняются из этой папки в PowerShell.', '', '```powershell',
        r"$blender = 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe'",
        'foreach ($tier in 2, 3) {',
        r'    & $blender --factory-startup -b .\base_scene.blend --python-exit-code 1 --python .\build_tiers.py -- $tier',
        r'    & $blender --factory-startup -b ".\exo_t$tier.blend" --python-exit-code 1 --python .\tier_qa.py -- $tier',
        r'    & $blender --factory-startup -b ".\exo_t$tier.blend" --python-exit-code 1 --python .\tier_previews.py -- "t$tier" all',
        '}', r'& $blender --factory-startup -b --python-exit-code 1 --python .\tier_previews.py -- compare',
        r'& $blender --factory-startup -b --python-exit-code 1 --python .\tier_report.py', '```',
    ]
    (ROOT/'REPORT_T2_T3.md').write_text('\n'.join(lines)+'\n',encoding='utf8')


if __name__ == '__main__':
    render_report()
