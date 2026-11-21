"""Write the Russian handoff from the read-back model and pose measurements."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
validation=json.loads((ROOT/'validation.json').read_text(encoding='utf8'))
poses=json.loads((ROOT/'qa_metrics.json').read_text(encoding='utf8'))['poses']
parts=validation['parts']
assert not validation['errors'],validation['errors']
all_stats=[v for pose in poses.values() for v in pose['parts'].values()]
assert all(not any(v['surface_intersection_triangle_pairs'].values()) for v in all_stats)
assert all(5<=v['closest_surface_gap_mm']<=25 for v in all_stats)
base=[name for name in parts if name.startswith('EXO_')]
total0=sum(parts[n][0] for n in base)
total1=sum(parts['EXO1_'+n[4:]][0] for n in base)
pose_names={'rest':'Исходная стойка','crouch':'Присед, тазобедренные суставы 60°, колени 95°',
            'knee120':'Сгибание коленей 120°','elbow110':'Сгибание локтей 110°',
            'down60':'Опускание рук 60°','twist30':'Поворот корпуса 30°'}

lines=[
'# EXO-3 — передача модели для интеграции',
'',
f'Модель содержит **{format(total0, "_").replace("_", " ")} треугольника в LOD0** и **{format(total1, "_").replace("_", " ")} в LOD1**. В каждом уровне по {len(base)} скинованных объектов. Основная сцена сохранена в REST. Матрицы привязки, иерархия, имена и концы всех 58 костей совпали с исходной сценой при повторном открытии файла.',
'',
'[Модель](exo_model.blend) · [Вид в три четверти](previews/three_quarter.png) · [Рама без одежды](previews/solo.png)',
'',
'## Состав и интеграция',
'',
'Две продольные направляющие несут съёмный блок питания. Плечевые вилки связывают спину с наружными рычагами рук. На ногах открытые направляющие проходят через боковые коленные шарниры и заканчиваются пяточными чашками со стременами под подошвами. Грудь пересекают узкие стропы с пряжкой. Пространство над воротом свободно.',
'',
'Для экспорта одного уровня выберите его коллекцию и арматуру `EFT_Bind`. В сцене включена `EXO_LOD0`. Видимость `EXO_LOD1` переключается на уровне коллекции для окна просмотра и рендера. Студийная камера, свет и пол находятся в `Preview Studio`. Камера настроена на ракурс в три четверти. Сохраните соседнюю папку `textures/` при переносе файла.',
'',
'Один материал `exo_mat` использует единый UV-атлас для обоих уровней. Все три PNG имеют размер 2048 × 2048 и 8 бит на канал. Альфа везде равна 255. Альбедо хранится в sRGB. Для tangent-space normal (+Y, OpenGL) и серой карты gloss используется Non-Color. В материале Blender шероховатость равна `1 − gloss`. Панельные швы, утопленные винты, потёртости и маркировка батареи запечены в карты.',
'',
f"Проверка всех UV-треугольников обоих LOD обнаружила **{validation['uv']['positive_overlap_pairs']} перекрытий положительной площади**, **{validation['uv']['degenerate_uv_triangles']} вырожденных UV-треугольников** и **{validation['uv']['outside_unit_square']} выходов за границы атласа**. Геометрия состоит из треугольников и четырёхугольников. У каждой детали ровно один модификатор Armature с целью `EFT_Bind`.",
'',
'## Детали и привязка',
'',
'В первом столбце приведено имя после `EXO_` или `EXO1_`. К каждому имени кости в последнем столбце добавляется префикс `Base Human` без пробела после `Human`. Например, `LThigh1` означает `Base HumanLThigh1`. Группы перечислены по всему объекту. На отдельную вершину приходится от одного до четырёх влияний, сумма весов проверена. Жёсткие корпуса движутся со своей костью. Текстильные элементы используют веса одежды, поясничные тяги плавно переходят между тазом и спиной.',
'',
'| Деталь | LOD0, трис. | LOD1, трис. | Кости LOD0 и LOD1 |',
'|---|---:|---:|---|']
for n in base:
    small=parts['EXO1_'+n[4:]]
    p0=set(parts[n][1]);p1=set(small[1])
    names=', '.join('`'+v.removeprefix('Base Human')+'`' for v in sorted(p0|p1))
    if p0!=p1:
        names+=' (наборы по LOD см. в validation.json)'
    lines.append(f'| `{n[4:]}` | {parts[n][0]} | {small[0]} | {names} |')
lines += [
'','## Посадка и деформация','',
'Для каждой позы Blender вычислял фактическую геометрию одежды и экзоскелета после скиннинга. Для каждой из 40 деталей проверены пересечения треугольников с `REF_top` и `REF_pants`. Минимальный зазор вычислен по обеим комбинациям вершина–грань и по ближайшим точкам внутренних участков двух рёбер. Пространственный поиск учитывал пары на расстоянии до 26 мм. В каждой проверке найдена ближайшая пара внутри этого радиуса.',
'',
'В таблице указан диапазон минимальных зазоров отдельных деталей. Первое число относится к детали, ближайшей к одежде, второе — к детали с наибольшим минимальным зазором.',
'',
'| Поза | LOD0, мм | LOD1, мм | Пересечения, оба LOD |',
'|---|---:|---:|---:|']
for pose,data in poses.items():
    cells=[]
    for lod in ('LOD0','LOD1'):
        gaps=[v['closest_surface_gap_mm'] for v in data['parts'].values() if v['lod']==lod]
        cells.append(f'{min(gaps):.2f}–{max(gaps):.2f}')
    lines.append(f"| {pose_names[pose]} | {cells[0]} | {cells[1]} | 0 |")
max_outer=max(v['distance_mm']['max'] for v in all_stats)
lines += [
'',
f'Дополнительно измерены расстояния от вершин, середин рёбер и центров треугольников. Наружные поверхности корпусов и рычагов выступают за монтажный зазор 25 мм. Наибольшее выборочное расстояние по всем позам составляет {max_outer:.1f} мм. Покомпонентные минимумы, медианы, процентили и доля точек в диапазоне 5–25 мм сохранены в [qa_metrics.json](qa_metrics.json).',
'',
'## Границы проверки','',
'Проверка выполнена на предоставленной куртке и брюках в шести фиксированных позах Blender. Меши одежды имеют открытые края, поэтому знак ближайшей нормали в JSON служит локальной подсказкой. Проверка пересечений опирается на геометрию треугольников. Другие комплекты одежды и игровые анимации требуют проверки при интеграции. Для рендеров использованы процедурные материалы ткани, перчаток и ботинок. Исходная сцена сохранена отдельно.',
'',
'## Рендеры','',
'[Спереди](previews/front.png) · [Сзади](previews/back.png) · [Слева](previews/left.png) · [Три четверти](previews/three_quarter.png) · [Глубокий присед](previews/crouch.png) · [Локти 110°](previews/elbow110.png) · [Без одежды](previews/solo.png)',
'',
'## Повторная сборка','',
'Команды PowerShell выполняются из этой папки. Blender работает в фоновом режиме. Сборка записывает модель и текстуры, две следующие команды заново измеряют сохранённый файл, последняя создаёт семь изображений Cycles. Финальные скрипты находятся рядом с моделью. В `studies/` собраны исследовательские и промежуточные скрипты, использованные при подгонке прототипов.',
'',
'```powershell',r"$blender = 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe'",
r'& $blender --factory-startup -b .\base_scene.blend --python-exit-code 1 --python .\build.py',
r'& $blender --factory-startup -b .\exo_model.blend --python-exit-code 1 --python .\validate.py',
r'& $blender --factory-startup -b .\exo_model.blend --python-exit-code 1 --python .\review.py',
r'& $blender --factory-startup -b .\exo_model.blend --python-exit-code 1 --python .\previews.py -- all',
'```','',
'[Результаты проверки сцены, костей, весов, LOD и UV](validation.json)']
(ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')

