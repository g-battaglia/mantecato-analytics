/**
 * Visual export utilities (PDF/PNG).
 * This module is intentionally separate from export.ts to avoid SSR issues —
 * jspdf pulls in fflate which uses Node.js Worker, incompatible with Turbopack SSR.
 * Only import this module dynamically at runtime: import("@/lib/export-visual")
 */

/**
 * Export a DOM element as a PNG image.
 */
export async function exportPNG(
  element: HTMLElement,
  filename = "export"
): Promise<void> {
  const html2canvas = (await import("html2canvas")).default;
  const canvas = await html2canvas(element, {
    backgroundColor: null,
    scale: 2,
    logging: false,
    useCORS: true,
  });
  const url = canvas.toDataURL("image/png");
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}.png`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/**
 * Export a DOM element as a PDF document.
 */
export async function exportPDF(
  element: HTMLElement,
  filename = "export",
  title?: string
): Promise<void> {
  const [html2canvas, { default: jsPDF }] = await Promise.all([
    import("html2canvas").then((m) => m.default),
    import("jspdf"),
  ]);

  const canvas = await html2canvas(element, {
    backgroundColor: "#ffffff",
    scale: 2,
    logging: false,
    useCORS: true,
  });

  const imgData = canvas.toDataURL("image/png");
  const imgWidth = canvas.width;
  const imgHeight = canvas.height;

  const margin = 40;

  const pdf = new jsPDF({
    orientation: "portrait",
    unit: "pt",
    format: "a4",
  });

  const actualPageWidth = pdf.internal.pageSize.getWidth();
  const actualPageHeight = pdf.internal.pageSize.getHeight();
  const actualContentWidth = actualPageWidth - margin * 2;
  const actualRatio = actualContentWidth / imgWidth;
  const actualScaledHeight = imgHeight * actualRatio;

  let yOffset = margin;

  // Optional title
  if (title) {
    pdf.setFontSize(16);
    pdf.text(title, margin, yOffset + 12);
    yOffset += 28;

    pdf.setFontSize(9);
    pdf.setTextColor(128);
    pdf.text(
      `Generated ${new Date().toLocaleString()}`,
      margin,
      yOffset + 8
    );
    pdf.setTextColor(0);
    yOffset += 20;
  }

  // If the image fits on one page
  if (actualScaledHeight + yOffset <= actualPageHeight - margin) {
    pdf.addImage(
      imgData,
      "PNG",
      margin,
      yOffset,
      actualContentWidth,
      actualScaledHeight
    );
  } else {
    // Multi-page: render full image, jsPDF clips automatically per page
    let remainingHeight = actualScaledHeight;
    let page = 0;

    while (remainingHeight > 0) {
      if (page > 0) {
        pdf.addPage();
        yOffset = margin;
      }

      const availableHeight = actualPageHeight - yOffset - margin;
      const sliceHeight = Math.min(remainingHeight, availableHeight);

      pdf.addImage(
        imgData,
        "PNG",
        margin,
        yOffset - (actualScaledHeight - remainingHeight),
        actualContentWidth,
        actualScaledHeight
      );

      remainingHeight -= sliceHeight;
      page++;

      if (page > 20) break;
    }
  }

  pdf.save(`${filename}.pdf`);
}
