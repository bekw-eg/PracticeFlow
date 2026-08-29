import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const deck = await PresentationFile.importPptx(await FileBlob.load("C:/Users/zdeat/Downloads/practiceflow-phase3-backend-checkpoint_1/.codex-tmp/presentation-audit/update-with-screenshots/template-starter.pptx"));
const slide = deck.slides.items[5];
const shape = slide.shapes.items[0];
console.log(JSON.stringify({
  slideCount: deck.slides.items.length,
  shapeCount: slide.shapes.items.length,
  slideId: slide.id,
  shapeId: shape.id,
  hasShapeDelete: typeof shape.delete,
  hasShapeRemove: typeof shape.remove,
  hasCollectionRemove: typeof slide.shapes.remove,
  hasCollectionDelete: typeof slide.shapes.delete,
  slideDelete: typeof slide.delete,
}, null, 2));
