export type ToastTone = "success" | "error" | "info";

export function showToast(message: string, tone: ToastTone = "success") {
  window.dispatchEvent(new CustomEvent("pf:toast", { detail: { message, tone } }));
}
