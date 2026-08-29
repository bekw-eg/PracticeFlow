import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const ROOT = "C:/Users/zdeat/Downloads/practiceflow-phase3-backend-checkpoint_1";
const WORK = `${ROOT}/.codex-tmp/presentation-audit/update-with-screenshots`;
const SOURCE = `${WORK}/template-starter.pptx`;
const OUT = `${ROOT}/PracticeFlow_3rd_defense_audit_updated.pptx`;

const C = {
  navy: "#10182A",
  blue: "#6D72FF",
  mint: "#67D4B0",
  ink: "#18233A",
  muted: "#60708D",
  pale: "#F5F7FC",
  line: "#DCE3F0",
  white: "#FFFFFF",
};

async function writeBlob(path, blob) {
  await fs.writeFile(path, new Uint8Array(await blob.arrayBuffer()));
}

async function imageBytes(path) {
  return new Uint8Array(await fs.readFile(path));
}

function addText(slide, text, x, y, w, h, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontSize: 18,
    color: C.ink,
    fontFace: "Aptos",
    ...style,
  };
  return shape;
}

function addRect(slide, x, y, w, h, fill, line = "none") {
  return slide.shapes.add({
    geometry: "roundRect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width: line === "none" ? 0 : 1 },
    borderRadius: "rounded-xl",
  });
}

function clearBodyKeepHeaderAndFooter(slide) {
  // Source slides are authored in header → body → footer order.  Preserve the
  // inherited visual anchors and remove only the slide-local body objects.
  for (let index = slide.shapes.items.length - 2; index >= 4; index -= 1) {
    slide.shapes.items[index].delete();
  }
}

function setSpeakerNotes(slide, text, sources) {
  slide.speakerNotes.textFrame.setText(`${text}\n\n[Sources]\n${sources}`);
  slide.speakerNotes.setVisible(true);
}

async function main() {
  await fs.mkdir(WORK, { recursive: true });
  const deck = await PresentationFile.importPptx(await FileBlob.load(SOURCE));
  const slide3 = deck.slides.items[2];
  const slide6 = deck.slides.items[5];

  // Preserve before snapshots for the two revised inherited slides.
  await writeBlob(`${WORK}/slide-3-before.png`, await deck.export({ slide: slide3, format: "png", scale: 1 }));
  await writeBlob(`${WORK}/slide-6-before.png`, await deck.export({ slide: slide6, format: "png", scale: 1 }));

  // Slide 3 — replace survey placeholders with the supplied Forms screenshots.
  slide3.shapes.items[1].text = "Опрос подтверждает проблему проверки";
  clearBodyKeepHeaderAndFooter(slide3);
  addText(slide3, "6 преподавателей • 83,3% тратят 5–10 часов в неделю на проверку", 72, 184, 1040, 30, {
    fontSize: 19,
    color: C.muted,
  });
  const reviewImg = await imageBytes(`${ROOT}/feedback/Screenshot 2026-08-20 220429.png`);
  const pilotImg = await imageBytes(`${ROOT}/feedback/Screenshot 2026-08-20 220521.png`);
  const surveyFrames = [
    { x: 72, label: "Время на проверку", bytes: reviewImg, alt: "Опрос: время преподавателя на проверку отчётов" },
    { x: 638, label: "Готовность к пилоту", bytes: pilotImg, alt: "Опрос: готовность преподавателей тестировать первую версию" },
  ];
  for (const frame of surveyFrames) {
    addRect(slide3, frame.x, 244, 530, 236, C.white, C.line);
    slide3.images.add({
      blob: frame.bytes,
      contentType: "image/png",
      alt: frame.alt,
      fit: "contain",
      geometry: "roundRect",
      borderRadius: "rounded-xl",
      position: { left: frame.x + 10, top: 254, width: 510, height: 216 },
    });
    addText(slide3, frame.label, frame.x, 492, 530, 24, {
      fontSize: 16,
      bold: true,
      color: C.ink,
      alignment: "center",
    });
  }
  addRect(slide3, 72, 550, 1096, 64, "#EEF0FF", "none");
  addText(slide3, "Вывод: проблема измерима, а готовность к раннему пилоту — высокая.", 100, 566, 1040, 28, {
    fontSize: 22,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
  setSpeakerNotes(
    slide3,
    "Опрос уже даёт опору для пилота: 83,3% опрошенных преподавателей тратят на проверку отчётов 5–10 часов в неделю, а 83,3% готовы протестировать первую версию. Это подтверждает и трудоёмкость текущего процесса, и готовность перейти к проверке в единой платформе.",
    "Пользовательские материалы, папка feedback: Screenshot 2026-08-20 220429.png и Screenshot 2026-08-20 220521.png (6 ответов).",
  );

  // Slide 6 — use only real, supplied product screenshots; no mock UI is added.
  slide6.shapes.items[1].text = "Реальные экраны MVP";
  clearBodyKeepHeaderAndFooter(slide6);
  addText(slide6, "Учитель и студент: группы, шаблоны и отчёты — фактические экраны реализации.", 72, 184, 1040, 30, {
    fontSize: 19,
    color: C.muted,
  });
  const screenDir = `${WORK}/cropped-screens`;
  const screens = [
    {
      x: 72, y: 246, label: "Учитель • Мои группы",
      file: "groups.png",
      alt: "Экран учителя: список групп",
    },
    {
      x: 638, y: 246, label: "Учитель • Шаблоны отчётов",
      file: "templates.png",
      alt: "Экран учителя: список шаблонов отчётов",
    },
    {
      x: 72, y: 466, label: "Учитель • Редактор шаблона",
      file: "template-editor.png",
      alt: "Экран учителя: редактор шаблона отчёта",
    },
    {
      x: 638, y: 466, label: "Студент • Редактор отчёта",
      file: "student-report.png",
      alt: "Экран студента: редактор отчёта",
    },
  ];
  for (const screen of screens) {
    addRect(slide6, screen.x, screen.y, 530, 170, C.white, C.line);
    slide6.images.add({
      blob: await imageBytes(`${screenDir}/${screen.file}`),
      contentType: "image/png",
      alt: screen.alt,
      fit: "cover",
      geometry: "roundRect",
      borderRadius: "rounded-xl",
      position: { left: screen.x + 2, top: screen.y + 2, width: 526, height: 166 },
    });
    addText(slide6, screen.label, screen.x, screen.y + 180, 530, 24, {
      fontSize: 16,
      bold: true,
      color: C.ink,
      alignment: "center",
    });
  }
  setSpeakerNotes(
    slide6,
    "На слайде — фактические экраны текущего MVP: преподаватель работает с группами, списком шаблонов и редактором структуры; студент заполняет свой отчёт. Экраны review и выгрузки здесь намеренно не показаны: для них есть backend API, но отдельного frontend-интерфейса пока нет.",
    "Пользовательские материалы, папка скриншоты реализованных тем: Screenshot 2026-08-20 215938.png, 220025.png, 220041.png и 220218.png.",
  );

  for (const [index, slide] of deck.slides.items.entries()) {
    await writeBlob(`${WORK}/final-slide-${String(index + 1).padStart(2, "0")}.png`, await deck.export({ slide, format: "png", scale: 1 }));
    await fs.writeFile(`${WORK}/final-slide-${String(index + 1).padStart(2, "0")}.layout.json`, await (await slide.export({ format: "layout" })).text());
  }
  await writeBlob(`${WORK}/final-montage.webp`, await deck.export({ format: "webp", montage: true, scale: 1 }));
  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(OUT);
  console.log(JSON.stringify({ output: OUT, slides: deck.slides.items.length }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
