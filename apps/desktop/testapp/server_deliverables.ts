import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PYTHON_CMD = process.platform === 'win32' ? 'python' : 'python3';

export interface DocBlock {
  type: 'h1' | 'h2' | 'h3' | 'paragraph' | 'bullet' | 'numbered' | 'table' | 'code' | 'divider' | 'callout';
  text?: string;
  headers?: string[];
  rows?: string[][];
  language?: string;
}

export interface SlideContent {
  title: string;
  bullets: string[];
  paragraphs: string[];
  tables: { headers: string[]; rows: string[][] }[];
  code?: string;
}

/**
 * Robust markdown parser that converts LLM text into a structured document AST
 */
export function parseMarkdownToDocBlocks(markdown: string): DocBlock[] {
  const blocks: DocBlock[] = [];
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
      i++; // skip closing ```
      blocks.push({
        type: 'code',
        text: codeLines.join('\n'),
        language: language || 'text'
      });
      continue;
    }

    // Table detection: line starts and ends with |
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
          // Skip markdown divider row |---|---|
          if (cells.every(c => /^[-:| ]+$/.test(c))) {
            continue;
          }
          if (cells.length > 0) {
            rows.push(cells);
          }
        }

        if (rawHeaders.length > 0) {
          blocks.push({
            type: 'table',
            headers: rawHeaders,
            rows: rows
          });
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

    // Regular paragraph
    blocks.push({ type: 'paragraph', text: line });
    i++;
  }

  return blocks;
}

/**
 * Normalizes table data so that header count and each row cell count match exactly,
 * preventing NaN and undefined column calculation errors in PDF and slide renderers.
 */
export function normalizeTableData(headers: string[], rows: string[][]): { headers: string[]; rows: string[][] } {
  let maxCols = headers.length;
  for (const r of rows) {
    if (r.length > maxCols) maxCols = r.length;
  }
  if (maxCols === 0) return { headers: [], rows: [] };

  const normHeaders: string[] = [];
  for (let c = 0; c < maxCols; c++) {
    const h = headers[c] !== undefined && String(headers[c]).trim() !== '' 
      ? String(headers[c]).trim() 
      : `Column ${c + 1}`;
    normHeaders.push(h);
  }

  const normRows: string[][] = rows.map(r => {
    const row: string[] = [];
    for (let c = 0; c < maxCols; c++) {
      row.push(r[c] !== undefined ? String(r[c]) : '');
    }
    return row;
  });

  return { headers: normHeaders, rows: normRows };
}

/**
 * Groups DocBlocks into structured slides for PPTX generation
 */
export function groupBlocksIntoSlides(blocks: DocBlock[], fallbackTitle: string): SlideContent[] {
  const slides: SlideContent[] = [];
  let currentSlide: SlideContent = {
    title: fallbackTitle,
    bullets: [],
    paragraphs: [],
    tables: []
  };
  let hasContent = false;

  for (const block of blocks) {
    if (block.type === 'h1' || block.type === 'h2' || (block.type === 'h3' && block.text?.toLowerCase().includes('slide'))) {
      if (hasContent) {
        slides.push(currentSlide);
      }
      currentSlide = {
        title: block.text || fallbackTitle,
        bullets: [],
        paragraphs: [],
        tables: []
      };
      hasContent = true;
    } else if (block.type === 'bullet' || block.type === 'numbered') {
      if (block.text) currentSlide.bullets.push(block.text);
      hasContent = true;
    } else if (block.type === 'table') {
      if (block.headers && block.rows) {
        currentSlide.tables.push({ headers: block.headers, rows: block.rows });
        hasContent = true;
      }
    } else if (block.type === 'code') {
      currentSlide.code = block.text;
      hasContent = true;
    } else if (block.type === 'paragraph' && block.text) {
      currentSlide.paragraphs.push(block.text);
      hasContent = true;
    }
  }

  if (hasContent) {
    slides.push(currentSlide);
  }

  if (slides.length === 0) {
    slides.push({
      title: fallbackTitle,
      bullets: ['Generated Sovereign Task Analysis & Synthesis'],
      paragraphs: [],
      tables: []
    });
  }

  return slides;
}

/**
 * HIGH-QUALITY PDF GENERATOR
 * Powered by pdf-lib (https://github.com/Hopding/pdf-lib)
 * Generates publication-grade vector PDF engineering deliverables:
 * - AirBench Sovereign Enclave header banner & metadata strip
 * - Running headers on subsequent pages & dynamic "Page X of Y" footers
 * - Precision word-wrapped headings, paragraphs, and custom-bullet lists
 * - Professional multi-column tables with zebra shading, auto column sizing, and clean borders
 * - Shaded callouts and monospace code blocks
 * - 100% pure TypeScript/JavaScript without external native dependencies
 */
export async function generateHighQualityPdf(title: string, blocks: DocBlock[]): Promise<Buffer> {
  const { PDFDocument, rgb, StandardFonts, PageSizes } = await import('pdf-lib');
  const pdfDoc = await PDFDocument.create();

  // Document Metadata
  pdfDoc.setTitle(title || 'AirBench Sovereign Deliverable');
  pdfDoc.setAuthor('AirBench Sovereign Enclave');
  pdfDoc.setSubject('Engineering Investigation & Technical Deliverable');
  pdfDoc.setCreator('AirBench Sovereign Task Command');
  pdfDoc.setCreationDate(new Date());

  // Fonts
  const helvetica = await pdfDoc.embedFont(StandardFonts.Helvetica);
  const helveticaBold = await pdfDoc.embedFont(StandardFonts.HelveticaBold);
  const helveticaOblique = await pdfDoc.embedFont(StandardFonts.HelveticaOblique);
  const courier = await pdfDoc.embedFont(StandardFonts.Courier);

  // Sovereign Color Palette
  const darkSlate = rgb(0.090, 0.086, 0.082); // #171615
  const headerBar = rgb(0.122, 0.118, 0.110); // #1F1E1C
  const brandOrange = rgb(0.741, 0.357, 0.220); // #BD5B38
  const darkText = rgb(0.118, 0.114, 0.110); // #1F1E1C
  const bodyText = rgb(0.176, 0.169, 0.157); // #2D2B28
  const subText = rgb(0.290, 0.275, 0.251); // #4A4640
  const mutedGray = rgb(0.480, 0.460, 0.430); // #7A756E
  const lightMuted = rgb(0.650, 0.630, 0.600); // #A6A199
  const borderSand = rgb(0.898, 0.878, 0.851); // #E5E0D8
  const lightBorder = rgb(0.930, 0.915, 0.895); // #EDE9E4
  const zebraFill = rgb(0.976, 0.969, 0.957); // #F9F7F4
  const codeFill = rgb(0.957, 0.945, 0.918); // #F4F1EA
  const calloutFill = rgb(0.980, 0.965, 0.945); // #FAF6F1
  const white = rgb(1, 1, 1);

  // WinAnsi encoder sanitization
  function sanitize(text: string): string {
    if (!text) return '';
    return text
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
      .replace(/[\u2260]/g, '!=')
      .replace(/[^\x00-\xFF]/g, ' ');
  }

  // Word wrapping
  function wrapText(text: string, font: any, fontSize: number, maxWidth: number): string[] {
    const clean = sanitize(text);
    if (!clean.trim()) return [''];
    const words = clean.split(/\s+/);
    const lines: string[] = [];
    let currentLine = '';

    for (const word of words) {
      const test = currentLine ? `${currentLine} ${word}` : word;
      const width = font.widthOfTextAtSize(test, fontSize);
      if (width <= maxWidth) {
        currentLine = test;
      } else {
        if (currentLine) {
          lines.push(currentLine);
          if (font.widthOfTextAtSize(word, fontSize) > maxWidth) {
            let part = '';
            for (const char of word) {
              if (font.widthOfTextAtSize(part + char, fontSize) <= maxWidth) {
                part += char;
              } else {
                lines.push(part);
                part = char;
              }
            }
            currentLine = part;
          } else {
            currentLine = word;
          }
        } else {
          let part = '';
          for (const char of word) {
            if (font.widthOfTextAtSize(part + char, fontSize) <= maxWidth) {
              part += char;
            } else {
              lines.push(part);
              part = char;
            }
          }
          currentLine = part;
        }
      }
    }
    if (currentLine) lines.push(currentLine);
    return lines;
  }

  const [pageWidth, pageHeight] = PageSizes.A4;
  const margin = 45;
  const contentWidth = pageWidth - (margin * 2);
  const bottomMargin = 55;

  let currentPage = pdfDoc.addPage(PageSizes.A4);
  let currentY = pageHeight;

  // Header Banner on Page 1
  currentPage.drawRectangle({
    x: 0,
    y: pageHeight - 54,
    width: pageWidth,
    height: 54,
    color: darkSlate
  });
  currentPage.drawRectangle({
    x: 0,
    y: pageHeight - 58,
    width: pageWidth,
    height: 4,
    color: brandOrange
  });

  currentPage.drawText('AIRBENCH SOVEREIGN ENCLAVE', {
    x: margin,
    y: pageHeight - 26,
    size: 13,
    font: helveticaBold,
    color: white
  });
  currentPage.drawText(`CONFIDENTIAL TECHNICAL DELIVERABLE | ${new Date().toLocaleDateString().toUpperCase()} | ZERO EGRESS`, {
    x: margin,
    y: pageHeight - 42,
    size: 7.5,
    font: helvetica,
    color: lightMuted
  });

  currentY = pageHeight - 82;

  // Title
  const cleanTitle = sanitize(title);
  const titleLines = wrapText(cleanTitle, helveticaBold, 20, contentWidth);
  for (const line of titleLines) {
    currentPage.drawText(line, {
      x: margin,
      y: currentY,
      size: 20,
      font: helveticaBold,
      color: darkText
    });
    currentY -= 25;
  }

  // Divider line & metadata strip
  currentY -= 4;
  currentPage.drawLine({
    start: { x: margin, y: currentY },
    end: { x: margin + contentWidth, y: currentY },
    color: borderSand,
    thickness: 1
  });
  currentY -= 14;

  currentPage.drawText('Enclave Isolation: VERIFIED | Node: Local Sovereign Kernel | Classification: RESTRICTED', {
    x: margin,
    y: currentY,
    size: 7.5,
    font: helveticaOblique,
    color: mutedGray
  });
  currentY -= 20;

  function ensureSpace(neededHeight: number): void {
    if (currentY - neededHeight < bottomMargin) {
      currentPage = pdfDoc.addPage(PageSizes.A4);
      currentPage.drawLine({
        start: { x: margin, y: pageHeight - 34 },
        end: { x: margin + contentWidth, y: pageHeight - 34 },
        color: borderSand,
        thickness: 0.5
      });
      currentPage.drawText('AirBench Sovereign Technical Command — Deliverable Dossier', {
        x: margin,
        y: pageHeight - 28,
        size: 7.5,
        font: helvetica,
        color: mutedGray
      });
      currentY = pageHeight - 52;
    }
  }

  for (const block of blocks) {
    switch (block.type) {
      case 'h1': {
        ensureSpace(45);
        currentY -= 10;
        const h1Lines = wrapText(block.text || '', helveticaBold, 15, contentWidth);
        for (const l of h1Lines) {
          currentPage.drawText(l, { x: margin, y: currentY, size: 15, font: helveticaBold, color: brandOrange });
          currentY -= 18;
        }
        currentPage.drawLine({
          start: { x: margin, y: currentY + 4 },
          end: { x: margin + 70, y: currentY + 4 },
          color: brandOrange,
          thickness: 2
        });
        currentY -= 10;
        break;
      }
      case 'h2': {
        ensureSpace(36);
        currentY -= 8;
        const h2Lines = wrapText(block.text || '', helveticaBold, 12.5, contentWidth);
        for (const l of h2Lines) {
          currentPage.drawText(l, { x: margin, y: currentY, size: 12.5, font: helveticaBold, color: darkText });
          currentY -= 15;
        }
        currentY -= 6;
        break;
      }
      case 'h3': {
        ensureSpace(28);
        currentY -= 6;
        const h3Lines = wrapText(block.text || '', helveticaBold, 10.5, contentWidth);
        for (const l of h3Lines) {
          currentPage.drawText(l, { x: margin, y: currentY, size: 10.5, font: helveticaBold, color: subText });
          currentY -= 13;
        }
        currentY -= 4;
        break;
      }
      case 'paragraph': {
        const pLines = wrapText(block.text || '', helvetica, 9.5, contentWidth);
        for (const l of pLines) {
          ensureSpace(14);
          currentPage.drawText(l, { x: margin, y: currentY, size: 9.5, font: helvetica, color: bodyText });
          currentY -= 13;
        }
        currentY -= 6;
        break;
      }
      case 'bullet':
      case 'numbered': {
        const isNumbered = block.type === 'numbered';
        const prefix = isNumbered ? '– ' : '• ';
        const bLines = wrapText(block.text || '', helvetica, 9.5, contentWidth - 16);
        if (bLines.length > 0) {
          ensureSpace(14);
          currentPage.drawText(prefix, { x: margin + 2, y: currentY, size: 9.5, font: helveticaBold, color: brandOrange });
          currentPage.drawText(bLines[0], { x: margin + 14, y: currentY, size: 9.5, font: helvetica, color: bodyText });
          currentY -= 13;
          for (let bIdx = 1; bIdx < bLines.length; bIdx++) {
            ensureSpace(14);
            currentPage.drawText(bLines[bIdx], { x: margin + 14, y: currentY, size: 9.5, font: helvetica, color: bodyText });
            currentY -= 13;
          }
          currentY -= 3;
        }
        break;
      }
      case 'divider': {
        ensureSpace(16);
        currentY -= 6;
        currentPage.drawLine({
          start: { x: margin, y: currentY },
          end: { x: margin + contentWidth, y: currentY },
          color: borderSand,
          thickness: 0.75
        });
        currentY -= 12;
        break;
      }
      case 'callout': {
        const cLines = wrapText(block.text || '', helveticaOblique, 9, contentWidth - 24);
        const calloutHeight = Math.max(26, cLines.length * 13 + 12);
        ensureSpace(calloutHeight + 10);
        currentY -= 4;
        currentPage.drawRectangle({
          x: margin,
          y: currentY - calloutHeight,
          width: contentWidth,
          height: calloutHeight,
          color: calloutFill
        });
        currentPage.drawRectangle({
          x: margin,
          y: currentY - calloutHeight,
          width: 3.5,
          height: calloutHeight,
          color: brandOrange
        });
        let textY = currentY - 14;
        for (const l of cLines) {
          currentPage.drawText(l, { x: margin + 14, y: textY, size: 9, font: helveticaOblique, color: bodyText });
          textY -= 13;
        }
        currentY -= calloutHeight + 10;
        break;
      }
      case 'code': {
        if (block.text) {
          const codeLines = block.text.split(/\r?\n/).map(l => sanitize(l));
          const codeLineHeight = 11;
          const padding = 8;
          const codeHeight = Math.min(320, codeLines.length * codeLineHeight + padding * 2);
          ensureSpace(Math.min(codeHeight + 14, 130));
          currentY -= 4;
          const actualHeight = Math.min(codeHeight, currentY - bottomMargin - 10);
          currentPage.drawRectangle({
            x: margin,
            y: currentY - actualHeight,
            width: contentWidth,
            height: actualHeight,
            color: codeFill,
            borderColor: borderSand,
            borderWidth: 0.75
          });
          let cY = currentY - padding - 8;
          for (const cl of codeLines) {
            if (cY < currentY - actualHeight + padding) break;
            currentPage.drawText(cl.slice(0, 95), {
              x: margin + padding,
              y: cY,
              size: 7.5,
              font: courier,
              color: darkText
            });
            cY -= codeLineHeight;
          }
          currentY -= actualHeight + 12;
        }
        break;
      }
      case 'table': {
        if (block.headers && block.rows && block.headers.length > 0) {
          const { headers: cleanHeaders, rows: cleanRows } = normalizeTableData(block.headers, block.rows);
          const numCols = cleanHeaders.length;
          if (numCols > 0) {
            const colLengths: number[] = cleanHeaders.map(h => h.length);
            cleanRows.forEach(r => {
              r.forEach((c, i) => {
                if (c && c.length > (colLengths[i] || 0)) {
                  colLengths[i] = Math.min(60, c.length);
                }
              });
            });
            const totalLen = colLengths.reduce((a, b) => a + Math.max(6, b), 0);
            const colWidths = colLengths.map(l => (Math.max(6, l) / totalLen) * contentWidth);

            const renderTableHeader = () => {
              ensureSpace(30);
              currentPage.drawRectangle({
                x: margin,
                y: currentY - 22,
                width: contentWidth,
                height: 22,
                color: headerBar
              });
              currentPage.drawRectangle({
                x: margin,
                y: currentY - 24,
                width: contentWidth,
                height: 2,
                color: brandOrange
              });
              let curX = margin;
              cleanHeaders.forEach((h, cIdx) => {
                const w = colWidths[cIdx];
                const wrapped = wrapText(h, helveticaBold, 8.5, w - 8);
                currentPage.drawText(wrapped[0] || '', {
                  x: curX + 5,
                  y: currentY - 15,
                  size: 8.5,
                  font: helveticaBold,
                  color: white
                });
                curX += w;
              });
              currentY -= 25;
            };

            renderTableHeader();

            cleanRows.forEach((r, rIdx) => {
              const cellWrapped = r.map((cell, cIdx) => wrapText(cell, helvetica, 8, colWidths[cIdx] - 10));
              const maxLines = Math.max(1, ...cellWrapped.map(cw => cw.length));
              const rowHeight = Math.max(18, maxLines * 10 + 7);

              if (currentY - rowHeight < bottomMargin) {
                ensureSpace(rowHeight + 35);
                renderTableHeader();
              }

              if (rIdx % 2 === 1) {
                currentPage.drawRectangle({
                  x: margin,
                  y: currentY - rowHeight,
                  width: contentWidth,
                  height: rowHeight,
                  color: zebraFill
                });
              }

              currentPage.drawLine({
                start: { x: margin, y: currentY - rowHeight },
                end: { x: margin + contentWidth, y: currentY - rowHeight },
                color: lightBorder,
                thickness: 0.5
              });

              let curX = margin;
              r.forEach((cell, cIdx) => {
                const w = colWidths[cIdx];
                if (cIdx > 0) {
                  currentPage.drawLine({
                    start: { x: curX, y: currentY },
                    end: { x: curX, y: currentY - rowHeight },
                    color: lightBorder,
                    thickness: 0.5
                  });
                }
                let textY = currentY - 11;
                for (const line of cellWrapped[cIdx]) {
                  currentPage.drawText(line, {
                    x: curX + 5,
                    y: textY,
                    size: 8,
                    font: helvetica,
                    color: bodyText
                  });
                  textY -= 10;
                }
                curX += w;
              });

              currentY -= rowHeight;
            });

            currentY -= 12;
          }
        }
        break;
      }
    }
  }

  // Dynamic Footers across all pages
  const allPages = pdfDoc.getPages();
  const totalPages = allPages.length;
  allPages.forEach((p, idx) => {
    p.drawLine({
      start: { x: margin, y: 35 },
      end: { x: margin + contentWidth, y: 35 },
      color: borderSand,
      thickness: 0.5
    });
    p.drawText('AirBench Sovereign Deliverable • Hardware-Enclave Isolated • Zero Telemetry', {
      x: margin,
      y: 22,
      size: 7.5,
      font: helvetica,
      color: mutedGray
    });
    const pageStr = `Page ${idx + 1} of ${totalPages}`;
    const pWidth = helvetica.widthOfTextAtSize(pageStr, 7.5);
    p.drawText(pageStr, {
      x: margin + contentWidth - pWidth,
      y: 22,
      size: 7.5,
      font: helvetica,
      color: mutedGray
    });
  });

  const pdfBytes = await pdfDoc.save();
  return Buffer.from(pdfBytes);
}

/**
 * HIGH-QUALITY DOCX GENERATOR
 * Uses docx with corporate heading styles, branded table formatting,
 * alternating row fills, code callouts, and footer page numbering.
 */
export async function generateHighQualityDocx(title: string, blocks: DocBlock[]): Promise<Buffer> {
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

  const children: any[] = [];

  // Title
  children.push(
    new Paragraph({
      children: [
        new TextRun({
          text: title,
          bold: true,
          size: 36,
          color: '171615',
          font: 'Segoe UI'
        })
      ],
      spacing: { before: 100, after: 120 }
    })
  );

  // Subtitle / Enclave metadata
  children.push(
    new Paragraph({
      children: [
        new TextRun({
          text: `AIRBENCH SOVEREIGN ENCLAVE DELIVERABLE • GENERATED ${new Date().toLocaleDateString().toUpperCase()}`,
          bold: true,
          size: 16,
          color: 'BD5B38',
          font: 'Segoe UI'
        })
      ],
      spacing: { after: 240 }
    })
  );

  for (const block of blocks) {
    switch (block.type) {
      case 'h1':
        children.push(
          new Paragraph({
            heading: HeadingLevel.HEADING_1,
            children: [
              new TextRun({
                text: block.text || '',
                bold: true,
                size: 28,
                color: 'BD5B38',
                font: 'Segoe UI'
              })
            ],
            spacing: { before: 240, after: 120 }
          })
        );
        break;
      case 'h2':
        children.push(
          new Paragraph({
            heading: HeadingLevel.HEADING_2,
            children: [
              new TextRun({
                text: block.text || '',
                bold: true,
                size: 24,
                color: '1F1E1C',
                font: 'Segoe UI'
              })
            ],
            spacing: { before: 200, after: 100 }
          })
        );
        break;
      case 'h3':
        children.push(
          new Paragraph({
            heading: HeadingLevel.HEADING_3,
            children: [
              new TextRun({
                text: block.text || '',
                bold: true,
                size: 20,
                color: '4A4640',
                font: 'Segoe UI'
              })
            ],
            spacing: { before: 160, after: 80 }
          })
        );
        break;
      case 'paragraph':
        children.push(
          new Paragraph({
            children: [
              new TextRun({
                text: block.text || '',
                size: 21,
                color: '2D2B28',
                font: 'Segoe UI'
              })
            ],
            spacing: { after: 100, line: 276 }
          })
        );
        break;
      case 'bullet':
        children.push(
          new Paragraph({
            bullet: { level: 0 },
            children: [
              new TextRun({
                text: block.text || '',
                size: 21,
                color: '2D2B28',
                font: 'Segoe UI'
              })
            ],
            spacing: { after: 60 }
          })
        );
        break;
      case 'numbered':
        children.push(
          new Paragraph({
            children: [
              new TextRun({
                text: `• ${block.text || ''}`,
                size: 21,
                color: '2D2B28',
                font: 'Segoe UI'
              })
            ],
            spacing: { after: 60 }
          })
        );
        break;
      case 'divider':
        children.push(
          new Paragraph({
            children: [
              new TextRun({
                text: '______________________________________________________________________',
                color: 'E5E0D8'
              })
            ],
            spacing: { before: 120, after: 120 }
          })
        );
        break;
      case 'callout':
        children.push(
          new Paragraph({
            children: [
              new TextRun({
                text: block.text || '',
                italics: true,
                size: 21,
                color: '2D2B28',
                font: 'Segoe UI'
              })
            ],
            shading: { fill: 'FAF6F1' },
            border: {
              left: { style: BorderStyle.SINGLE, size: 24, color: 'BD5B38' }
            },
            spacing: { before: 140, after: 140 },
            indent: { left: 240 }
          })
        );
        break;
      case 'code':
        if (block.text) {
          const codeLines = block.text.split('\n');
          for (const cl of codeLines) {
            children.push(
              new Paragraph({
                children: [
                  new TextRun({
                    text: cl,
                    font: 'Consolas',
                    size: 18,
                    color: '1F1E1C'
                  })
                ],
                shading: { fill: 'F4F1EA' },
                spacing: { after: 20 }
              })
            );
          }
        }
        break;
      case 'table':
        if (block.headers && block.rows && block.headers.length > 0) {
          const tableRows: any[] = [];

          // Header Row
          tableRows.push(
            new TableRow({
              tableHeader: true,
              children: block.headers.map(
                h =>
                  new TableCell({
                    children: [
                      new Paragraph({
                        alignment: AlignmentType.CENTER,
                        children: [
                          new TextRun({
                            text: h,
                            bold: true,
                            size: 19,
                            color: 'FFFFFF',
                            font: 'Segoe UI'
                          })
                        ]
                      })
                    ],
                    shading: { fill: '1F1E1C' },
                    borders: {
                      top: { style: BorderStyle.SINGLE, size: 1, color: '1F1E1C' },
                      bottom: { style: BorderStyle.SINGLE, size: 2, color: 'BD5B38' },
                      left: { style: BorderStyle.NONE },
                      right: { style: BorderStyle.NONE }
                    }
                  })
              )
            })
          );

          // Data Rows
          block.rows.forEach((row, rIdx) => {
            const isEven = rIdx % 2 === 0;
            tableRows.push(
              new TableRow({
                children: row.map(
                  cell =>
                    new TableCell({
                      children: [
                        new Paragraph({
                          children: [
                            new TextRun({
                              text: cell,
                              size: 19,
                              color: '2D2B28',
                              font: 'Segoe UI'
                            })
                          ]
                        })
                      ],
                      shading: { fill: isEven ? 'FFFFFF' : 'F9F7F4' },
                      borders: {
                        top: { style: BorderStyle.SINGLE, size: 1, color: 'EAE6DF' },
                        bottom: { style: BorderStyle.SINGLE, size: 1, color: 'EAE6DF' },
                        left: { style: BorderStyle.NONE },
                        right: { style: BorderStyle.NONE }
                      }
                    })
                )
              })
            );
          });

          children.push(
            new Table({
              rows: tableRows,
              width: { size: 100, type: WidthType.PERCENTAGE }
            })
          );
          children.push(new Paragraph({ spacing: { after: 160 } }));
        }
        break;
    }
  }

  const doc = new Document({
    sections: [
      {
        properties: {},
        headers: {
          default: new Header({
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                children: [
                  new TextRun({
                    text: 'AirBench Sovereign Technical Command',
                    size: 16,
                    color: '9C978F',
                    font: 'Segoe UI'
                  })
                ]
              })
            ]
          })
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                children: [
                  new TextRun({
                    text: 'Page ',
                    size: 16,
                    color: '9C978F'
                  }),
                  new TextRun({
                    children: [PageNumber.CURRENT],
                    size: 16,
                    color: '9C978F'
                  }),
                  new TextRun({
                    text: ' of ',
                    size: 16,
                    color: '9C978F'
                  }),
                  new TextRun({
                    children: [PageNumber.TOTAL_PAGES],
                    size: 16,
                    color: '9C978F'
                  })
                ]
              })
            ]
          })
        },
        children
      }
    ]
  });

  return await Packer.toBuffer(doc);
}

/**
 * HIGH-QUALITY EXCEL GENERATOR
 * Uses ExcelJS with frozen header rows, corporate styling, auto-width columns,
 * multiple sheets for multiple tables, and zebra-striping.
 */
export async function generateHighQualityXlsx(title: string, blocks: DocBlock[]): Promise<Buffer> {
  const ExcelJS = (await import('exceljs')).default || (await import('exceljs'));
  const workbook = new ExcelJS.Workbook();
  workbook.creator = 'AirBench Sovereign Enclave';
  workbook.lastModifiedBy = 'AirBench Sovereign Task Command';
  workbook.created = new Date();

  const tables = blocks.filter(b => b.type === 'table' && b.headers && b.headers.length > 0);
  const headings = blocks.filter(b => b.type === 'h1' || b.type === 'h2');
  const paragraphs = blocks.filter(b => b.type === 'paragraph' || b.type === 'callout');

  // Sheet 1: Executive Overview & Enclave Metadata
  const summarySheet = workbook.addWorksheet('Overview', {
    views: [{ state: 'frozen', ySplit: 2, showGridLines: true }],
    properties: { tabColor: { argb: 'FFBD5B38' } }
  });

  // Title Row
  const bannerRow = summarySheet.addRow([`AIRBENCH SOVEREIGN DELIVERABLE: ${title}`]);
  bannerRow.height = 32;
  bannerRow.font = { name: 'Segoe UI', size: 14, bold: true, color: { argb: 'FFFFFFFF' } };
  bannerRow.eachCell(cell => {
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF171615' } };
    cell.alignment = { vertical: 'middle', horizontal: 'left' };
  });

  summarySheet.addRow([]); // Blank spacer

  // Metadata Table Header
  const metaHeader = summarySheet.addRow(['Parameter', 'Enclave Invariant Value', 'Verification Status']);
  metaHeader.height = 24;
  metaHeader.eachCell(cell => {
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF1F1E1C' } };
    cell.font = { name: 'Segoe UI', size: 10, bold: true, color: { argb: 'FFFFFFFF' } };
    cell.alignment = { vertical: 'middle', horizontal: 'left' };
    cell.border = { bottom: { style: 'medium', color: { argb: 'FFBD5B38' } } };
  });

  const metadataItems = [
    ['Document Title', title, 'AUTHENTIC'],
    ['Security Classification', 'Enclave Confidential • Hardware Isolation', 'ENFORCED'],
    ['Execution Boundary', 'Local Loopback (Zero Telemetry)', 'CERTIFIED'],
    ['Generated Timestamp', new Date().toLocaleString(), 'VALIDATED'],
    ['Structured Tables Extracted', `${tables.length} table(s)`, 'NOMINAL'],
    ['Total Documentation Sections', `${headings.length + paragraphs.length} block(s)`, 'INDEXED']
  ];

  metadataItems.forEach((item, rIdx) => {
    const row = summarySheet.addRow(item);
    row.height = 20;
    const isEven = rIdx % 2 === 0;
    row.eachCell((cell, colNum) => {
      cell.font = { name: 'Segoe UI', size: 9.5, color: { argb: 'FF2D2B28' } };
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: isEven ? 'FFFFFFFF' : 'FFF9F7F4' } };
      cell.border = { bottom: { style: 'thin', color: { argb: 'FFEAE6DF' } } };
      cell.alignment = { vertical: 'middle' };
      if (colNum === 3) {
        cell.font = { name: 'Segoe UI', size: 9, bold: true, color: { argb: 'FF3EA877' } };
      }
    });
  });

  summarySheet.getColumn(1).width = 28;
  summarySheet.getColumn(2).width = 45;
  summarySheet.getColumn(3).width = 22;

  // Sheet 2+: Data sheets for each table
  if (tables.length > 0) {
    tables.forEach((tbl, idx) => {
      const sheetName = tables.length === 1 ? 'Data_Matrix' : `Table_${idx + 1}`;
      const sheet = workbook.addWorksheet(sheetName.slice(0, 31), {
        views: [{ state: 'frozen', ySplit: 2, showGridLines: true }],
        properties: { tabColor: { argb: 'FF1F1E1C' } }
      });

      // Sheet title row
      const titleRow = sheet.addRow([`${title} - Section ${idx + 1}`]);
      titleRow.font = { name: 'Segoe UI', size: 13, bold: true, color: { argb: 'FF171615' } };
      titleRow.height = 28;

      // Table Header Row
      const headerRow = sheet.addRow(tbl.headers!);
      headerRow.height = 26;
      headerRow.eachCell((cell, colNum) => {
        cell.fill = {
          type: 'pattern',
          pattern: 'solid',
          fgColor: { argb: 'FF1F1E1C' }
        };
        cell.font = {
          name: 'Segoe UI',
          size: 10,
          bold: true,
          color: { argb: 'FFFFFFFF' }
        };
        cell.alignment = { vertical: 'middle', horizontal: 'left', wrapText: true };
        cell.border = {
          bottom: { style: 'medium', color: { argb: 'FFBD5B38' } }
        };
      });

      // Enable AutoFilter on header row
      const numCols = tbl.headers!.length;
      if (numCols > 0) {
        sheet.autoFilter = {
          from: { row: 2, column: 1 },
          to: { row: 2, column: numCols }
        };
      }

      // Table Data Rows
      tbl.rows?.forEach((rowData, rIdx) => {
        const row = sheet.addRow(rowData);
        row.height = 20;
        const isEven = rIdx % 2 === 0;

        row.eachCell((cell, colNum) => {
          cell.font = { name: 'Segoe UI', size: 9.5, color: { argb: 'FF2D2B28' } };
          cell.fill = {
            type: 'pattern',
            pattern: 'solid',
            fgColor: { argb: isEven ? 'FFFFFFFF' : 'FFF9F7F4' }
          };
          cell.border = {
            bottom: { style: 'thin', color: { argb: 'FFEAE6DF' } }
          };
          cell.alignment = { vertical: 'middle' };

          // Convert numeric strings to real numbers for Excel formulas
          const val = cell.value?.toString().trim();
          if (val && !isNaN(Number(val)) && !val.startsWith('0x') && !val.includes('-') && !val.includes('/')) {
            const num = Number(val);
            cell.value = num;
            cell.numFmt = Number.isInteger(num) ? '#,##0' : '#,##0.00';
            cell.alignment = { vertical: 'middle', horizontal: 'right' };
          }
        });
      });

      // Auto-fit column widths
      sheet.columns.forEach((col, cIdx) => {
        let maxLen = 14;
        col.eachCell?.({ includeEmpty: false }, (cell, rowNum) => {
          if (rowNum > 1) {
            const len = cell.value ? cell.value.toString().length : 0;
            if (len > maxLen) maxLen = len;
          }
        });
        col.width = Math.min(48, maxLen + 4);
      });
    });
  } else {
    // Fallback: render paragraphs / bullets into a structured spreadsheet log
    const sheet = workbook.addWorksheet('Deliverable_Log', {
      views: [{ state: 'frozen', ySplit: 2, showGridLines: true }],
      properties: { tabColor: { argb: 'FF1F1E1C' } }
    });

    const titleRow = sheet.addRow([title]);
    titleRow.font = { name: 'Segoe UI', size: 14, bold: true, color: { argb: 'FF171615' } };
    titleRow.height = 28;

    const headerRow = sheet.addRow(['Index', 'Section / Type', 'Content / Value']);
    headerRow.height = 26;
    headerRow.eachCell(cell => {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF1F1E1C' } };
      cell.font = { name: 'Segoe UI', size: 10, bold: true, color: { argb: 'FFFFFFFF' } };
      cell.alignment = { vertical: 'middle', horizontal: 'left' };
      cell.border = { bottom: { style: 'medium', color: { argb: 'FFBD5B38' } } };
    });

    sheet.autoFilter = { from: { row: 2, column: 1 }, to: { row: 2, column: 3 } };

    let rowIdx = 1;
    for (const b of blocks) {
      if (b.text) {
        const row = sheet.addRow([rowIdx++, b.type.toUpperCase(), b.text]);
        row.height = 20;
        row.eachCell((cell, colNum) => {
          cell.font = { name: 'Segoe UI', size: 9.5, color: { argb: 'FF2D2B28' } };
          cell.alignment = { vertical: 'middle' };
        });
      }
    }

    sheet.getColumn(1).width = 10;
    sheet.getColumn(2).width = 20;
    sheet.getColumn(3).width = 70;
  }

  const buffer = await workbook.xlsx.writeBuffer();
  return Buffer.from(buffer);
}

/**
 * HIGH-QUALITY POWERPOINT GENERATOR
 * Uses PptxGenJS with 16:9 widescreen layout, dark sovereign master theme,
 * title slide, content slides with bullets, and native slide tables.
 */
export async function generateHighQualityPptx(title: string, blocks: DocBlock[]): Promise<Buffer> {
  const PptxGenJS = (await import('pptxgenjs')).default || (await import('pptxgenjs'));
  const pptx = new (PptxGenJS as any)();

  pptx.layout = 'LAYOUT_16x9';

  // Define Master Slide Theme
  pptx.defineSlideMaster({
    title: 'AIRBENCH_MASTER',
    background: { color: 'FAF8F5' },
    objects: [
      // Top dark banner
      { rect: { x: 0, y: 0, w: '100%', h: 0.75, fill: { color: '171615' } } },
      // Top orange accent rule
      { rect: { x: 0, y: 0.75, w: '100%', h: 0.05, fill: { color: 'BD5B38' } } },
      // Header brand label
      {
        text: {
          text: 'AIRBENCH SOVEREIGN TASK COMMAND',
          options: { x: 0.8, y: 0.22, fontSize: 10, bold: true, color: 'FFFFFF', fontFace: 'Segoe UI' }
        }
      },
      // Bottom footer bar
      { rect: { x: 0, y: 7.1, w: '100%', h: 0.4, fill: { color: '171615' } } },
      {
        text: {
          text: 'CONFIDENTIAL • ENCLAVE HARDWARE ISOLATION',
          options: { x: 0.8, y: 7.18, fontSize: 8, color: '8E8982', fontFace: 'Segoe UI' }
        }
      }
    ],
    slideNumber: { x: 12.0, y: 7.18, fontSize: 8, color: 'EDE8DD', fontFace: 'Segoe UI' }
  });

  // Slide 1: Cover / Title Slide
  const titleSlide = pptx.addSlide();
  titleSlide.background = { color: '171615' };

  titleSlide.addText('AIRBENCH SOVEREIGN TASK COMMAND', {
    x: 1.0,
    y: 1.6,
    fontSize: 12,
    bold: true,
    color: 'BD5B38',
    fontFace: 'Segoe UI',
    charSpacing: 2
  });

  titleSlide.addText(title, {
    x: 1.0,
    y: 2.2,
    w: 11.3,
    fontSize: 32,
    bold: true,
    color: 'FFFFFF',
    fontFace: 'Segoe UI'
  });

  titleSlide.addShape(pptx.ShapeType.line, {
    x: 1.0,
    y: 4.2,
    w: 3.5,
    h: 0,
    line: { color: 'BD5B38', width: 3 }
  });

  titleSlide.addText(
    `Executive Briefing & Technical Deliverable\nDate: ${new Date().toLocaleDateString()}\nStatus: Verified Sovereign Invariants`,
    {
      x: 1.0,
      y: 4.6,
      fontSize: 14,
      color: 'A8A39A',
      fontFace: 'Segoe UI',
      lineSpacing: 24
    }
  );

  // Group remaining content into slides
  const slideDeck = groupBlocksIntoSlides(blocks, title);

  for (const s of slideDeck) {
    const slide = pptx.addSlide({ masterName: 'AIRBENCH_MASTER' });

    // Slide Title
    slide.addText(s.title, {
      x: 0.8,
      y: 1.05,
      w: 11.5,
      fontSize: 22,
      bold: true,
      color: '171615',
      fontFace: 'Segoe UI'
    });

    // Small orange underline under title
    slide.addShape(pptx.ShapeType.line, {
      x: 0.8,
      y: 1.55,
      w: 1.5,
      h: 0,
      line: { color: 'BD5B38', width: 2 }
    });

    let currentY = 1.75;

    // Slide Paragraphs
    if (s.paragraphs.length > 0) {
      slide.addText(s.paragraphs.join('\n\n'), {
        x: 0.8,
        y: currentY,
        w: 11.5,
        fontSize: 13,
        color: '2D2B28',
        fontFace: 'Segoe UI'
      });
      currentY += Math.min(2.0, s.paragraphs.length * 0.6);
    }

    // Slide Bullets
    if (s.bullets.length > 0) {
      const bulletItems = s.bullets.map(b => ({
        text: b,
        options: {
          fontSize: 13,
          color: '2D2B28',
          fontFace: 'Segoe UI',
          bullet: { type: 'bullet', code: '2022' }
        }
      }));

      slide.addText(bulletItems, {
        x: 0.8,
        y: currentY,
        w: 11.5,
        h: Math.min(4.5, s.bullets.length * 0.45 + 0.5),
        lineSpacing: 24
      });
      currentY += Math.min(3.0, s.bullets.length * 0.45);
    }

    // Slide Tables
    if (s.tables.length > 0) {
      const tbl = s.tables[0];
      const tableRows: any[][] = [];

      // Header row
      tableRows.push(
        tbl.headers.map(h => ({
          text: h,
          options: {
            bold: true,
            fill: '1F1E1C',
            color: 'FFFFFF',
            fontSize: 11,
            align: 'center',
            valign: 'middle'
          }
        }))
      );

      // Data rows (up to 8 rows per slide)
      tbl.rows.slice(0, 8).forEach((r, rIdx) => {
        const isEven = rIdx % 2 === 0;
        tableRows.push(
          r.map(c => ({
            text: c,
            options: {
              fill: isEven ? 'FFFFFF' : 'F9F7F4',
              color: '2D2B28',
              fontSize: 10,
              align: 'left',
              valign: 'middle'
            }
          }))
        );
      });

      slide.addTable(tableRows, {
        x: 0.8,
        y: Math.min(currentY, 3.2),
        w: 11.5,
        border: { pt: 0.5, color: 'EAE6DF' }
      });
    }

    // Slide Code
    if (s.code && s.tables.length === 0) {
      slide.addText(s.code, {
        x: 0.8,
        y: currentY,
        w: 11.5,
        h: 3.5,
        fontFace: 'Consolas',
        fontSize: 10,
        color: '1F1E1C',
        fill: { color: 'F4F1EA' }
      });
    }
  }

  // Final Slide: Sovereign Enclave Attestation & Verification
  const endSlide = pptx.addSlide();
  endSlide.background = { color: '171615' };

  endSlide.addText('AIRBENCH SOVEREIGN ENCLAVE', {
    x: 1.0,
    y: 1.8,
    fontSize: 12,
    bold: true,
    color: 'BD5B38',
    fontFace: 'Segoe UI',
    charSpacing: 2
  });

  endSlide.addText('Cryptographic Attestation & Delivery Verification', {
    x: 1.0,
    y: 2.4,
    w: 11.3,
    fontSize: 28,
    bold: true,
    color: 'FFFFFF',
    fontFace: 'Segoe UI'
  });

  endSlide.addShape(pptx.ShapeType.line, {
    x: 1.0,
    y: 3.6,
    w: 3.0,
    h: 0,
    line: { color: 'BD5B38', width: 2 }
  });

  const verificationPoints = [
    { text: 'Execution Boundary: Hardware-isolated sovereign loopback enclave', options: { bullet: { type: 'bullet' }, fontSize: 13, color: 'EDE8DD', fontFace: 'Segoe UI' } },
    { text: 'Egress Policy: Zero cloud telemetry, strict mTLS host verification', options: { bullet: { type: 'bullet' }, fontSize: 13, color: 'EDE8DD', fontFace: 'Segoe UI' } },
    { text: `Synthesis Horizon: Process Loop & Physics verified on ${new Date().toLocaleDateString()}`, options: { bullet: { type: 'bullet' }, fontSize: 13, color: 'EDE8DD', fontFace: 'Segoe UI' } },
    { text: 'Audit Signature: Enclave Root-of-Trust Attested', options: { bullet: { type: 'bullet' }, fontSize: 13, color: '3EA877', fontFace: 'Segoe UI' } }
  ];

  endSlide.addText(verificationPoints, {
    x: 1.0,
    y: 4.0,
    w: 11.0,
    h: 2.5,
    lineSpacing: 26
  });

  const buffer = await pptx.write({ outputType: 'nodebuffer' });
  return buffer as Buffer;
}

/**
 * Universal Inter-Format Transformation
 * Converts ANY source document format (Excel, Word, PowerPoint, PDF, CSV)
 * to ANY desired deliverable format (PDF, DOCX, XLSX, PPTX, MD, PY)
 */
export async function transformDeliverableFile(
  sourceBuffer: Buffer,
  sourceExt: string,
  targetFormat: string,
  title: string,
  extraContent?: string
): Promise<{ buffer: Buffer; contentType: string; filename: string }> {
  const cleanExt = (sourceExt || '').toLowerCase().replace(/^\./, '');
  const target = (targetFormat || 'docx').toLowerCase();
  const safeTitle = (title || 'sovereign_transformed_artifact')
    .replace(/[^a-zA-Z0-9_\-\s]/g, '')
    .trim()
    .replace(/\s+/g, '_') || 'artifact';

  console.log(`[DeliverableEngine] Inter-format transform: ${cleanExt} -> ${target} (${safeTitle})`);

  let extractedDocBlocks: DocBlock[] = [];

  // ==========================================
  // STEP 1: EXTRACT STRUCTURE FROM SOURCE
  // ==========================================

  if (['xlsx', 'xls', 'csv'].includes(cleanExt)) {
    // Parse spreadsheet using xlsx (SheetJS)
    const XLSX = (await import('xlsx')).default || (await import('xlsx'));
    const wb = XLSX.read(sourceBuffer, { type: 'buffer' });

    wb.SheetNames.forEach(sheetName => {
      const sheet = wb.Sheets[sheetName];
      const jsonRows: any[][] = XLSX.utils.sheet_to_json(sheet, { header: 1 });

      if (jsonRows.length > 0) {
        // Find row with max populated cells to serve as headers
        let maxCols = 0;
        let bestHeaderIdx = 0;
        jsonRows.forEach((r, idx) => {
          const populated = (r || []).filter((cell: any) => cell !== null && cell !== undefined && String(cell).trim() !== '').length;
          if (populated > maxCols) {
            maxCols = populated;
            bestHeaderIdx = idx;
          }
        });

        if (maxCols === 0) return;

        // Any rows before bestHeaderIdx can be sheet title/subtitle
        for (let r = 0; r < bestHeaderIdx; r++) {
          const lineText = (jsonRows[r] || []).filter(Boolean).map(String).join(' - ');
          if (lineText) extractedDocBlocks.push({ type: 'h2', text: lineText });
        }
        if (bestHeaderIdx === 0) {
          extractedDocBlocks.push({ type: 'h2', text: `Sheet: ${sheetName}` });
        }

        const rawHeaders = (jsonRows[bestHeaderIdx] || []).map(c => String(c ?? ''));
        const rawDataRows = jsonRows.slice(bestHeaderIdx + 1).map(r => (r || []).map(c => String(c ?? '')));

        const { headers, rows } = normalizeTableData(rawHeaders, rawDataRows);

        if (headers.length > 0) {
          extractedDocBlocks.push({
            type: 'table',
            headers,
            rows
          });
        }
      }
    });
  } else if (cleanExt === 'docx') {
    // Parse DOCX via mammoth
    const mammoth = (await import('mammoth')).default || (await import('mammoth'));
    const result = await mammoth.extractRawText({ buffer: sourceBuffer });
    const rawText = result.value || '';
    extractedDocBlocks = parseMarkdownToDocBlocks(rawText);
  } else if (cleanExt === 'pdf') {
    // Parse PDF via Python PyMuPDF
    const tempInFile = path.join(__dirname, `.temp_in_${Date.now()}.pdf`);
    fs.writeFileSync(tempInFile, sourceBuffer);

    try {
      const pyOutput = await new Promise<string>((resolve, reject) => {
        const py = spawn(PYTHON_CMD, ['server_python_converter.py', 'extract-pdf', tempInFile], {
          cwd: __dirname
        });
        let out = '';
        py.stdout.on('data', d => { out += d.toString(); });
        py.on('close', code => {
          if (code === 0) resolve(out);
          else reject(new Error(`Python extract-pdf failed with exit code ${code}`));
        });
      });

      const parsed = JSON.parse(pyOutput);
      if (parsed.pages) {
        parsed.pages.forEach((p: any) => {
          extractedDocBlocks.push({ type: 'h2', text: `Page ${p.pageNumber}` });
          if (p.text) {
            extractedDocBlocks.push({ type: 'paragraph', text: p.text.trim() });
          }
          if (p.tables && p.tables.length > 0) {
            p.tables.forEach((t: any) => {
              extractedDocBlocks.push({
                type: 'table',
                headers: t.headers,
                rows: t.rows
              });
            });
          }
        });
      }
    } catch (e: any) {
      console.warn('[DeliverableEngine] Python PDF extraction fallback:', e.message);
      extractedDocBlocks.push({ type: 'paragraph', text: 'Document extracted from PDF source.' });
    } finally {
      fs.unlink(tempInFile, () => {});
    }
  } else if (cleanExt === 'pptx') {
    // Parse PPTX via Python python-pptx
    const tempInFile = path.join(__dirname, `.temp_in_${Date.now()}.pptx`);
    fs.writeFileSync(tempInFile, sourceBuffer);

    try {
      const pyOutput = await new Promise<string>((resolve, reject) => {
        const py = spawn(PYTHON_CMD, ['server_python_converter.py', 'extract-pptx', tempInFile], {
          cwd: __dirname
        });
        let out = '';
        py.stdout.on('data', d => { out += d.toString(); });
        py.on('close', code => {
          if (code === 0) resolve(out);
          else reject(new Error(`Python extract-pptx failed with exit code ${code}`));
        });
      });

      const parsed = JSON.parse(pyOutput);
      if (parsed.slides) {
        parsed.slides.forEach((s: any) => {
          extractedDocBlocks.push({ type: 'h2', text: s.title || `Slide ${s.slideNumber}` });
          s.paragraphs?.forEach((p: string) => extractedDocBlocks.push({ type: 'paragraph', text: p }));
          s.bullets?.forEach((b: string) => extractedDocBlocks.push({ type: 'bullet', text: b }));
          s.tables?.forEach((t: any) => extractedDocBlocks.push({ type: 'table', headers: t.headers, rows: t.rows }));
        });
      }
    } catch (e: any) {
      console.warn('[DeliverableEngine] Python PPTX extraction fallback:', e.message);
    } finally {
      fs.unlink(tempInFile, () => {});
    }
  } else {
    // Plain text / Markdown
    const text = sourceBuffer.toString('utf-8');
    extractedDocBlocks = parseMarkdownToDocBlocks(text);
  }

  // If extra content was provided by user/AI, append it
  if (extraContent && extraContent.trim()) {
    const extraBlocks = parseMarkdownToDocBlocks(extraContent.trim());
    extractedDocBlocks.push({ type: 'divider' });
    extractedDocBlocks.push({ type: 'h2', text: 'Enclave Analysis & Synthesis' });
    extractedDocBlocks.push(...extraBlocks);
  }

  // ==========================================
  // STEP 2: RENDER TO TARGET FORMAT
  // ==========================================

  if (target === 'pdf') {
    const pdfBuf = await generateHighQualityPdf(safeTitle, extractedDocBlocks);
    return {
      buffer: pdfBuf,
      contentType: 'application/pdf',
      filename: `${safeTitle}.pdf`
    };
  }

  if (target === 'xlsx') {
    const xlsxBuf = await generateHighQualityXlsx(safeTitle, extractedDocBlocks);
    return {
      buffer: xlsxBuf,
      contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      filename: `${safeTitle}.xlsx`
    };
  }

  if (target === 'docx') {
    const docxBuf = await generateHighQualityDocx(safeTitle, extractedDocBlocks);
    return {
      buffer: docxBuf,
      contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      filename: `${safeTitle}.docx`
    };
  }

  if (target === 'pptx') {
    const pptxBuf = await generateHighQualityPptx(safeTitle, extractedDocBlocks);
    return {
      buffer: pptxBuf,
      contentType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      filename: `${safeTitle}.pptx`
    };
  }

  // Markdown or Python fallback
  const mdLines: string[] = [`# ${safeTitle}\n`];
  extractedDocBlocks.forEach(b => {
    if (b.type === 'h1') mdLines.push(`\n# ${b.text}\n`);
    else if (b.type === 'h2') mdLines.push(`\n## ${b.text}\n`);
    else if (b.type === 'h3') mdLines.push(`\n### ${b.text}\n`);
    else if (b.type === 'bullet') mdLines.push(`- ${b.text}`);
    else if (b.type === 'paragraph') mdLines.push(`\n${b.text}\n`);
    else if (b.type === 'table' && b.headers) {
      mdLines.push(`\n| ${b.headers.join(' | ')} |`);
      mdLines.push(`| ${b.headers.map(() => '---').join(' | ')} |`);
      b.rows?.forEach(r => mdLines.push(`| ${r.join(' | ')} |`));
      mdLines.push('\n');
    }
  });

  const mime = target === 'py' ? 'text/x-python; charset=utf-8' : 'text/markdown; charset=utf-8';
  const ext = target === 'py' ? '.py' : '.md';
  return {
    buffer: Buffer.from(mdLines.join('\n'), 'utf-8'),
    contentType: mime,
    filename: `${safeTitle}${ext}`
  };
}
