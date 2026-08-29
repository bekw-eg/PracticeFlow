import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = "C:/Users/zdeat/Downloads/practiceflow-phase3-backend-checkpoint_1";
const TMP = `${ROOT}/.codex-tmp/business-model-5m`;
const OUT_DIR = `${ROOT}/outputs/business_model_5m`;
const OUT = `${OUT_DIR}/PracticeFlow_business_model_5m_KZT.xlsx`;

const C = {
  navy: "#10182A",
  blue: "#6D72FF",
  teal: "#117A8B",
  mint: "#DDF5EC",
  pale: "#F5F7FC",
  line: "#DCE3F0",
  ink: "#18233A",
  muted: "#60708D",
  inputFill: "#FFF7CC",
  inputBlue: "#0000FF",
  linkGreen: "#008000",
  red: "#B05050",
  white: "#FFFFFF",
};

const money = '#,##0;[Red](#,##0);-';
const percent = '0.0%;[Red](0.0%);-';
const number = '#,##0;[Red](#,##0);-';

async function saveBlob(path, blob) {
  await fs.writeFile(path, new Uint8Array(await blob.arrayBuffer()));
}

function style(range, config = {}) {
  range.format = config;
}

function title(sheet, text, subtitle, endCol = "H") {
  sheet.mergeCells(`A1:${endCol}1`);
  sheet.getRange("A1").values = [[text]];
  style(sheet.getRange(`A1:${endCol}1`), {
    fill: C.navy,
    font: { bold: true, color: C.white, size: 18 },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  });
  sheet.getRange("A1").format.rowHeight = 30;
  sheet.mergeCells(`A2:${endCol}2`);
  sheet.getRange("A2").values = [[subtitle]];
  style(sheet.getRange(`A2:${endCol}2`), {
    fill: C.pale,
    font: { color: C.muted, italic: true, size: 10 },
    verticalAlignment: "center",
    wrapText: true,
  });
  sheet.getRange("A2").format.rowHeight = 30;
}

function section(sheet, range, label) {
  sheet.mergeCells(range);
  const anchor = range.split(":")[0];
  sheet.getRange(anchor).values = [[label]];
  style(sheet.getRange(range), {
    fill: C.teal,
    font: { bold: true, color: C.white, size: 11 },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  });
}

function headerRow(sheet, range) {
  style(sheet.getRange(range), {
    fill: "#E8ECF8",
    font: { bold: true, color: C.ink, size: 10 },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "bottom", style: "thin", color: C.line },
  });
}

function financeInput(sheet, range, format) {
  style(sheet.getRange(range), {
    fill: C.inputFill,
    font: { color: C.inputBlue },
    horizontalAlignment: "right",
  });
  if (format) sheet.getRange(range).format.numberFormat = format;
}

function formulaLink(sheet, range, format) {
  style(sheet.getRange(range), { font: { color: C.linkGreen }, horizontalAlignment: "right" });
  if (format) sheet.getRange(range).format.numberFormat = format;
}

function calculation(sheet, range, format, bold = false) {
  style(sheet.getRange(range), { font: { color: "#000000", bold }, horizontalAlignment: "right" });
  if (format) sheet.getRange(range).format.numberFormat = format;
}

function setColumnWidths(sheet, widths) {
  Object.entries(widths).forEach(([col, width]) => {
    sheet.getRange(`${col}1:${col}100`).format.columnWidth = width;
  });
}

function addBusinessModelCanvas(sheet) {
  title(sheet, "PracticeFlow — бизнес‑модель (BMC)", "B2B SaaS для управления студенческой практикой. Первичный фокус — платный пилот на уровне кафедры/факультета, затем годовая лицензия для организации.", "I");
  setColumnWidths(sheet, { A: 15, B: 15, C: 15, D: 15, E: 15, F: 15, G: 15, H: 15, I: 15 });
  const blocks = [
    ["A4:C4", "A5:C9", "Сегменты клиентов", "ЛПР: заведующий кафедрой, деканат, отдел практики.\nПользователи: преподаватель, студент, методист/директор."],
    ["D4:F4", "D5:F9", "Ценность", "Единый путь: шаблон → отчёт → проверка → правки → итоговый документ.\nМеньше версий файлов, прозрачные статусы и история."],
    ["G4:I4", "G5:I9", "Каналы", "Прямой пилот с кафедрой.\nДемонстрация на реальных экранах.\nПартнёрство с вузом и рекомендация между подразделениями."],
    ["A11:C11", "A12:C16", "Отношения с клиентом", "Онбординг шаблонов и групп.\nПоддержка в период практики.\nЕжемесячный созвон по обратной связи и метрикам."],
    ["D11:F11", "D12:F16", "Потоки выручки", "Платный пилот: 350 тыс. ₸.\nГодовая лицензия: от 1,2 млн ₸.\nРазовая настройка/онбординг: 250 тыс. ₸."],
    ["G11:I11", "G12:I16", "Ключевые действия", "Закрыть UI review/publish/export.\nСтабилизировать Docker/PDF.\nЗапустить 2–3 пилота и конвертировать их в годовые лицензии."],
    ["A18:C18", "A19:C23", "Ключевые ресурсы", "MVP-код, документный движок, команда продукта, UX-исследование, шаблоны и экспертность преподавателей."],
    ["D18:F18", "D19:F23", "Ключевые партнёры", "Кафедры и отделы практики, пилотные вузы, методисты, облачная инфраструктура, юридическая/закупочная поддержка."],
    ["G18:I18", "G19:I23", "Структура затрат", "Разработка и QA, UX, облако/DevOps, онбординг, продажи и договоры.\nПодробное распределение — на листе 04."],
  ];
  blocks.forEach(([head, body, label, text]) => {
    sheet.mergeCells(head);
    sheet.getRange(head.split(":")[0]).values = [[label]];
    style(sheet.getRange(head), {
      fill: C.teal,
      font: { bold: true, color: C.white, size: 11 },
      horizontalAlignment: "left",
      verticalAlignment: "center",
    });
    sheet.mergeCells(body);
    sheet.getRange(body.split(":")[0]).values = [[text]];
    style(sheet.getRange(body), {
      fill: C.pale,
      font: { color: C.ink, size: 10 },
      verticalAlignment: "top",
      wrapText: true,
      borders: { preset: "outside", style: "thin", color: C.line },
    });
  });
  for (const row of [4, 11, 18]) sheet.getRange(`A${row}:I${row}`).format.rowHeight = 22;
  for (const row of [5, 12, 19]) sheet.getRange(`A${row}:I${row}`).format.rowHeight = 82;
  sheet.showGridLines = false;
}

function addAssumptions(sheet, workbook) {
  title(sheet, "Допущения и драйверы", "Жёлтые/синие ячейки — редактируемые допущения. Все расчёты в остальных листах ссылаются на этот лист.", "H");
  setColumnWidths(sheet, { A: 36, B: 16, C: 14, D: 55, E: 3, F: 21, G: 17, H: 28 });
  section(sheet, "A4:D4", "Коммерческие и финансовые драйверы");
  sheet.getRange("A5:D5").values = [["Показатель", "Значение", "Ед.", "Комментарий"]];
  headerRow(sheet, "A5:D5");
  const rows = [
    ["Инвестиции", 5000000, "₸", "Рабочее допущение пользователя: 5 млн ₸."],
    ["Срок MVP‑программы", 10, "мес.", "Период для закрытия критичных UI-гепов и запуска первых пилотов."],
    ["Резерв", 800000, "₸", "Резерв на сдвиг сроков, интеграции и непредвиденные расходы."],
    ["Цена платного пилота", 350000, "₸", "Один факультет/кафедра, один цикл практики."],
    ["Годовая лицензия", 1200000, "₸/год", "Стартовый тариф для организации до 500 активных участников."],
    ["Онбординг и настройка", 250000, "₸", "Разовый платёж: шаблоны, группы, обучение координатора."],
    ["COGS", 0.15, "% выручки", "Облако, поддержка и сопровождение клиента; предположение."],
    ["Активные лицензии — Год 1", 2, "шт.", "Две первые организации после пилота."],
    ["Активные лицензии — Год 2", 7, "шт.", "Пять новых + удержание первых двух."],
    ["Активные лицензии — Год 3", 15, "шт.", "Восемь новых + удержание действующих клиентов."],
    ["Новые лицензии — Год 1", 2, "шт.", "Конверсия первых пилотов в договор на год."],
    ["Платные пилоты — Год 1", 2, "шт.", "Пилоты должны проходить в реальном учебном цикле."],
    ["Новые лицензии — Год 2", 5, "шт.", "План продаж при наличии первых кейсов."],
    ["Платные пилоты — Год 2", 3, "шт.", "Верх воронки на следующий год."],
    ["Новые лицензии — Год 3", 8, "шт.", "Рост через рекомендации и прямые продажи."],
    ["Платные пилоты — Год 3", 5, "шт.", "Воронка для последующих контрактов."],
    ["Операционные расходы — Год 1", 4200000, "₸", "Расходование основной части 5 млн ₸; резерв не включён."],
    ["Операционные расходы — Год 2", 6600000, "₸", "Расширение команды и клиентской поддержки."],
    ["Операционные расходы — Год 3", 9600000, "₸", "Масштабирование продаж, поддержки и инфраструктуры."],
    ["НДС/налог на прибыль", 0, "%", "Не моделируется: зависит от юридической формы и режима налогообложения."],
  ];
  sheet.getRange("A6:D25").values = rows;
  financeInput(sheet, "B6:B25");
  sheet.getRange("B6").format.numberFormat = money;
  sheet.getRange("B7").format.numberFormat = number;
  sheet.getRange("B8").format.numberFormat = money;
  sheet.getRange("B9:B11").format.numberFormat = money;
  sheet.getRange("B12").format.numberFormat = percent;
  sheet.getRange("B13:B20").format.numberFormat = number;
  sheet.getRange("B21:B24").format.numberFormat = money;
  sheet.getRange("B25").format.numberFormat = percent;
  style(sheet.getRange("A6:D25"), { borders: { preset: "insideHorizontal", style: "thin", color: C.line }, verticalAlignment: "center", wrapText: true });
  sheet.getRange("A6:A25").format.font = { color: C.ink };
  sheet.getRange("C6:D25").format.font = { color: C.muted };
  sheet.getRange("A6:D25").format.rowHeight = 23;

  section(sheet, "A27:D27", "Распределение инвестиций — вводимые статьи");
  sheet.getRange("A28:D28").values = [["Статья", "Бюджет, ₸", "Доля", "Привязка к MVP"]];
  headerRow(sheet, "A28:D28");
  const budget = [
    ["Продукт и frontend", 1800000, null, "Publish/review/export UI и роли Director/Admin"],
    ["Backend, QA и качество документов", 700000, null, "E2E-тесты, workflow, DOCX/PDF"],
    ["UX, дизайн и тестирование", 350000, null, "Путь преподавателя и студента; usability"],
    ["DevOps, облако и безопасность", 300000, null, "Docker, PDF-зависимости, логи, бэкапы"],
    ["Пилот и customer success", 650000, null, "Онбординг кафедр, поддержка, обучение"],
    ["Продажи, договоры и юридическое", 400000, null, "Коммерческое предложение, договоры, закупка"],
    ["Резерв", 800000, null, "Непредвиденные работы и задержки"],
  ];
  sheet.getRange("A29:D35").values = budget;
  financeInput(sheet, "B29:B35", money);
  sheet.getRange("C29").formulas = [["=B29/$B$36"]];
  sheet.getRange("C29:C35").fillDown();
  calculation(sheet, "C29:C35", percent);
  sheet.getRange("A36:D36").values = [["Итого", null, null, "Должно совпадать с суммой инвестиций"]];
  sheet.getRange("B36").formulas = [["=SUM(B29:B35)"]];
  sheet.getRange("C36").formulas = [["=SUM(C29:C35)"]];
  calculation(sheet, "B36", money, true);
  calculation(sheet, "C36", percent, true);
  style(sheet.getRange("A36:D36"), { fill: "#E8ECF8", font: { bold: true, color: C.ink }, borders: { preset: "doubleBottom", style: "medium", color: C.teal } });

  section(sheet, "F4:H4", "Легенда модели");
  sheet.getRange("F5:H8").values = [
    ["Синий текст", "Редактируемый ввод", "Поменяйте после интервью и котировок."],
    ["Зелёный текст", "Ссылка на другой лист", "Формула‑связь между блоками."],
    ["Чёрный текст", "Расчёт", "Формула внутри листа."],
    ["Сценарий", "Базовый", "Все суммы без налогов и без оценки доли инвестора."],
  ];
  style(sheet.getRange("F5:H8"), { fill: C.pale, verticalAlignment: "center", wrapText: true, borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("F5").format.font = { color: C.inputBlue, bold: true };
  sheet.getRange("F6").format.font = { color: C.linkGreen, bold: true };
  sheet.getRange("F7").format.font = { color: "#000000", bold: true };
  sheet.getRange("F5:H8").format.rowHeight = 30;
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(5);

  workbook.comments.setSelf({ displayName: "User" });
  workbook.comments.addThread({ cell: sheet.getRange("B6") }, "Assumption: 5 000 000 KZT was requested by the user; currency is assumed to be KZT.");
  workbook.comments.addThread({ cell: sheet.getRange("B10") }, "Assumption: preliminary annual institution price. Validate with pilots and procurement interviews.");
  workbook.comments.addThread({ cell: sheet.getRange("B12") }, "Assumption: COGS covers infrastructure and customer support; validate after the first pilots.");
}

function addInvestment(sheet) {
  title(sheet, "Распределение инвестиций — 5 млн ₸", "Бюджет закрывает критичные продуктовые гепы, запускает пилот и оставляет резерв. Это плановый бюджет, а не подтверждённая смета подрядчиков.", "H");
  setColumnWidths(sheet, { A: 31, B: 54, C: 17, D: 14, E: 4, F: 29, G: 18, H: 20 });
  section(sheet, "A4:D4", "Use of funds");
  sheet.getRange("A5:D5").values = [["Направление", "Что будет профинансировано", "Бюджет, ₸", "Доля"]];
  headerRow(sheet, "A5:D5");
  const labels = [
    ["Продукт и frontend", "UI публикации практики, review/comments/history, export/download, незакрытые роли", "='03_Допущения'!$B$29"],
    ["Backend, QA и документы", "E2E‑проверки, стабилизация workflow и качество DOCX/PDF", "='03_Допущения'!$B$30"],
    ["UX и тестирование", "Сценарии преподавателя/студента, прототипирование, usability‑сессии", "='03_Допущения'!$B$31"],
    ["DevOps и облако", "Docker, PDF‑зависимости, мониторинг, бэкапы и безопасность", "='03_Допущения'!$B$32"],
    ["Пилот и сопровождение", "Онбординг кафедр, миграция шаблонов, обучение и первая линия поддержки", "='03_Допущения'!$B$33"],
    ["Продажи и договоры", "Пилотное коммерческое предложение, договоры, юр. и закупочная подготовка", "='03_Допущения'!$B$34"],
    ["Резерв", "Изменение требований, интеграции, сдвиг сроков или дополнительный пилот", "='03_Допущения'!$B$35"],
  ];
  labels.forEach((row, index) => {
    const excelRow = 6 + index;
    sheet.getRange(`A${excelRow}:B${excelRow}`).values = [[row[0], row[1]]];
    sheet.getRange(`C${excelRow}`).formulas = [[row[2]]];
    sheet.getRange(`D${excelRow}`).formulas = [[`=C${excelRow}/$C$13`]];
  });
  formulaLink(sheet, "C6:C12", money);
  calculation(sheet, "D6:D12", percent);
  style(sheet.getRange("A6:D12"), { verticalAlignment: "center", wrapText: true, borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("A6:D12").format.rowHeight = 34;
  sheet.getRange("A13:D13").values = [["Итого", "", null, null]];
  sheet.getRange("C13").formulas = [["=SUM(C6:C12)"]];
  sheet.getRange("D13").formulas = [["=SUM(D6:D12)"]];
  calculation(sheet, "C13", money, true);
  calculation(sheet, "D13", percent, true);
  style(sheet.getRange("A13:D13"), { fill: "#E8ECF8", font: { bold: true }, borders: { preset: "doubleBottom", style: "medium", color: C.teal } });

  section(sheet, "F4:H4", "Runway и контроль исполнения");
  sheet.getRange("F5:H5").values = [["Метрика", "Значение", "Смысл"]];
  headerRow(sheet, "F5:H5");
  sheet.getRange("F6:F10").values = [["Срок MVP‑программы"], ["Основной бюджет без резерва"], ["Средний core burn / мес."], ["Резерв в месяцах core burn"], ["Плановый cash runway"]];
  sheet.getRange("G6").formulas = [["='03_Допущения'!$B$7"]];
  sheet.getRange("G7").formulas = [["=SUM(C6:C11)"]];
  sheet.getRange("G8").formulas = [["=G7/G6"]];
  sheet.getRange("G9").formulas = [["=C12/G8"]];
  sheet.getRange("G10").formulas = [["=C13/G8"]];
  sheet.getRange("H6:H10").values = [["Время на закрытие MVP и первый пилот"], ["Не включает резерв"], ["Ориентир для контроля затрат"], ["Дополнительный запас при том же burn"], ["Если резерв используется только при необходимости"]];
  formulaLink(sheet, "G6", number);
  calculation(sheet, "G7:G8", money);
  calculation(sheet, "G9:G10", '0.0');
  style(sheet.getRange("F6:H10"), { fill: C.pale, verticalAlignment: "center", wrapText: true, borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("F6:H10").format.rowHeight = 34;

  section(sheet, "A16:H16", "Результат, который должен быть получен за инвестиции");
  sheet.mergeCells("A17:H19");
  sheet.getRange("A17").values = [["За 10 месяцев PracticeFlow должен превратить текущий API‑фундамент в замкнутый пользовательский маршрут: преподаватель публикует практику, студент сдаёт отчёт, преподаватель проверяет и выгружает результат. Коммерческая цель — 2 платных пилота и 2 годовые лицензии, которые формируют доказательство спроса для следующего раунда продаж."]];
  style(sheet.getRange("A17:H19"), { fill: "#EEF0FF", font: { bold: true, color: C.ink, size: 11 }, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: C.line } });
  sheet.getRange("A17:H19").format.rowHeight = 34;
  sheet.showGridLines = false;
}

function addForecast(sheet) {
  title(sheet, "Прогноз выручки и операционного потока — 3 года", "Базовый сценарий, без налогов и без оценки доли инвестора. Все драйверы — с листа 03; суммы в ₸.", "H");
  setColumnWidths(sheet, { A: 40, B: 17, C: 17, D: 17, E: 4, F: 31, G: 18, H: 24 });
  section(sheet, "A4:D4", "Финансовая модель");
  sheet.getRange("A5:D5").values = [["Показатель", "Год 1", "Год 2", "Год 3"]];
  headerRow(sheet, "A5:D5");
  const labels = [
    "Активные годовые лицензии, шт.",
    "Новые годовые лицензии, шт.",
    "Платные пилоты, шт.",
    "Цена годовой лицензии, ₸",
    "Цена пилота, ₸",
    "Онбординг, ₸",
    "Выручка: годовые лицензии",
    "Выручка: пилоты",
    "Выручка: онбординг",
    "Итого выручка",
    "COGS, %",
    "COGS, ₸",
    "Валовая прибыль",
    "Операционные расходы",
    "Операционный денежный поток",
    "Операционная маржа",
    "Накопленный операционный поток",
    "Выручка для безубыточности",
    "Лицензий для безубыточности, шт.",
    "Накопленный поток после инвестиций",
  ];
  sheet.getRange("A6:A25").values = labels.map((x) => [x]);
  const formulas = [
    ["='03_Допущения'!$B$13", "='03_Допущения'!$B$14", "='03_Допущения'!$B$15"],
    ["='03_Допущения'!$B$16", "='03_Допущения'!$B$18", "='03_Допущения'!$B$20"],
    ["='03_Допущения'!$B$17", "='03_Допущения'!$B$19", "='03_Допущения'!$B$21"],
    ["='03_Допущения'!$B$10", "='03_Допущения'!$B$10", "='03_Допущения'!$B$10"],
    ["='03_Допущения'!$B$9", "='03_Допущения'!$B$9", "='03_Допущения'!$B$9"],
    ["='03_Допущения'!$B$11", "='03_Допущения'!$B$11", "='03_Допущения'!$B$11"],
    ["=B6*B9", "=C6*C9", "=D6*D9"],
    ["=B8*B10", "=C8*C10", "=D8*D10"],
    ["=B7*B11", "=C7*C11", "=D7*D11"],
    ["=SUM(B12:B14)", "=SUM(C12:C14)", "=SUM(D12:D14)"],
    ["='03_Допущения'!$B$12", "='03_Допущения'!$B$12", "='03_Допущения'!$B$12"],
    ["=B15*B16", "=C15*C16", "=D15*D16"],
    ["=B15-B17", "=C15-C17", "=D15-D17"],
    ["='03_Допущения'!$B$22", "='03_Допущения'!$B$23", "='03_Допущения'!$B$24"],
    ["=B18-B19", "=C18-C19", "=D18-D19"],
    ["=IF(B15=0,0,B20/B15)", "=IF(C15=0,0,C20/C15)", "=IF(D15=0,0,D20/D15)"],
    ["=B20", "=B22+C20", "=C22+D20"],
    ["=B19/(1-B16)", "=C19/(1-C16)", "=D19/(1-D16)"],
    ["=ROUNDUP(B23/B9,0)", "=ROUNDUP(C23/C9,0)", "=ROUNDUP(D23/D9,0)"],
    ["=B22-'03_Допущения'!$B$6", "=C22-'03_Допущения'!$B$6", "=D22-'03_Допущения'!$B$6"],
  ];
  sheet.getRange("B6:D25").formulas = formulas;
  formulaLink(sheet, "B6:D8", number);
  formulaLink(sheet, "B9:D11", money);
  calculation(sheet, "B12:D15", money);
  formulaLink(sheet, "B16:D16", percent);
  calculation(sheet, "B17:D20", money);
  calculation(sheet, "B21:D21", percent);
  calculation(sheet, "B22:D23", money);
  calculation(sheet, "B24:D24", number);
  style(sheet.getRange("A6:D25"), { verticalAlignment: "center", borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("A6:D25").format.rowHeight = 22;
  calculation(sheet, "B25:D25", money, true);
  [15, 18, 20, 22, 24, 25].forEach((row) => {
    style(sheet.getRange(`A${row}:D${row}`), { fill: row === 20 ? "#DDF5EC" : "#E8ECF8", font: { bold: true, color: C.ink } });
  });
  sheet.getRange("A15:D15").format.borders = { preset: "doubleBottom", style: "medium", color: C.teal };
  sheet.getRange("A20:D20").format.borders = { preset: "doubleBottom", style: "medium", color: C.teal };

  section(sheet, "F4:H4", "Как читать модель");
  sheet.getRange("F5:H10").values = [
    ["Выручка", "Лицензии + пилоты + онбординг", "Контрактная модель B2B SaaS"],
    ["COGS", "Инфраструктура и сопровождение", "Не включает продуктовую команду"],
    ["Опер. поток", "Валовая прибыль − OpEx", "До налогообложения"],
    ["Безубыточность", "Выручка, покрывающая OpEx", "Считается без разовых платежей"],
    ["Окупаемость 5 млн", "Год 3 в базовом сценарии", "По строке накопленного потока после инвестиций"],
    ["Риск", "Длинный цикл закупки", "Сначала продаём пилот, затем годовую лицензию"],
  ];
  style(sheet.getRange("F5:H10"), { fill: C.pale, wrapText: true, verticalAlignment: "center", borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("F5:H10").format.rowHeight = 34;
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(5);
}

function addScenarios(sheet) {
  title(sheet, "Сценарии — чувствительность к цене и продажам", "Сценарии меняют ключевые драйверы Года 3. Базовая строка согласована с прогнозом на листе 05.", "L");
  setColumnWidths(sheet, { A: 18, B: 17, C: 15, D: 15, E: 17, F: 17, G: 15, H: 13, I: 17, J: 18, K: 18, L: 19 });
  section(sheet, "A4:L4", "Сценарная таблица — Год 3");
  sheet.getRange("A5:L5").values = [["Сценарий", "Лицензия, ₸", "Онбординг, ₸", "Пилот, ₸", "Активные лицензии", "Новые лицензии", "Пилоты", "COGS", "OpEx, ₸", "Выручка, ₸", "Опер. поток, ₸", "Лицензий для BE"]];
  headerRow(sheet, "A5:L5");
  sheet.getRange("A6:I8").values = [
    ["Консервативный", 1000000, 200000, 300000, 9, 5, 3, 0.18, 9200000],
    ["Базовый", 1200000, 250000, 350000, 15, 8, 5, 0.15, 9600000],
    ["Ускоренный", 1400000, 300000, 450000, 22, 10, 7, 0.13, 11000000],
  ];
  financeInput(sheet, "B6:I8");
  sheet.getRange("B6:D8").format.numberFormat = money;
  sheet.getRange("E6:G8").format.numberFormat = number;
  sheet.getRange("H6:H8").format.numberFormat = percent;
  sheet.getRange("I6:I8").format.numberFormat = money;
  sheet.getRange("J6").formulas = [["=E6*B6+F6*C6+G6*D6"]];
  sheet.getRange("J6:J8").fillDown();
  sheet.getRange("K6").formulas = [["=J6*(1-H6)-I6"]];
  sheet.getRange("K6:K8").fillDown();
  sheet.getRange("L6").formulas = [["=ROUNDUP((I6/(1-H6))/B6,0)"]];
  sheet.getRange("L6:L8").fillDown();
  calculation(sheet, "J6:K8", money);
  calculation(sheet, "L6:L8", number);
  style(sheet.getRange("A6:L8"), { verticalAlignment: "center", borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  style(sheet.getRange("A7:L7"), { fill: "#DDF5EC", font: { bold: true, color: C.ink } });
  sheet.getRange("A6:L8").format.rowHeight = 26;

  section(sheet, "A11:F11", "Интерпретация");
  sheet.getRange("A12:F16").values = [
    ["Консервативный", "9 лицензий к Году 3", "Выручки не хватает для роста команды", "Нужен грант/софинансирование или выше тариф", "", ""],
    ["Базовый", "15 лицензий к Году 3", "Окупаемость 5 млн в Году 3", "Цель первого коммерческого цикла", "", ""],
    ["Ускоренный", "22 лицензии к Году 3", "Можно расширять customer success и продажи", "Нужен сильный канал и кейсы", "", ""],
    ["Правило", "Не снижать цену без доказанной конверсии", "Пилот продаёт доверие; лицензия — повторяемую ценность", "Сначала измерить экономию времени преподавателя", "", ""],
    ["Ключевая метрика", "Конверсия пилот → годовой договор", "Владелец: product/sales", "Цель: ≥60% после первых пилотов", "", ""],
  ];
  style(sheet.getRange("A12:F16"), { fill: C.pale, wrapText: true, verticalAlignment: "center", borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("A12:F16").format.rowHeight = 62;
  sheet.showGridLines = false;
}

function addChecks(sheet) {
  title(sheet, "Проверки модели", "Контроль связей между бюджетом, прогнозом и базовым сценарием. Статус должен быть PASS перед использованием расчёта.", "F");
  setColumnWidths(sheet, { A: 36, B: 18, C: 18, D: 18, E: 14, F: 50 });
  section(sheet, "A4:F4", "MODEL STATUS");
  sheet.getRange("A5:B5").values = [["Итоговый статус", null]];
  sheet.getRange("B5").formulas = [["=IF(AND(E8=\"OK\",E9=\"OK\",E10=\"OK\",E11=\"OK\",E12=\"OK\"),\"PASS\",\"FAIL\")"]];
  style(sheet.getRange("A5:B5"), { fill: "#E8ECF8", font: { bold: true, color: C.ink, size: 12 }, verticalAlignment: "center" });
  sheet.getRange("A5:B5").format.rowHeight = 28;
  sheet.getRange("A7:F7").values = [["Проверка", "Факт", "Ожидание", "Отклонение", "Статус", "Комментарий"]];
  headerRow(sheet, "A7:F7");
  const rows = [
    ["Инвестиции распределены полностью", "='04_Инвестиции_5м'!$C$13", "='03_Допущения'!$B$6", "=B8-C8", "=IF(D8=0,\"OK\",\"FAIL\")", "Итого use of funds должен равняться 5 млн ₸."],
    ["Резерв неотрицательный", "='03_Допущения'!$B$8", "=0", "=B9-C9", "=IF(B9>=C9,\"OK\",\"FAIL\")", "Резерв нужен для нестабильности раннего MVP."],
    ["Базовая выручка Года 3 сходится", "='05_Прогноз_3г'!$D$15", "='06_Сценарии'!$J$7", "=B10-C10", "=IF(D10=0,\"OK\",\"FAIL\")", "Базовая строка сценариев должна совпасть с прогнозом."],
    ["Базовый операционный поток Года 3 сходится", "='05_Прогноз_3г'!$D$20", "='06_Сценарии'!$K$7", "=B11-C11", "=IF(D11=0,\"OK\",\"FAIL\")", "Проверка модели доходов и затрат."],
    ["Операционный поток Года 2 положительный", "='05_Прогноз_3г'!$C$20", "=0", "=B12-C12", "=IF(B12>0,\"OK\",\"FAIL\")", "Базовый план должен иметь положительный поток во втором году."],
  ];
  rows.forEach((row, i) => {
    const r = 8 + i;
    sheet.getRange(`A${r}`).values = [[row[0]]];
    sheet.getRange(`B${r}`).formulas = [[row[1]]];
    sheet.getRange(`C${r}`).formulas = [[row[2]]];
    sheet.getRange(`D${r}`).formulas = [[row[3]]];
    sheet.getRange(`E${r}`).formulas = [[row[4]]];
    sheet.getRange(`F${r}`).values = [[row[5]]];
  });
  formulaLink(sheet, "B8:C12", money);
  calculation(sheet, "D8:D12", money);
  style(sheet.getRange("A8:F12"), { verticalAlignment: "center", wrapText: true, borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("A8:F12").format.rowHeight = 30;
  sheet.getRange("E8:E12").conditionalFormats.add("containsText", { text: "OK", format: { fill: "#DDF5EC", font: { bold: true, color: "#1D6B45" } } });
  sheet.getRange("E8:E12").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FCE3E3", font: { bold: true, color: C.red } } });
  sheet.getRange("B5").conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#DDF5EC", font: { bold: true, color: "#1D6B45" } } });
  sheet.getRange("B5").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FCE3E3", font: { bold: true, color: C.red } } });
  sheet.showGridLines = false;
}

function addSources(sheet) {
  title(sheet, "Источники и ограничения", "В модели нет внешних рыночных цен: коммерческие параметры помечены как допущения и должны быть заменены результатами пилота.", "G");
  setColumnWidths(sheet, { A: 22, B: 31, C: 22, D: 17, E: 24, F: 52, G: 28 });
  sheet.getRange("A4:G4").values = [["ID", "Материал", "Тип", "Дата", "Как использован", "Ограничение / заметка", "Расположение"]];
  headerRow(sheet, "A4:G4");
  sheet.getRange("A5:G9").values = [
    ["S1", "Аудит PracticeFlow", "Внутренний аудит кода", "2026-08-20", "Определение реализованного MVP и критичных гепов", "Не является коммерческой валидацией рынка.", "PracticeFlow_3rd_defense_audit_updated.pptx"],
    ["S2", "Опрос преподавателей", "Пользовательские скриншоты Google Forms", "2026-08-20", "Проблема трудоёмкости и готовность к пилоту", "6 ответов — качественный сигнал, не рыночная статистика.", "feedback/"],
    ["S3", "Экраны MVP", "Пользовательские UI‑скриншоты", "2026-08-20", "Подтверждение текущего продуктового фокуса", "Не подтверждает готовность end‑to‑end review/export UI.", "скриншоты реализованных тем/"],
    ["A1", "Цены, расходы, объёмы продаж", "Плановые допущения", "2026-08-20", "Финансовый прогноз и сценарии", "Не внешние котировки. Заменить после интервью и договорных предложений.", "Лист 03_Допущения"],
    ["A2", "Курс/оценка инвестора", "Не используется", "2026-08-20", "Не рассчитывается", "В этой версии нет valuation, доли инвестора, налоговой модели и debt schedule.", "—"],
  ];
  style(sheet.getRange("A5:G9"), { verticalAlignment: "top", wrapText: true, borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("A5:G9").format.rowHeight = 48;
  section(sheet, "A12:G12", "Как улучшить модель после первых интервью");
  sheet.mergeCells("A13:G16");
  sheet.getRange("A13").values = [["Замените тарифы и затраты на фактические коммерческие предложения; добавьте воронку продаж по каждому вузу; подтвердите срок закупки; разделите пилот и годовой договор по cash‑timing; добавьте налоги и инвесторскую долю только после выбора юридической структуры и условий раунда."]];
  style(sheet.getRange("A13:G16"), { fill: C.pale, font: { color: C.ink }, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: C.line } });
  sheet.getRange("A13:G16").format.rowHeight = 33;
  sheet.showGridLines = false;
}

function addSummary(sheet) {
  title(sheet, "PracticeFlow — инвестиционная бизнес‑модель", "Lean‑план на 5 000 000 ₸ для закрытия MVP‑гепов, запуска 2 пилотов и выхода на первые годовые лицензии. Базовый сценарий; не является инвестиционной рекомендацией.", "L");
  setColumnWidths(sheet, { A: 22, B: 18, C: 22, D: 18, E: 22, F: 18, G: 22, H: 18, I: 4, J: 16, K: 18, L: 18 });
  section(sheet, "A4:H4", "Ключевые показатели");
  const cards = [
    ["A5:B5", "A6:B7", "Инвестиции", "='03_Допущения'!$B$6", money],
    ["C5:D5", "C6:D7", "MVP‑программа", "='03_Допущения'!$B$7", number],
    ["E5:F5", "E6:F7", "Core burn / мес.", "='04_Инвестиции_5м'!$G$8", money],
    ["G5:H5", "G6:H7", "Лицензий для BE", "='05_Прогноз_3г'!$C$24", number],
    ["A9:B9", "A10:B11", "Выручка — Год 3", "='05_Прогноз_3г'!$D$15", money],
    ["C9:D9", "C10:D11", "Опер. поток — Год 2", "='05_Прогноз_3г'!$C$20", money],
    ["E9:F9", "E10:F11", "Опер. поток — Год 3", "='05_Прогноз_3г'!$D$20", money],
    ["G9:H9", "G10:H11", "Поток после 5 млн — Год 3", "='05_Прогноз_3г'!$D$25", money],
  ];
  cards.forEach(([head, body, label, formula, format]) => {
    sheet.mergeCells(head);
    sheet.getRange(head.split(":")[0]).values = [[label]];
    style(sheet.getRange(head), { fill: C.teal, font: { bold: true, color: C.white, size: 10 }, horizontalAlignment: "center", verticalAlignment: "center" });
    sheet.mergeCells(body);
    const anchor = body.split(":")[0];
    sheet.getRange(anchor).formulas = [[formula]];
    style(sheet.getRange(body), { fill: C.pale, font: { bold: true, color: C.ink, size: 15 }, horizontalAlignment: "center", verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: C.line } });
    sheet.getRange(anchor).format.numberFormat = format;
  });
  sheet.getRange("A5:H5").format.rowHeight = 22;
  sheet.getRange("A6:H7").format.rowHeight = 28;
  sheet.getRange("A9:H9").format.rowHeight = 22;
  sheet.getRange("A10:H11").format.rowHeight = 28;
  ["A6", "C6", "E6", "G6", "A10", "C10", "E10", "G10"].forEach((cell) => formulaLink(sheet, cell));
  sheet.getRange("A6").format.numberFormat = money;
  sheet.getRange("C6").format.numberFormat = number;
  sheet.getRange("E6").format.numberFormat = money;
  sheet.getRange("G6").format.numberFormat = number;
  sheet.getRange("A10:F10").format.numberFormat = money;
  sheet.getRange("G10").format.numberFormat = money;

  section(sheet, "A13:H13", "Инвестиционная логика");
  sheet.getRange("A14:H17").values = [
    ["1", "Закрыть критичные пользовательские гепы", "Publish, review/comments/history, export UI; стабилизировать Docker/PDF.", "", "", "", "", ""],
    ["2", "Проверить спрос платным пилотом", "2 кафедры/факультета; замерить время проверки, активацию и конверсию в годовой договор.", "", "", "", "", ""],
    ["3", "Продать годовую лицензию", "Тариф + онбординг; контрактное доказательство повторяемой ценности.", "", "", "", "", ""],
    ["4", "Масштабировать только после кейсов", "Базовый план: 7 активных лицензий во 2‑й год и 15 — в 3‑й.", "", "", "", "", ""],
  ];
  sheet.getRange("A14").format.numberFormat = number;
  style(sheet.getRange("A14:H17"), { fill: C.pale, verticalAlignment: "center", wrapText: true, borders: { preset: "insideHorizontal", style: "thin", color: C.line } });
  sheet.getRange("A14:H17").format.rowHeight = 56;
  sheet.getRange("A14:A17").format.font = { bold: true, color: C.blue, size: 14 };
  sheet.getRange("B14:B17").format.font = { bold: true, color: C.ink };

  sheet.getRange("J3:L3").values = [["Период", "Выручка, ₸", "Опер. поток, ₸"]];
  sheet.getRange("J4:L6").formulas = [
    ["=\"Год 1\"", "='05_Прогноз_3г'!B15", "='05_Прогноз_3г'!B20"],
    ["=\"Год 2\"", "='05_Прогноз_3г'!C15", "='05_Прогноз_3г'!C20"],
    ["=\"Год 3\"", "='05_Прогноз_3г'!D15", "='05_Прогноз_3г'!D20"],
  ];
  formulaLink(sheet, "J4:L6", money);
  sheet.getRange("J4:J6").format.numberFormat = "@";
  const chart = sheet.charts.add("bar", sheet.getRange("J3:L6"));
  chart.title = "Выручка и операционный поток, ₸";
  chart.hasLegend = true;
  chart.yAxis = { numberFormatCode: '#,##0' };
  chart.setPosition("J8", "L22");
  sheet.showGridLines = false;
}

async function main() {
  await fs.mkdir(TMP, { recursive: true });
  await fs.mkdir(OUT_DIR, { recursive: true });

  const workbook = Workbook.create();
  const summary = workbook.worksheets.add("01_Резюме");
  const bmc = workbook.worksheets.add("02_BMC");
  const assumptions = workbook.worksheets.add("03_Допущения");
  const investment = workbook.worksheets.add("04_Инвестиции_5м");
  const forecast = workbook.worksheets.add("05_Прогноз_3г");
  const scenarios = workbook.worksheets.add("06_Сценарии");
  const checks = workbook.worksheets.add("07_Проверки");
  const sources = workbook.worksheets.add("08_Источники");

  addBusinessModelCanvas(bmc);
  addAssumptions(assumptions, workbook);
  addInvestment(investment);
  addForecast(forecast);
  addScenarios(scenarios);
  addChecks(checks);
  addSources(sources);
  addSummary(summary);

  const sheetsToRender = ["01_Резюме", "02_BMC", "03_Допущения", "04_Инвестиции_5м", "05_Прогноз_3г", "06_Сценарии", "07_Проверки", "08_Источники"];
  for (const name of sheetsToRender) {
    const image = await workbook.render({ sheetName: name, autoCrop: "all", scale: 1.25, format: "png" });
    await saveBlob(`${TMP}/${name}.png`, image);
  }

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(OUT);
  const verification = await workbook.inspect({ kind: "table", range: "01_Резюме!A1:L22", include: "values,formulas", tableMaxRows: 24, tableMaxCols: 12 });
  await fs.writeFile(`${TMP}/summary-inspect.ndjson`, verification.ndjson);
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
  await fs.writeFile(`${TMP}/formula-errors.ndjson`, errors.ndjson);
  console.log(JSON.stringify({ output: OUT, sheets: sheetsToRender.length }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
