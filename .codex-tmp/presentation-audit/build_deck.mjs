import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "C:/Users/zdeat/Downloads/practiceflow-phase3-backend-checkpoint_1/PracticeFlow_3rd_defense_audit.pptx";
const TMP = "C:/Users/zdeat/Downloads/practiceflow-phase3-backend-checkpoint_1/.codex-tmp/presentation-audit";

const C = {
  navy: "#10182A",
  navy2: "#17213A",
  blue: "#6D72FF",
  cyan: "#73D5FF",
  mint: "#67D4B0",
  amber: "#FFCC74",
  coral: "#FF8C8C",
  ink: "#18233A",
  muted: "#60708D",
  pale: "#F5F7FC",
  line: "#DCE3F0",
  white: "#FFFFFF",
};

function addText(slide, text, x, y, w, h, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontSize: 20,
    color: C.ink,
    fontFace: "Aptos",
    ...style,
  };
  return shape;
}

function addRect(slide, x, y, w, h, fill, radius = false, line = "none") {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width: line === "none" ? 0 : 1 },
    ...(radius ? { borderRadius: "rounded-xl" } : {}),
  });
}

function addCircle(slide, x, y, d, fill) {
  return slide.shapes.add({
    geometry: "ellipse",
    position: { left: x, top: y, width: d, height: d },
    fill,
    line: { style: "solid", fill: "none", width: 0 },
  });
}

function header(slide, index, title, kicker, dark = false) {
  const main = dark ? C.white : C.ink;
  const sub = dark ? "#BFC8E5" : C.muted;
  addText(slide, kicker.toUpperCase(), 72, 50, 500, 22, { fontSize: 13, bold: true, color: sub, characterSpacing: 2 });
  addText(slide, title, 72, 82, 1020, 60, { fontSize: 42, bold: true, color: main });
  addRect(slide, 72, 151, 76, 4, dark ? C.cyan : C.blue);
  addText(slide, `0${index}`, 1140, 54, 66, 28, { fontSize: 16, bold: true, color: sub, alignment: "right" });
}

function footer(slide, dark = false) {
  addText(slide, "PracticeFlow  •  3-я защита", 72, 680, 360, 22, { fontSize: 13, color: dark ? "#AEB9D6" : C.muted });
}

function addNote(slide, note, source) {
  slide.speakerNotes.textFrame.setText(`${note}\n\n[Sources]\n${source}`);
  slide.speakerNotes.setVisible(true);
}

async function writeBlob(path, blob) {
  await fs.writeFile(path, new Uint8Array(await blob.arrayBuffer()));
}

function slide1(deck) {
  const slide = deck.slides.add();
  slide.background.fill = C.navy;
  // Decorative layers: a simple visual motif, not a UI screenshot.
  addRect(slide, 806, 126, 326, 326, C.navy2, true);
  addRect(slide, 836, 156, 326, 326, "#232F50", true);
  addRect(slide, 866, 186, 326, 326, C.blue, true);
  addText(slide, "PF", 930, 272, 150, 84, { fontSize: 64, bold: true, color: C.white, alignment: "center" });
  addText(slide, "PRACTICEFLOW", 72, 94, 380, 24, { fontSize: 14, bold: true, color: C.cyan, characterSpacing: 2 });
  addText(slide, "Цифровая платформа\nдля управления\nстуденческой практикой", 72, 164, 675, 220, { fontSize: 54, bold: true, color: C.white });
  addText(slide, "3-я защита • честный статус MVP на основе аудита репозитория", 74, 424, 590, 40, { fontSize: 22, color: "#C6D0E9" });
  addRect(slide, 72, 522, 246, 4, C.cyan);
  addText(slide, "август 2026", 72, 546, 250, 26, { fontSize: 17, color: "#AEB9D6" });
  footer(slide, true);
  addNote(slide, "Здравствуйте. PracticeFlow — это платформа, которая переводит работу с отчётами по практике из разрозненных файлов в единый процесс. Сегодня покажу проблему, целевой поток и честный статус MVP по фактическому коду.", "Аудит локального репозитория PracticeFlow, 20.08.2026.");
}

function slide2(deck) {
  const slide = deck.slides.add();
  slide.background.fill = C.pale;
  header(slide, 2, "Проверка отчётов всё ещё живёт в файлах и пересылках", "Проблема");
  // Flow line behind the entity nodes.
  addRect(slide, 144, 369, 796, 4, C.line);
  const nodes = [
    ["Word\nфайлы", 126, C.coral],
    ["Письма и\nверсии", 364, C.amber],
    ["Ручная\nпроверка", 602, C.blue],
    ["Оформление\nвручную", 840, C.mint],
  ];
  for (const [label, x, color] of nodes) {
    addCircle(slide, x, 327, 86, color);
    addText(slide, label, x - 34, 433, 156, 56, { fontSize: 19, bold: true, color: C.ink, alignment: "center" });
  }
  addText(slide, "Много версий отчёта • сложно увидеть, что именно исправить • итоговый документ приходится собирать вручную", 126, 538, 942, 62, { fontSize: 26, color: C.ink, alignment: "center" });
  footer(slide);
  addNote(slide, "Сейчас процесс обычно строится вокруг Word-файлов и почты. Отчёт пересылается несколько раз, преподаватель вручную ищет изменения, а студенту не всегда ясно, к какому месту относится замечание. Отдельная работа — финальное оформление документа.", "Логически обоснованная проблематика из постановки задачи; статистика не заявляется.");
}

function slide3(deck) {
  const slide = deck.slides.add();
  slide.background.fill = C.white;
  header(slide, 3, "Данные преподавателей добавим после Google Forms", "Исследование");
  addText(slide, "В репозитории нет результатов опроса — статистика намеренно не показана.", 72, 184, 910, 32, { fontSize: 23, color: C.muted });
  const items = [
    ["Участников", "[будет заполнено]"],
    ["Основная проблема", "[будет заполнено]"],
    ["Интерес к онлайн-проверке", "[будет заполнено]"],
    ["Востребованная функция", "[будет заполнено]"],
  ];
  let y = 272;
  for (let i = 0; i < items.length; i += 1) {
    const x = i % 2 === 0 ? 72 : 650;
    if (i === 2) y = 458;
    addRect(slide, x, y, 530, 128, i === 1 ? "#F8F9FF" : C.pale, true, C.line);
    addText(slide, items[i][0], x + 28, y + 24, 420, 28, { fontSize: 18, bold: true, color: C.muted });
    addText(slide, items[i][1], x + 28, y + 63, 450, 30, { fontSize: 24, bold: true, color: i === 3 ? C.blue : C.ink });
  }
  footer(slide);
  addNote(slide, "Опрос преподавателей запланирован, но его результатов в проекте нет. Поэтому мы не подменяем исследование предположениями. После Google Forms сюда добавим размер выборки, главную проблему, интерес к онлайн-проверке и приоритетную функцию.", "Поиск по репозиторию: отсутствуют Google Forms, survey/опрос и результаты исследования.");
}

function slide4(deck) {
  const slide = deck.slides.add();
  slide.background.fill = C.navy;
  header(slide, 4, "Один маршрут вместо цепочки файлов", "Решение", true);
  addText(slide, "Целевой процесс PracticeFlow", 72, 188, 380, 30, { fontSize: 23, color: "#C7D0EA" });
  // Route first, then nodes on top.
  addRect(slide, 126, 369, 1028, 4, "#51607F");
  const stages = ["Шаблон", "Группа", "Студент", "Заполнение", "Проверка", "Правки", "Утверждение", "Word / PDF"];
  const colors = [C.cyan, C.cyan, C.mint, C.mint, C.amber, C.coral, C.blue, C.blue];
  stages.forEach((label, i) => {
    const x = 92 + i * 143;
    addCircle(slide, x, 335, 68, colors[i]);
    addText(slide, String(i + 1), x, 352, 68, 26, { fontSize: 18, bold: true, color: C.navy, alignment: "center" });
    addText(slide, label, x - 34, 426, 136, 44, { fontSize: 17, bold: true, color: C.white, alignment: "center" });
  });
  addText(slide, "Роли разделены: преподаватель задаёт структуру и проверяет; студент работает только со своим черновиком.", 128, 551, 1000, 36, { fontSize: 23, color: "#C7D0EA", alignment: "center" });
  footer(slide, true);
  addNote(slide, "Решение строится как единый маршрут: преподаватель создаёт шаблон и назначает практику группе, студент заполняет свой экземпляр, затем начинается проверка, правки и финальное утверждение с экспортом. Этот поток — целевая модель; ниже я отделяю уже реализованные участки от недостающих экранов.", "Постановка задачи пользователя; реализация сверена с API и фронтендом.");
}

function slide5(deck) {
  const slide = deck.slides.add();
  slide.background.fill = C.white;
  header(slide, 5, "MVP: сильный API-фундамент, но пользовательский поток ещё не замкнут", "Фактический статус");
  addRect(slide, 72, 192, 4, 416, C.blue);
  addText(slide, "Реализовано в коде и API", 98, 192, 470, 34, { fontSize: 26, bold: true, color: C.ink });
  const ready = [
    "JWT, refresh/logout, 4 роли и tenant isolation",
    "Группы, шаблоны, версии и назначение практики",
    "Структурированный редактор: разделы, таблицы, изображения, стили, нумерация",
    "Черновики, отправка, повторная отправка и история версий",
    "API проверки: статусы, inline/general comments, ответы и resolve",
    "API-экспорт DOCX/PDF с полями, отступами и форматированием",
  ];
  ready.forEach((text, i) => {
    addCircle(slide, 100, 250 + i * 54, 12, C.blue);
    addText(slide, text, 126, 238 + i * 54, 460, 42, { fontSize: 18, color: C.ink });
  });
  addRect(slide, 650, 192, 4, 416, C.amber);
  addText(slide, "Нужно завершить перед пилотом", 676, 192, 510, 34, { fontSize: 26, bold: true, color: C.ink });
  const gaps = [
    "UI публикации практики — API есть, кнопки нет",
    "UI review/comments/history и скачивание экспортов",
    "Рабочие панели Director и Super Admin",
    "Управление организациями, профилями, группами — пока seed/API foundation",
    "End-to-end проверка Docker и PDF-зависимостей",
  ];
  gaps.forEach((text, i) => {
    addCircle(slide, 678, 250 + i * 61, 12, C.amber);
    addText(slide, text, 704, 238 + i * 61, 450, 48, { fontSize: 18, color: C.ink });
  });
  footer(slide);
  addNote(slide, "По коду реализованы авторизация, роли и tenant isolation, группы и версии шаблонов, документный редактор, отправка и повторная отправка. На backend есть review, комментарии и DOCX/PDF export. Но фронтенд пока не выводит публикацию, проверку, историю и скачивание; Director и Super Admin — заглушки. Поэтому MVP нельзя объявлять готовым end-to-end.", "backend/app/api/v1, backend/app/services, frontend/src/App.tsx и frontend/src/features; практический запуск не подтверждён из-за окружения.");
}

function slide6(deck) {
  const slide = deck.slides.add();
  slide.background.fill = C.pale;
  header(slide, 6, "На защите показываем только реальные экраны после запуска", "Демонстрация");
  addText(slide, "Скриншотов интерфейса в репозитории нет. Ниже — честный список кадров для захвата после исправления окружения.", 72, 184, 1050, 36, { fontSize: 22, color: C.muted });
  const shots = [
    ["01", "Teacher • Мои группы", "/groups", "Список закреплённых групп"],
    ["02", "Template editor", "/templates/:id/versions/:id", "Структура, стили и A4 preview"],
    ["03", "Student • Мои отчёты", "/reports", "Назначенный отчёт и статус"],
    ["04", "Student report editor", "/reports/:id/edit", "Редактирование только разрешённых разделов"],
  ];
  shots.forEach((shot, i) => {
    const x = 72 + (i % 2) * 566;
    const y = 268 + Math.floor(i / 2) * 184;
    addRect(slide, x, y, 530, 146, C.white, true, C.line);
    addText(slide, shot[0], x + 26, y + 25, 54, 36, { fontSize: 25, bold: true, color: C.blue });
    addText(slide, shot[1], x + 96, y + 22, 376, 28, { fontSize: 22, bold: true, color: C.ink });
    addText(slide, shot[2], x + 96, y + 59, 380, 24, { fontSize: 16, color: C.muted });
    addText(slide, shot[3], x + 96, y + 92, 400, 27, { fontSize: 17, color: C.ink });
  });
  addText(slide, "Не добавлять фейковые кадры review/export: этих экранов во frontend пока нет.", 72, 625, 1060, 30, { fontSize: 20, bold: true, color: "#B05050" });
  footer(slide);
  addNote(slide, "Для демонстрации нужны только реальные экраны из запущенного проекта: группы преподавателя, редактор шаблона, список отчётов студента и редактор отчёта. В репозитории нет готовых UI-скриншотов. Не стоит показывать review или export как существующие экраны: на backend API они есть, но frontend-интерфейс отсутствует.", "frontend/src/App.tsx и frontend/src/features; в репозитории нет screenshot-файлов UI.");
}

function slide7(deck) {
  const slide = deck.slides.add();
  slide.background.fill = C.white;
  header(slide, 7, "Следующий этап — замкнуть путь пользователя и подтвердить его на практике", "Итог и план");
  const steps = [
    ["Сейчас", "MVP-фундамент", C.blue],
    ["Дальше", "Публикация + review UI", C.amber],
    ["Затем", "Export UI + стабильный Docker", C.cyan],
    ["Финал", "Пилот с преподавателями", C.mint],
  ];
  addRect(slide, 144, 378, 902, 4, C.line);
  steps.forEach((step, i) => {
    const x = 114 + i * 254;
    addCircle(slide, x, 344, 72, step[2]);
    addText(slide, String(i + 1), x, 364, 72, 22, { fontSize: 18, bold: true, color: C.navy, alignment: "center" });
    addText(slide, step[0], x - 20, 450, 112, 26, { fontSize: 17, bold: true, color: C.muted, alignment: "center" });
    addText(slide, step[1], x - 62, 486, 196, 56, { fontSize: 21, bold: true, color: C.ink, alignment: "center" });
  });
  addText(slide, "PracticeFlow создаёт прозрачный маршрут практики — от структуры отчёта до проверяемого результата.", 160, 604, 960, 38, { fontSize: 25, bold: true, color: C.ink, alignment: "center" });
  footer(slide);
  addNote(slide, "Итог такой: у проекта уже есть серьёзный фундамент, но следующий приоритет — соединить реализованный backend с полноценным пользовательским опытом и проверить весь маршрут в нормальном развёртывании. Ценность PracticeFlow — сделать путь от шаблона до результата прозрачным и управляемым для преподавателя и студента.", "Вывод основан на аудите реализации и практических проверках окружения, 20.08.2026.");
}

async function main() {
  await fs.mkdir(TMP, { recursive: true });
  const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  slide1(deck);
  slide2(deck);
  slide3(deck);
  slide4(deck);
  slide5(deck);
  slide6(deck);
  slide7(deck);

  for (const [index, slide] of deck.slides.items.entries()) {
    await writeBlob(`${TMP}/slide-${String(index + 1).padStart(2, "0")}.png`, await deck.export({ slide, format: "png", scale: 1 }));
    await fs.writeFile(`${TMP}/slide-${String(index + 1).padStart(2, "0")}.layout.json`, await (await slide.export({ format: "layout" })).text());
  }
  await writeBlob(`${TMP}/montage.webp`, await deck.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(OUT);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
