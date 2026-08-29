import fs from "node:fs/promises";
import sharp from "sharp";

const ROOT = "C:/Users/zdeat/Downloads/practiceflow-phase3-backend-checkpoint_1";
const SOURCE = `${ROOT}/скриншоты реализованных тем`;
const OUT = `${ROOT}/.codex-tmp/presentation-audit/update-with-screenshots/cropped-screens`;

const crops = [
  { input: "Screenshot 2026-08-20 215938.png", output: "groups.png", left: 0, top: 0, width: 1815, height: 595 },
  { input: "Screenshot 2026-08-20 220025.png", output: "templates.png", left: 0, top: 0, width: 1650, height: 541 },
  { input: "Screenshot 2026-08-20 220041.png", output: "template-editor.png", left: 0, top: 0, width: 1748, height: 573 },
  { input: "Screenshot 2026-08-20 220218.png", output: "student-report.png", left: 0, top: 0, width: 954, height: 313 },
];

await fs.mkdir(OUT, { recursive: true });
for (const crop of crops) {
  await sharp(`${SOURCE}/${crop.input}`)
    .extract({ left: crop.left, top: crop.top, width: crop.width, height: crop.height })
    .png()
    .toFile(`${OUT}/${crop.output}`);
}
console.log(JSON.stringify({ output: OUT, crops: crops.map(({ output }) => output) }, null, 2));
