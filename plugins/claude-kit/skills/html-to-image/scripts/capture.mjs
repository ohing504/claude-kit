#!/usr/bin/env node
// html-to-image: HTML(파일·URL·문자열)을 지정 비율로 정확히 캡처 → PNG/JPEG.
// 본질은 브라우저로 HTML 열어 screenshot이고, 가치는 정확한 크기·배율·렌더 완료 대기·batch.
// 컴포지션(HTML 만들기)은 호출자 책임. 모션/영상은 범위 밖(Remotion/hyperframes).

import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

function parseArgs(argv) {
  const a = { delay: 400, quality: 90, freeze: true, fullPage: false };
  const next = (i) => {
    if (i + 1 >= argv.length) throw new Error(`${argv[i]} 값 누락`);
    return argv[i + 1];
  };
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '--html': a.html = next(i); i++; break;
      case '--url': a.url = next(i); i++; break;
      case '--html-string': a.htmlString = next(i); i++; break;
      case '--preset': a.preset = next(i); i++; break;
      case '--width': a.width = Number(next(i)); i++; break;
      case '--height': a.height = Number(next(i)); i++; break;
      case '--scale': a.scale = Number(next(i)); i++; break;
      case '--selector': a.selector = next(i); i++; break;
      case '--wait-selector': a.waitSelector = next(i); i++; break;
      case '--delay': a.delay = Number(next(i)); i++; break;
      case '--out': a.out = next(i); i++; break;
      case '--format': a.format = next(i); i++; break;
      case '--quality': a.quality = Number(next(i)); i++; break;
      case '--no-freeze': a.freeze = false; break;
      case '--full-page': a.fullPage = true; break;
      case '--manifest': a.manifest = next(i); i++; break;
      default: throw new Error(`알 수 없는 인자: ${argv[i]}`);
    }
  }
  return a;
}

const PRESETS = JSON.parse(
  readFileSync(fileURLToPath(new URL('../references/presets.json', import.meta.url)), 'utf8'),
);

function resolveSize(job) {
  let { width, height, scale } = job;
  if (job.preset) {
    const p = PRESETS[job.preset];
    if (!p) throw new Error(`프리셋 없음: ${job.preset} (references/presets.json 참조)`);
    width = width ?? p.width;
    height = height ?? p.height;
    scale = scale ?? p.scale;
  }
  if (!width || !height) throw new Error('크기 미지정: --preset 또는 --width/--height 필요');
  return { width, height, scale: scale ?? 1 };
}

function inferFormat(out, fmt) {
  if (fmt) return fmt === 'jpg' ? 'jpeg' : fmt;
  return /\.jpe?g$/i.test(out || '') ? 'jpeg' : 'png';
}

async function loadSource(page, job) {
  if (job.url) {
    await page.goto(job.url, { waitUntil: 'networkidle' });
  } else if (job.html) {
    await page.goto(pathToFileURL(resolve(job.html)).href, { waitUntil: 'networkidle' });
  } else if (job.htmlString != null) {
    await page.setContent(job.htmlString, { waitUntil: 'networkidle' });
  } else {
    throw new Error('소스 미지정: --html | --url | --html-string 중 하나');
  }
}

async function capture(browser, job) {
  if (!job.out) throw new Error('출력 경로 미지정: --out (manifest는 각 항목의 out)');
  const { width, height, scale } = resolveSize(job);
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: scale });
  const page = await ctx.newPage();
  try {
    await loadSource(page, job);
    // 폰트·이미지가 실제로 준비될 때까지 — raw screenshot이 빈/반쪽으로 깨지는 #1 원인.
    await page.evaluate(() => document.fonts && document.fonts.ready);
    if (job.waitSelector) await page.waitForSelector(job.waitSelector, { state: 'visible' });
    // 정적 캡처: 애니메이션·트랜지션을 멈춰 결정적 프레임을 얻는다.
    if (job.freeze) {
      await page.addStyleTag({
        content: '*,*::before,*::after{animation:none!important;transition:none!important;animation-duration:0s!important}',
      });
    }
    if (job.delay) await page.waitForTimeout(job.delay);

    const format = inferFormat(job.out, job.format);
    const opts = { path: job.out, type: format };
    if (format === 'jpeg') opts.quality = job.quality;

    if (job.selector) {
      await page.locator(job.selector).screenshot(opts);
    } else if (job.fullPage) {
      await page.screenshot({ ...opts, fullPage: true });
    } else {
      await page.screenshot({ ...opts, clip: { x: 0, y: 0, width, height } });
    }
    return job.out;
  } finally {
    await ctx.close();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  let jobs;
  if (args.manifest) {
    const items = JSON.parse(readFileSync(resolve(args.manifest), 'utf8'));
    // 각 항목은 전역 기본값(preset·scale·delay 등)을 상속, 항목값이 우선.
    const { manifest, ...defaults } = args;
    jobs = items.map((it) => ({ ...defaults, ...it }));
  } else {
    jobs = [args];
  }

  const browser = await chromium.launch();
  try {
    for (const job of jobs) {
      const saved = await capture(browser, job);
      console.log(`✓ ${saved}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((e) => {
  console.error(`html-to-image 실패: ${e.message}`);
  process.exit(1);
});
