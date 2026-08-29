import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const source = "C:/Users/zdeat/Downloads/practiceflow-phase3-backend-checkpoint_1/PracticeFlow_3rd_defense_audit.pptx";
const out = "C:/Users/zdeat/Downloads/practiceflow-phase3-backend-checkpoint_1/.codex-tmp/presentation-audit/update-with-screenshots";

const deck = await PresentationFile.importPptx(await FileBlob.load(source));
const snapshot = await deck.inspect({
  kind: "slide,textbox,shape,image,table,chart,notes,thread,layout",
  maxChars: 60000,
});
await fs.writeFile(`${out}/direct-inspect.ndjson`, snapshot.ndjson);
await fs.mkdir(`${out}/template-inspect`, { recursive: true });
await fs.writeFile(`${out}/template-inspect/template-inspect.ndjson`, snapshot.ndjson);
for (const [index, slide] of deck.slides.items.entries()) {
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(`${out}/source-slide-${index + 1}.layout.json`, await layout.text());
}
