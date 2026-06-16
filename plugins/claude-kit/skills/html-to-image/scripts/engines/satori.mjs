// satori 엔진: 브라우저 없이 flexbox-only HTML → PNG.
// HTML 문자열 → satori-html(element 변환) → satori(SVG) → @resvg/resvg-js(scale 래스터화) → PNG.
// CSS 제약(flexbox-only, grid/float/z-index/calc/RTL/<link> 웹폰트 불가)은 satori 한계 그대로.
// capture.mjs가 --engine satori일 때만 동적 import하므로 Playwright-only 사용자엔 영향 0.

import satori from 'satori';
import { html } from 'satori-html';
import { Resvg } from '@resvg/resvg-js';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// 기본 번들 폰트 — 한글+Latin 커버(Pretendard, OFL). satori는 시스템 폰트 fallback이 없어 항상 1종 보장 필요.
const DEFAULT_FONT = fileURLToPath(new URL('../fonts/Pretendard-Regular.otf', import.meta.url));

export async function renderSatori(htmlString, { width, height, scale = 1, fonts, out }) {
  const files = fonts && fonts.length ? fonts : [DEFAULT_FONT];
  const loaded = await Promise.all(
    files.map(async (f) => ({
      name: 'bundled',
      data: await readFile(resolve(f)),
      weight: 400,
      style: 'normal',
    })),
  );
  const markup = html(htmlString);
  const svg = await satori(markup, { width, height, fonts: loaded });
  // satori SVG는 width×height 비율 고정 — width 기준 scale배 래스터화하면 height도 비례.
  const resvg = new Resvg(svg, { fitTo: { mode: 'width', value: Math.round(width * scale) } });
  await writeFile(resolve(out), resvg.render().asPng());
  return out;
}
