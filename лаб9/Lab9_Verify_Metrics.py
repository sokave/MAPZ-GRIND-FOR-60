"""Перевірка метрик Лаб. 9. Python 3, лише стандартна бібліотека.

Факти про Лаб. 2, 4, 5 і 6 взято з еталонних описів §3.9–3.10
методичних вказівок. Графи поведінки нижче — явні реконструкції
інвентарю, а не копії не наданих вихідних UML-діаграм.
"""

from collections import Counter, defaultdict, deque
from fractions import Fraction
from pathlib import Path
import argparse
import base64
from html.parser import HTMLParser
import re
from xml.etree import ElementTree as ET


NAMES = {
    "context": "Лаб9_діаграма_контексту",
    "containers": "Лаб9_діаграма_контейнерів",
    "modules": "Лаб9_діаграма_модулів",
}
CLASSES = (
    "Особа", "Клієнт", "Курʼєр", "Оцінюваний", "Заклад", "Страва",
    "Замовлення", "ПозиціяЗамовлення", "Оплата",
)
DECLARED = dict.fromkeys(CLASSES, 2)
PARENTS = {"Клієнт": "Особа", "Курʼєр": "Особа"}
# Еталон дає кількість реалізацій інтерфейсу, без переліку їхніх назв.
IMPLEMENTERS = {"Оцінюваний": 2}
COUPLINGS = {
    ("Клієнт", "Замовлення"), ("Курʼєр", "Замовлення"),
    ("Замовлення", "Оплата"), ("Замовлення", "ПозиціяЗамовлення"),
    ("Заклад", "Страва"), ("Страва", "ПозиціяЗамовлення"),
}
RFC = {
    "Диспетчер": (
        {"призначитиКурʼєра", "відібратиКандидатів", "прийняти", "відхилити"},
        {
            "Пропозиція.«create»", "Курʼєр.надіслатиПропозицію",
            "Курʼєр.прийнятиЗамовлення", "Заклад.повідомитиПроКурʼєра",
            "ДодатокКлієнта.надіслатиДаніКурʼєра",
        },
    ),
    "Курʼєр": (
        {"прийнятиЗамовлення", "підтвердитиДоставку", "надіслатиПропозицію"},
        {"Диспетчер.прийняти", "Диспетчер.відхилити"},
    ),
}
# A1–A15 позначають дії без припущення щодо їхніх оригінальних назв.
ACTIVITY = {
    ("Початок", "A1"), ("A1", "A2"), ("A2", "A3"), ("A3", "A4"),
    ("A4", "A5"), ("A5", "fork"),
    ("fork", "A6"), ("A6", "A7"), ("A7", "A8"), ("A8", "join"),
    ("fork", "A9"), ("A9", "A10"), ("A10", "Курʼєр прийняв?"),
    ("Курʼєр прийняв?", "A9"), ("Курʼєр прийняв?", "A11"),
    ("A11", "join"), ("join", "A12"), ("A12", "A13"),
    ("A13", "Клієнт на місці?"), ("Клієнт на місці?", "A14"),
    ("Клієнт на місці?", "A15"), ("A14", "merge"), ("A15", "merge"),
    ("merge", "Кінець"),
}
STATES = {
    ("Початок", "Офлайн"), ("Офлайн", "Очікує"), ("Офлайн", "Кінець"),
    ("Очікує", "Офлайн"), ("Очікує", "Перерва"), ("Перерва", "Очікує"),
    ("Очікує", "ОтримавПропозицію"), ("ОтримавПропозицію", "Очікує"),
    ("ОтримавПропозицію", "ПрямуєДоЗакладу"),
    ("ПрямуєДоЗакладу", "ЗабравЗамовлення"),
    ("ЗабравЗамовлення", "ПрямуєДоКлієнта"), ("ПрямуєДоКлієнта", "Очікує"),
}


def neighbors(edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    return adj


def inheritance_depth(node):
    depth = 0
    while node in PARENTS:
        node = PARENTS[node]
        depth += 1
    return depth


def ck():
    assoc = neighbors(COUPLINGS)
    kids = Counter(PARENTS.values())
    return {
        c: (DECLARED[c], inheritance_depth(c), IMPLEMENTERS.get(c, kids[c]), len(assoc[c]))
        for c in CLASSES
    }


def complexity(edges, choices):
    adj = neighbors(edges)
    unseen = set(adj)
    components = 0
    while unseen:
        components += 1
        pending = [unseen.pop()]
        while pending:
            node = pending.pop()
            unseen_neighbors = adj[node] & unseen
            pending.extend(unseen_neighbors)
            unseen.difference_update(unseen_neighbors)
    degrees = Counter(a for a, _ in edges)
    d = sum(degrees[node] - 1 for node in choices)
    n, e = len(adj), len(edges)
    return n, e, components, d, e - n + 2 * components, d + 1


def module_metrics(nodes, edges):
    incoming = Counter(b for _, b in edges)
    outgoing = Counter(a for a, _ in edges)
    metrics = {
        n: (incoming[n], outgoing[n], Fraction(outgoing[n], incoming[n] + outgoing[n]))
        for n in nodes
    }
    remaining = {n: incoming[n] for n in nodes}
    queue = deque(n for n in nodes if remaining[n] == 0)
    targets = {n: [b for b in nodes if (n, b) in edges] for n in nodes}
    order = []
    while queue:
        a = queue.popleft()
        order.append(a)
        for b in targets[a]:
            remaining[b] -= 1
            if remaining[b] == 0:
                queue.append(b)
    bad = sorted((a, b) for a, b in edges if metrics[a][2] <= metrics[b][2])
    return metrics, order, len(order) == len(nodes), bad


def svg_data(data):
    root = ET.fromstring(data)
    assert root.tag.endswith("}svg")
    tags = [n.tag.split("}")[-1] for n in root.iter()]
    assert "script" not in tags and "foreignObject" not in tags
    assert not any(
        key.split("}")[-1].lower().startswith("on")
        or (key.split("}")[-1] == "href" and not value.startswith(("#", "data:image/png;base64,")))
        for node in root.iter() for key, value in node.attrib.items()
    )
    counts = Counter(n.get("class") for n in root.iter())
    lines = [" ".join("".join(n.itertext()).split()) for n in root.iter() if n.tag.endswith("}text")]
    return counts, tuple(s for s in lines if s)


class GuideImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        src = dict(attrs).get("src", "")
        if tag == "img" and src.startswith("data:image/svg+xml;base64,"):
            self.images.append(base64.b64decode(src.split(",", 1)[1]))


def verify(source, guide_dir=None):
    source = Path(source)
    codes = {k: (source / (stem + ".puml")).read_text(encoding="utf-8") for k, stem in NAMES.items()}
    expected = {"context": (7, 6), "containers": (11, 10), "modules": (5, 9)}
    print("ЛАБОРАТОРНА РОБОТА №9 — ПЕРЕВІРКА АРТЕФАКТІВ І МЕТРИК")
    embedded = None
    if guide_dir:
        guide_dir = Path(guide_dir)
        guide_md = (guide_dir / "Лабораторна_робота_09.md").read_text(encoding="utf-8")
        md_code = [s.strip() for s in re.findall(r"```plantuml\s*\n([\s\S]*?)```", guide_md)]
        html = GuideImages()
        html.feed((guide_dir / "Лабораторна_робота_09.html").read_text(encoding="utf-8"))
        embedded = [svg_data(b)[1] for b in html.images]
        assert len(md_code) == len(embedded) == 3
        assert all(code.strip() in md_code for code in codes.values())

    for key, code in codes.items():
        entities = re.findall(r"^\s*(?:Person|System(?:_Ext)?|Container(?:Db)?|Component)\(", code, re.M)
        rel = re.findall(r'^Rel\(([^,]+),\s*([^,]+),\s*"([^"]+)"(?:,\s*"([^"]+)")?\)', code, re.M)
        svg_counts, svg_text = svg_data((source / (NAMES[key] + ".svg")).read_bytes())
        assert (len(entities), len(rel)) == expected[key]
        assert (svg_counts["entity"], svg_counts["link"]) == expected[key]
        assert all(rel_text.strip() for _, _, rel_text, _ in rel)
        if key == "containers":
            containers = re.findall(r'^\s*Container(?:Db)?\(([^,]+),\s*"[^"]+",\s*"([^"]+)"', code, re.M)
            assert len(containers) == 5
            aliases = {a for a, _ in containers}
            assert all(protocol for a, b, _, protocol in rel if a in aliases and b in aliases)
        if embedded is not None:
            # SVG в HTML може мати інші атрибути доступності; порівнюємо текст.
            assert svg_text in embedded, (key, "текст HTML/SVG різниться")
        print(f"C4 {key}: {len(entities)} вузлів, {len(rel)} звʼязків у коді та SVG")
    if embedded is not None:
        print("MD: збігаються всі 3 блоки PlantUML. HTML: збігається видимий текст усіх 3 SVG.")

    print("\nCK (Лаб. 2 за еталоном; WMC / DIT / NOC / CBO)")
    for name, vals in ck().items():
        print(name, *vals, sep=" | ")
    assert sum(v[0] for v in ck().values()) == 18
    assert sum(v[3] for v in ck().values()) == 2 * len(COUPLINGS) == 12
    print("RFC (Лаб. 6 за еталоном)")
    for name, (owned, calls) in RFC.items():
        print(f"{name}: {len(owned)} + {len(calls)} = {len(owned) + len(calls)}")

    print("\nV(G), N / E / P / d / за ребрами / за виборами")
    a = complexity(ACTIVITY, ("Курʼєр прийняв?", "Клієнт на місці?"))
    s = complexity(STATES, ("Офлайн", "Очікує", "ОтримавПропозицію"))
    assert a == (22, 24, 1, 2, 4, 3)
    assert s == (9, 12, 1, 4, 5, 5)
    print("Лаб. 4: ", a)
    print("Лаб. 5: ", s)

    print("\nМодулі (Ca / Ce / I)")
    mod = codes["modules"]
    records = re.findall(
        r'^\s*Component\(([^,]+),\s*"Модуль «([^»]+)»"[^\n]*Ca = (\d+), Ce = (\d+), I = ([0-9,]+)',
        mod, re.M,
    )
    aliases = {alias: label for alias, label, *_ in records}
    assert len(aliases) == 5
    deps = {(aliases[a], aliases[b]) for a, b in re.findall(r"^Rel\(([^,]+),\s*([^,]+),", mod, re.M)}
    metrics, order, acyclic, bad = module_metrics(list(aliases.values()), deps)
    assert len(deps) == sum(v[0] for v in metrics.values()) == sum(v[1] for v in metrics.values()) == 9
    for _, n, ca, ce, i in records:
        m = metrics[n]
        assert m[:2] == (int(ca), int(ce)) and f"{float(m[2]):.2f}" == i.replace(",", ".")
        print(f"{n}: {m[0]} / {m[1]} / {float(m[2]):.2f}")
    assert acyclic and not bad
    print("ADP: циклів немає; порядок: " + " → ".join(order))
    print("SDP: усі 9 ребер спрямовані від більшого I до меншого.")

    print("\nЩо змінюється після додавання класу Пропозиція")
    after = neighbors(COUPLINGS | {("Пропозиція", "Курʼєр"), ("Пропозиція", "Замовлення")})
    assert [len(after[n]) for n in ("Замовлення", "Курʼєр", "Пропозиція")] == [5, 2, 2]
    assert sum(map(len, after.values())) == 16
    print("CBO Замовлення: 4 → 5; Курʼєр: 1 → 2; Пропозиція: 2; сума 12 → 16.")
    mutated, _, good, violations = module_metrics(list(aliases.values()), deps | {("Оплата", "Замовлення")})
    assert not good and violations == [("Замовлення", "Оплата")]
    assert mutated["Замовлення"][2] == Fraction(2, 5) and mutated["Оплата"][2] == Fraction(1, 2)
    print("Додаткове ребро Оплата → Замовлення: цикл; SDP: Замовлення (0,40) → Оплата (0,50).")
    print("Підрахунки й перевірки завершено.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--guide-dir", type=Path, help="Додатково звірити матеріали методички MD та HTML")
    args = parser.parse_args()
    verify(args.source_dir, args.guide_dir)
