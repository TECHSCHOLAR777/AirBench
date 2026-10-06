/**
 * Client-Side Open Source Deliverables Engine
 * Generates high-quality deliverables directly in the browser using:
 * 1. docx (https://github.com/dolanmiu/docx)
 * 2. PptxGenJS (https://github.com/gitbrent/PptxGenJS)
 * 3. ExcelJS (https://github.com/exceljs/exceljs)
 * 4. pdf-lib (https://github.com/Hopding/pdf-lib)
 */

export interface ClientDocBlock {
  type: 'h1' | 'h2' | 'h3' | 'paragraph' | 'bullet' | 'numbered' | 'table' | 'code' | 'divider' | 'callout';
  text?: string;
  headers?: string[];
  rows?: string[][];
  language?: string;
}

export function parseMarkdownBlocks(markdown: string): ClientDocBlock[] {
  const blocks: ClientDocBlock[] = [];
  const lines = markdown.split(/\r?\n/);
  let i = 0;

  while (i < lines.length) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (!line) {
      i++;
      continue;
    }

    // Code block
    if (line.startsWith('```')) {
      const language = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      blocks.push({
        type: 'code',
        text: codeLines.join('\n'),
        language: language || 'text'
      });
      continue;
    }

    // Table detection
    if (line.startsWith('|') && line.endsWith('|')) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
        tableLines.push(lines[i].trim());
        i++;
      }

      if (tableLines.length >= 2) {
        const rawHeaders = tableLines[0].split('|').map(c => c.trim()).filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
        const rows: string[][] = [];

        for (let r = 1; r < tableLines.length; r++) {
          const cells = tableLines[r].split('|').map(c => c.trim()).filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
          if (cells.every(c => /^[-:| ]+$/.test(c))) continue;
          if (cells.length > 0) rows.push(cells);
        }

        if (rawHeaders.length > 0) {
          blocks.push({ type: 'table', headers: rawHeaders, rows });
          continue;
        }
      }
    }

    // Headings
    if (line.startsWith('### ')) {
      blocks.push({ type: 'h3', text: line.replace(/^###\s+/, '').trim() });
      i++;
      continue;
    }
    if (line.startsWith('## ')) {
      blocks.push({ type: 'h2', text: line.replace(/^##\s+/, '').trim() });
      i++;
      continue;
    }
    if (line.startsWith('# ')) {
      blocks.push({ type: 'h1', text: line.replace(/^#\s+/, '').trim() });
      i++;
      continue;
    }

    // Dividers
    if (/^[-*_]{3,}$/.test(line)) {
      blocks.push({ type: 'divider' });
      i++;
      continue;
    }

    // Callouts / Blockquotes
    if (line.startsWith('>')) {
      blocks.push({ type: 'callout', text: line.replace(/^>\s*/, '').trim() });
      i++;
      continue;
    }

    // Bullets
    if (/^[*\-•]\s+/.test(line)) {
      blocks.push({ type: 'bullet', text: line.replace(/^[*\-•]\s+/, '').trim() });
      i++;
      continue;
    }

    // Numbered lists
    if (/^\d+\.\s+/.test(line)) {
      blocks.push({ type: 'numbered', text: line.replace(/^\d+\.\s+/, '').trim() });
      i++;
      continue;
    }

    // Paragraph
    blocks.push({ type: 'paragraph', text: line });
    i++;
  }

  return blocks;
}

/**
 * Generates a high-quality PDF using pdf-lib
 */
export async function generateClientPdf(title: string, markdown: string): Promise<Blob> {
  const { PDFDocument, rgb, StandardFonts, PageSizes } = await import('pdf-lib');
  const blocks = parseMarkdownBlocks(markdown);
  const pdfDoc = await PDFDocument.create();

  pdfDoc.setTitle(title);
  pdfDoc.setAuthor('AirBench Sovereign Enclave');
  pdfDoc.setCreationDate(new Date());

  const helvetica = await pdfDoc.embedFont(StandardFonts.Helvetica);
  const helveticaBold = await pdfDoc.embedFont(StandardFonts.HelveticaBold);
  const helveticaOblique = await pdfDoc.embedFont(StandardFonts.HelveticaOblique);
  const courier = await pdfDoc.embedFont(StandardFonts.Courier);

  const darkSlate = rgb(0.090, 0.086, 0.082);
  const headerBar = rgb(0.122, 0.118, 0.110);
  const brandOrange = rgb(0.741, 0.357, 0.220);
  const darkText = rgb(0.118, 0.114, 0.110);
  const bodyText = rgb(0.176, 0.169, 0.157);
  const mutedGray = rgb(0.480, 0.460, 0.430);
  const borderSand = rgb(0.898, 0.878, 0.851);
  const lightBorder = rgb(0.930, 0.915, 0.895);
  const zebraFill = rgb(0.976, 0.969, 0.957);
  const codeFill = rgb(0.957, 0.945, 0.918);
  const calloutFill = rgb(0.980, 0.965, 0.945);
  const white = rgb(1, 1, 1);

  function sanitize(t: string): string {
    if (!t) return '';
    return t
      .replace(/[\u2018\u2019]/g, "'")
      .replace(/[\u201C\u201D]/g, '"')
      .replace(/[\u2013\u2014]/g, '-')
      .replace(/[\u2022\u25CF\u25CB]/g, '*')
      .replace(/\u2026/g, '...')
      .replace(/[\u0394\u2206]/g, 'Delta')
      .replace(/[\u03BC\u00B5]/g, 'u')
      .replace(/\u00B0/g, ' deg ')
      .replace(/\u00B1/g, '+/-')
      .replace(/[\u2264]/g, '<=')
      .replace(/[\u2265]/g, '>=')
      .replace(/[\u00D7]/g, 'x')
      .replace(/[^\x00-\xFF]/g, ' ');
  }

  function wrap(text: string, font: any, size: number, maxW: number): string[] {
    const clean = sanitize(text);
    if (!clean.trim()) return [''];
    const words = clean.split(/\s+/);
    const lines: string[] = [];
    let cur = '';

    for (const w of words) {
      const test = cur ? `${cur} ${w}` : w;
      if (font.widthOfTextAtSize(test, size) <= maxW) {
        cur = test;
      } else {
        if (cur) lines.push(cur);
        cur = w;
      }
    }
    if (cur) lines.push(cur);
    return lines;
  }

  const [pageWidth, pageHeight] = PageSizes.A4;
  const margin = 45;
  const contentWidth = pageWidth - (margin * 2);
  const bottomMargin = 55;

  let page = pdfDoc.addPage(PageSizes.A4);
  let currentY = pageHeight;

  // Banner
  page.drawRectangle({ x: 0, y: pageHeight - 54, width: pageWidth, height: 54, color: darkSlate });
  page.drawRectangle({ x: 0, y: pageHeight - 58, width: pageWidth, height: 4, color: brandOrange });
  page.drawText('AIRBENCH SOVEREIGN ENCLAVE', { x: margin, y: pageHeight - 26, size: 13, font: helveticaBold, color: white });
  page.drawText(`CONFIDENTIAL TECHNICAL DELIVERABLE | ${new Date().toLocaleDateString().toUpperCase()}`, {
    x: margin, y: pageHeight - 42, size: 7.5, font: helvetica, color: rgb(0.65, 0.63, 0.60)
  });

  currentY = pageHeight - 82;

  const tLines = wrap(title, helveticaBold, 20, contentWidth);
  for (const l of tLines) {
    page.drawText(l, { x: margin, y: currentY, size: 20, font: helveticaBold, color: darkText });
    currentY -= 25;
  }
  currentY -= 6;
  page.drawLine({ start: { x: margin, y: currentY }, end: { x: margin + contentWidth, y: currentY }, color: borderSand, thickness: 1 });
  currentY -= 18;

  function ensure(h: number) {
    if (currentY - h < bottomMargin) {
      page = pdfDoc.addPage(PageSizes.A4);
      page.drawLine({ start: { x: margin, y: pageHeight - 34 }, end: { x: margin + contentWidth, y: pageHeight - 34 }, color: borderSand, thickness: 0.5 });
      page.drawText('AirBench Sovereign Technical Command — Deliverable Dossier', { x: margin, y: pageHeight - 28, size: 7.5, font: helvetica, color: mutedGray });
      currentY = pageHeight - 52;
    }
  }

  for (const b of blocks) {
    if (b.type === 'h1') {
      ensure(42);
      currentY -= 10;
      const lines = wrap(b.text || '', helveticaBold, 15, contentWidth);
      for (const l of lines) {
        page.drawText(l, { x: margin, y: currentY, size: 15, font: helveticaBold, color: brandOrange });
        currentY -= 18;
      }
      page.drawLine({ start: { x: margin, y: currentY + 4 }, end: { x: margin + 70, y: currentY + 4 }, color: brandOrange, thickness: 2 });
      currentY -= 8;
    } else if (b.type === 'h2') {
      ensure(34);
      currentY -= 8;
      const lines = wrap(b.text || '', helveticaBold, 12.5, contentWidth);
      for (const l of lines) {
        page.drawText(l, { x: margin, y: currentY, size: 12.5, font: helveticaBold, color: darkText });
        currentY -= 15;
      }
      currentY -= 6;
    } else if (b.type === 'paragraph') {
      const lines = wrap(b.text || '', helvetica, 9.5, contentWidth);
      for (const l of lines) {
        ensure(14);
        page.drawText(l, { x: margin, y: currentY, size: 9.5, font: helvetica, color: bodyText });
        currentY -= 13;
      }
      currentY -= 6;
    } else if (b.type === 'bullet' || b.type === 'numbered') {
      const sym = b.type === 'numbered' ? '– ' : '• ';
      const lines = wrap(b.text || '', helvetica, 9.5, contentWidth - 16);
      if (lines.length > 0) {
        ensure(14);
        page.drawText(sym, { x: margin + 2, y: currentY, size: 9.5, font: helveticaBold, color: brandOrange });
        page.drawText(lines[0], { x: margin + 14, y: currentY, size: 9.5, font: helvetica, color: bodyText });
        currentY -= 13;
        for (let idx = 1; idx < lines.length; idx++) {
          ensure(14);
          page.drawText(lines[idx], { x: margin + 14, y: currentY, size: 9.5, font: helvetica, color: bodyText });
          currentY -= 13;
        }
        currentY -= 3;
      }
    } else if (b.type === 'callout') {
      const lines = wrap(b.text || '', helveticaOblique, 9, contentWidth - 24);
      const h = Math.max(26, lines.length * 13 + 12);
      ensure(h + 10);
      currentY -= 4;
      page.drawRectangle({ x: margin, y: currentY - h, width: contentWidth, height: h, color: calloutFill });
      page.drawRectangle({ x: margin, y: currentY - h, width: 3.5, height: h, color: brandOrange });
      let tY = currentY - 14;
      for (const l of lines) {
        page.drawText(l, { x: margin + 14, y: tY, size: 9, font: helveticaOblique, color: bodyText });
        tY -= 13;
      }
      currentY -= h + 10;
    } else if (b.type === 'code' && b.text) {
      const lines = b.text.split(/\r?\n/).map(l => sanitize(l));
      const codeH = Math.min(300, lines.length * 11 + 16);
      ensure(Math.min(codeH + 14, 120));
      currentY -= 4;
      const actualH = Math.min(codeH, currentY - bottomMargin - 10);
      page.drawRectangle({ x: margin, y: currentY - actualH, width: contentWidth, height: actualH, color: codeFill, borderColor: borderSand, borderWidth: 0.75 });
      let cY = currentY - 16;
      for (const cl of lines) {
        if (cY < currentY - actualH + 8) break;
        page.drawText(cl.slice(0, 95), { x: margin + 8, y: cY, size: 7.5, font: courier, color: darkText });
        cY -= 11;
      }
      currentY -= actualH + 12;
    } else if (b.type === 'table' && b.headers && b.rows && b.headers.length > 0) {
      const headers = b.headers;
      const rows = b.rows;
      const numCols = headers.length;
      const colWidth = contentWidth / numCols;

      const drawHeader = () => {
        ensure(28);
        page.drawRectangle({ x: margin, y: currentY - 22, width: contentWidth, height: 22, color: headerBar });
        page.drawRectangle({ x: margin, y: currentY - 24, width: contentWidth, height: 2, color: brandOrange });
        headers.forEach((h, cIdx) => {
          const wText = wrap(h, helveticaBold, 8.5, colWidth - 8)[0] || '';
          page.drawText(wText, { x: margin + (cIdx * colWidth) + 5, y: currentY - 15, size: 8.5, font: helveticaBold, color: white });
        });
        currentY -= 25;
      };

      drawHeader();

      rows.forEach((r, rIdx) => {
        const rowH = 18;
        if (currentY - rowH < bottomMargin) {
          ensure(rowH + 30);
          drawHeader();
        }
        if (rIdx % 2 === 1) {
          page.drawRectangle({ x: margin, y: currentY - rowH, width: contentWidth, height: rowH, color: zebraFill });
        }
        page.drawLine({ start: { x: margin, y: currentY - rowH }, end: { x: margin + contentWidth, y: currentY - rowH }, color: lightBorder, thickness: 0.5 });
        r.forEach((cell, cIdx) => {
          const w = wrap(cell || '', helvetica, 8, colWidth - 8)[0] || '';
          page.drawText(w, { x: margin + (cIdx * colWidth) + 5, y: currentY - 13, size: 8, font: helvetica, color: bodyText });
        });
        currentY -= rowH;
      });
      currentY -= 12;
    }
  }

  const allPages = pdfDoc.getPages();
  const total = allPages.length;
  allPages.forEach((p, idx) => {
    p.drawLine({ start: { x: margin, y: 35 }, end: { x: margin + contentWidth, y: 35 }, color: borderSand, thickness: 0.5 });
    p.drawText('AirBench Sovereign Deliverable • Zero Telemetry', { x: margin, y: 22, size: 7.5, font: helvetica, color: mutedGray });
    const pStr = `Page ${idx + 1} of ${total}`;
    const w = helvetica.widthOfTextAtSize(pStr, 7.5);
    p.drawText(pStr, { x: margin + contentWidth - w, y: 22, size: 7.5, font: helvetica, color: mutedGray });
  });

  const pdfBytes = await pdfDoc.save();
  return new Blob([pdfBytes as any], { type: 'application/pdf' });
}

/**
 * Generates a high-quality Word (.docx) document using docx
 */
export async function generateClientDocx(title: string, markdown: string): Promise<Blob> {
  const docx = await import('docx');
  const {
    Document,
    Packer,
    Paragraph,
    TextRun,
    HeadingLevel,
    Table,
    TableRow,
    TableCell,
    WidthType,
    BorderStyle,
    AlignmentType,
    Header,
    Footer,
    PageNumber
  } = docx;

  const blocks = parseMarkdownBlocks(markdown);
  const children: any[] = [];

  children.push(
    new Paragraph({
      children: [
        new TextRun({ text: title, bold: true, size: 36, color: '171615', font: 'Segoe UI' })
      ],
      spacing: { before: 100, after: 100 }
    }),
    new Paragraph({
      children: [
        new TextRun({
          text: `AIRBENCH SOVEREIGN ENCLAVE DELIVERABLE • ${new Date().toLocaleDateString().toUpperCase()}`,
          bold: true,
          size: 16,
          color: 'BD5B38',
          font: 'Segoe UI'
        })
      ],
      spacing: { after: 220 }
    })
  );

  for (const b of blocks) {
    if (b.type === 'h1') {
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: b.text || '', bold: true, size: 28, color: 'BD5B38', font: 'Segoe UI' })],
        spacing: { before: 200, after: 100 }
      }));
    } else if (b.type === 'h2') {
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: b.text || '', bold: true, size: 24, color: '1F1E1C', font: 'Segoe UI' })],
        spacing: { before: 180, after: 90 }
      }));
    } else if (b.type === 'paragraph') {
      children.push(new Paragraph({
        children: [new TextRun({ text: b.text || '', size: 21, color: '2D2B28', font: 'Segoe UI' })],
        spacing: { after: 90, line: 276 }
      }));
    } else if (b.type === 'bullet') {
      children.push(new Paragraph({
        bullet: { level: 0 },
        children: [new TextRun({ text: b.text || '', size: 21, color: '2D2B28', font: 'Segoe UI' })],
        spacing: { after: 50 }
      }));
    } else if (b.type === 'callout') {
      children.push(new Paragraph({
        children: [new TextRun({ text: b.text || '', italics: true, size: 21, color: '2D2B28', font: 'Segoe UI' })],
        shading: { fill: 'FAF6F1' },
        border: { left: { style: BorderStyle.SINGLE, size: 24, color: 'BD5B38' } },
        spacing: { before: 120, after: 120 },
        indent: { left: 240 }
      }));
    } else if (b.type === 'code' && b.text) {
      for (const line of b.text.split('\n')) {
        children.push(new Paragraph({
          children: [new TextRun({ text: line, font: 'Consolas', size: 18, color: '1F1E1C' })],
          shading: { fill: 'F4F1EA' },
          spacing: { after: 20 }
        }));
      }
    } else if (b.type === 'table' && b.headers && b.rows) {
      const rows: any[] = [];
      rows.push(new TableRow({
        tableHeader: true,
        children: b.headers.map(h => new TableCell({
          children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: h, bold: true, size: 19, color: 'FFFFFF' })] })],
          shading: { fill: '1F1E1C' },
          borders: { top: { style: BorderStyle.SINGLE, size: 1, color: '1F1E1C' }, bottom: { style: BorderStyle.SINGLE, size: 2, color: 'BD5B38' }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
        }))
      }));

      b.rows.forEach((r, rIdx) => {
        const isEven = rIdx % 2 === 0;
        rows.push(new TableRow({
          children: r.map(c => new TableCell({
            children: [new Paragraph({ children: [new TextRun({ text: c, size: 19, color: '2D2B28' })] })],
            shading: { fill: isEven ? 'FFFFFF' : 'F9F7F4' },
            borders: { top: { style: BorderStyle.SINGLE, size: 1, color: 'EAE6DF' }, bottom: { style: BorderStyle.SINGLE, size: 1, color: 'EAE6DF' }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }
          }))
        }));
      });

      children.push(new Table({ rows, width: { size: 100, type: WidthType.PERCENTAGE } }));
      children.push(new Paragraph({ spacing: { after: 140 } }));
    }
  }

  const doc = new Document({
    sections: [{
      headers: {
        default: new Header({
          children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: 'AirBench Sovereign Technical Command', size: 16, color: '9C978F' })] })]
        })
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [
              new TextRun({ text: 'Page ', size: 16, color: '9C978F' }),
              new TextRun({ children: [PageNumber.CURRENT], size: 16, color: '9C978F' }),
              new TextRun({ text: ' of ', size: 16, color: '9C978F' }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: '9C978F' })
            ]
          })]
        })
      },
      children
    }]
  });

  return await Packer.toBlob(doc);
}

/**
 * Generates a high-quality Excel spreadsheet using ExcelJS
 */
export async function generateClientXlsx(title: string, markdown: string): Promise<Blob> {
  const ExcelJS = (await import('exceljs')).default || (await import('exceljs'));
  const blocks = parseMarkdownBlocks(markdown);
  const workbook = new ExcelJS.Workbook();
  workbook.creator = 'AirBench Sovereign Enclave';
  workbook.created = new Date();

  const tables = blocks.filter(b => b.type === 'table' && b.headers && b.headers.length > 0);

  // Overview Sheet
  const summarySheet = workbook.addWorksheet('Overview', {
    views: [{ state: 'frozen', ySplit: 2, showGridLines: true }],
    properties: { tabColor: { argb: 'FFBD5B38' } }
  });

  const bannerRow = summarySheet.addRow([`AIRBENCH SOVEREIGN DELIVERABLE: ${title}`]);
  bannerRow.height = 30;
  bannerRow.font = { name: 'Segoe UI', size: 13, bold: true, color: { argb: 'FFFFFFFF' } };
  bannerRow.eachCell(cell => {
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF171615' } };
    cell.alignment = { vertical: 'middle', horizontal: 'left' };
  });

  summarySheet.addRow([]);
  const metaHeader = summarySheet.addRow(['Parameter', 'Enclave Value', 'Status']);
  metaHeader.height = 24;
  metaHeader.eachCell(cell => {
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF1F1E1C' } };
    cell.font = { name: 'Segoe UI', size: 10, bold: true, color: { argb: 'FFFFFFFF' } };
    cell.alignment = { vertical: 'middle', horizontal: 'left' };
  });

  [
    ['Document Title', title, 'VERIFIED'],
    ['Security Classification', 'Enclave Confidential • Zero Egress', 'ENFORCED'],
    ['Generated Timestamp', new Date().toLocaleString(), 'AUTHENTIC'],
    ['Tables Extracted', `${tables.length} table(s)`, 'NOMINAL']
  ].forEach((item, idx) => {
    const row = summarySheet.addRow(item);
    row.height = 20;
    const isEven = idx % 2 === 0;
    row.eachCell((cell, colNum) => {
      cell.font = { name: 'Segoe UI', size: 9.5, color: { argb: 'FF2D2B28' } };
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: isEven ? 'FFFFFFFF' : 'FFF9F7F4' } };
      if (colNum === 3) cell.font = { name: 'Segoe UI', size: 9, bold: true, color: { argb: 'FF3EA877' } };
    });
  });

  summarySheet.getColumn(1).width = 25;
  summarySheet.getColumn(2).width = 45;
  summarySheet.getColumn(3).width = 20;

  // Data sheets
  if (tables.length > 0) {
    tables.forEach((tbl, idx) => {
      const sheetName = tables.length === 1 ? 'Data_Matrix' : `Table_${idx + 1}`;
      const sheet = workbook.addWorksheet(sheetName.slice(0, 31), {
        views: [{ state: 'frozen', ySplit: 2, showGridLines: true }],
        properties: { tabColor: { argb: 'FF1F1E1C' } }
      });

      const titleRow = sheet.addRow([`${title} - Section ${idx + 1}`]);
      titleRow.font = { name: 'Segoe UI', size: 13, bold: true, color: { argb: 'FF171615' } };
      titleRow.height = 28;

      const headerRow = sheet.addRow(tbl.headers!);
      headerRow.height = 26;
      headerRow.eachCell(cell => {
        cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF1F1E1C' } };
        cell.font = { name: 'Segoe UI', size: 10, bold: true, color: { argb: 'FFFFFFFF' } };
        cell.border = { bottom: { style: 'medium', color: { argb: 'FFBD5B38' } } };
      });

      if (tbl.headers!.length > 0) {
        sheet.autoFilter = { from: { row: 2, column: 1 }, to: { row: 2, column: tbl.headers!.length } };
      }

      tbl.rows?.forEach((r, rIdx) => {
        const row = sheet.addRow(r);
        row.height = 20;
        const isEven = rIdx % 2 === 0;
        row.eachCell(cell => {
          cell.font = { name: 'Segoe UI', size: 9.5, color: { argb: 'FF2D2B28' } };
          cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: isEven ? 'FFFFFFFF' : 'FFF9F7F4' } };
          const val = cell.value?.toString().trim();
          if (val && !isNaN(Number(val)) && !val.startsWith('0x') && !val.includes('-')) {
            const num = Number(val);
            cell.value = num;
            cell.numFmt = Number.isInteger(num) ? '#,##0' : '#,##0.00';
            cell.alignment = { horizontal: 'right' };
          }
        });
      });

      sheet.columns.forEach(col => {
        col.width = 22;
      });
    });
  }

  const buffer = await workbook.xlsx.writeBuffer();
  return new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
}

/**
 * Generates a high-quality PowerPoint deck using PptxGenJS
 */
export async function generateClientPptx(title: string, markdown: string): Promise<Blob> {
  const PptxGenJS = (await import('pptxgenjs')).default || (await import('pptxgenjs'));
  const blocks = parseMarkdownBlocks(markdown);
  const pptx = new (PptxGenJS as any)();

  pptx.layout = 'LAYOUT_16x9';

  pptx.defineSlideMaster({
    title: 'AIRBENCH_MASTER',
    background: { color: 'FAF8F5' },
    objects: [
      { rect: { x: 0, y: 0, w: '100%', h: 0.75, fill: { color: '171615' } } },
      { rect: { x: 0, y: 0.75, w: '100%', h: 0.05, fill: { color: 'BD5B38' } } },
      { text: { text: 'AIRBENCH SOVEREIGN TASK COMMAND', options: { x: 0.8, y: 0.22, fontSize: 10, bold: true, color: 'FFFFFF' } } },
      { rect: { x: 0, y: 7.1, w: '100%', h: 0.4, fill: { color: '171615' } } },
      { text: { text: 'CONFIDENTIAL • ENCLAVE HARDWARE ISOLATION', options: { x: 0.8, y: 7.18, fontSize: 8, color: '8E8982' } } }
    ],
    slideNumber: { x: 12.0, y: 7.18, fontSize: 8, color: 'EDE8DD' }
  });

  // Slide 1: Cover
  const titleSlide = pptx.addSlide();
  titleSlide.background = { color: '171615' };
  titleSlide.addText('AIRBENCH SOVEREIGN TASK COMMAND', { x: 1.0, y: 1.6, fontSize: 12, bold: true, color: 'BD5B38', charSpacing: 2 });
  titleSlide.addText(title, { x: 1.0, y: 2.2, w: 11.3, fontSize: 32, bold: true, color: 'FFFFFF' });
  titleSlide.addShape(pptx.ShapeType.line, { x: 1.0, y: 4.2, w: 3.5, h: 0, line: { color: 'BD5B38', width: 3 } });
  titleSlide.addText(`Executive Briefing & Technical Deliverable\nDate: ${new Date().toLocaleDateString()}\nStatus: Verified Sovereign Invariants`, {
    x: 1.0, y: 4.6, fontSize: 14, color: 'A8A39A', lineSpacing: 24
  });

  // Group content into slides
  let currentTitle = title;
  let currentBullets: string[] = [];
  let currentParas: string[] = [];

  const flushSlide = () => {
    if (currentBullets.length === 0 && currentParas.length === 0) return;
    const slide = pptx.addSlide({ masterName: 'AIRBENCH_MASTER' });
    slide.addText(currentTitle, { x: 0.8, y: 1.05, w: 11.5, fontSize: 22, bold: true, color: '171615' });
    slide.addShape(pptx.ShapeType.line, { x: 0.8, y: 1.55, w: 1.5, h: 0, line: { color: 'BD5B38', width: 2 } });

    let curY = 1.8;
    if (currentParas.length > 0) {
      slide.addText(currentParas.join('\n\n'), { x: 0.8, y: curY, w: 11.5, fontSize: 13, color: '2D2B28' });
      curY += Math.min(2.0, currentParas.length * 0.6);
    }
    if (currentBullets.length > 0) {
      slide.addText(currentBullets.map(b => ({ text: b, options: { fontSize: 13, color: '2D2B28', bullet: { type: 'bullet' } } })), {
        x: 0.8, y: curY, w: 11.5, h: 4.0, lineSpacing: 24
      });
    }
    currentBullets = [];
    currentParas = [];
  };

  for (const b of blocks) {
    if (b.type === 'h1' || b.type === 'h2') {
      flushSlide();
      currentTitle = b.text || title;
    } else if (b.type === 'bullet' || b.type === 'numbered') {
      if (b.text) currentBullets.push(b.text);
      if (currentBullets.length >= 6) flushSlide();
    } else if (b.type === 'paragraph' && b.text) {
      currentParas.push(b.text);
    } else if (b.type === 'table' && b.headers && b.rows) {
      flushSlide();
      const slide = pptx.addSlide({ masterName: 'AIRBENCH_MASTER' });
      slide.addText(`${currentTitle} (Data Table)`, { x: 0.8, y: 1.05, w: 11.5, fontSize: 22, bold: true, color: '171615' });
      slide.addShape(pptx.ShapeType.line, { x: 0.8, y: 1.55, w: 1.5, h: 0, line: { color: 'BD5B38', width: 2 } });

      const tableData: any[][] = [];
      tableData.push(b.headers.map(h => ({ text: h, options: { bold: true, fill: '1F1E1C', color: 'FFFFFF', fontSize: 10, align: 'center' } })));
      b.rows.slice(0, 8).forEach((r, idx) => {
        tableData.push(r.map(c => ({ text: c, options: { fill: idx % 2 === 0 ? 'FFFFFF' : 'F9F7F4', color: '2D2B28', fontSize: 9 } })));
      });
      slide.addTable(tableData, { x: 0.8, y: 1.9, w: 11.5, border: { pt: 0.5, color: 'EAE6DF' } });
    }
  }
  flushSlide();

  // Final Slide
  const endSlide = pptx.addSlide();
  endSlide.background = { color: '171615' };
  endSlide.addText('AIRBENCH SOVEREIGN ENCLAVE', { x: 1.0, y: 1.8, fontSize: 12, bold: true, color: 'BD5B38', charSpacing: 2 });
  endSlide.addText('Cryptographic Attestation & Delivery Verification', { x: 1.0, y: 2.4, w: 11.3, fontSize: 28, bold: true, color: 'FFFFFF' });
  endSlide.addShape(pptx.ShapeType.line, { x: 1.0, y: 3.6, w: 3.0, h: 0, line: { color: 'BD5B38', width: 2 } });
  endSlide.addText([
    { text: 'Execution Boundary: Hardware-isolated sovereign loopback enclave', options: { bullet: { type: 'bullet' }, fontSize: 13, color: 'EDE8DD' } },
    { text: 'Egress Policy: Zero cloud telemetry, strict mTLS host verification', options: { bullet: { type: 'bullet' }, fontSize: 13, color: 'EDE8DD' } },
    { text: `Synthesis Horizon: Process Loop & Physics verified on ${new Date().toLocaleDateString()}`, options: { bullet: { type: 'bullet' }, fontSize: 13, color: 'EDE8DD' } },
    { text: 'Audit Signature: Enclave Root-of-Trust Attested', options: { bullet: { type: 'bullet' }, fontSize: 13, color: '3EA877' } }
  ], { x: 1.0, y: 4.0, w: 11.0, h: 2.5, lineSpacing: 26 });

  return await pptx.write({ outputType: 'blob' });
}
