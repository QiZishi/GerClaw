import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import { sanitizeFilename } from "./utils";

async function renderToCanvas(element: HTMLElement): Promise<HTMLCanvasElement> {
  return html2canvas(element, {
    backgroundColor: "#ffffff",
    scale: 2,
    useCORS: true,
    logging: false,
    ignoreElements: (el) => el.hasAttribute("data-html2canvas-ignore"),
  });
}

export async function exportToPng(element: HTMLElement, filename: string): Promise<void> {
  const canvas = await renderToCanvas(element);
  const link = document.createElement("a");
  link.download = `${sanitizeFilename(filename)}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

export async function exportToJpg(element: HTMLElement, filename: string, quality = 0.92): Promise<void> {
  const canvas = await renderToCanvas(element);
  const link = document.createElement("a");
  link.download = `${sanitizeFilename(filename)}.jpg`;
  link.href = canvas.toDataURL("image/jpeg", quality);
  link.click();
}

export async function exportToPdf(element: HTMLElement, filename: string): Promise<void> {
  const canvas = await renderToCanvas(element);

  const imgData = canvas.toDataURL("image/png");
  const pdf = new jsPDF("p", "mm", "a4");

  const pdfWidth = pdf.internal.pageSize.getWidth();
  const pdfHeight = pdf.internal.pageSize.getHeight();
  const imgWidth = pdfWidth;
  const imgHeight = (canvas.height * imgWidth) / canvas.width;

  let heightLeft = imgHeight;
  let position = 0;
  const margin = 0;

  pdf.addImage(imgData, "PNG", margin, position, imgWidth, imgHeight);
  heightLeft -= pdfHeight;

  while (heightLeft > 0) {
    position = heightLeft - imgHeight;
    pdf.addPage();
    pdf.addImage(imgData, "PNG", margin, position, imgWidth, imgHeight);
    heightLeft -= pdfHeight;
  }

  pdf.save(`${sanitizeFilename(filename)}.pdf`);
}
