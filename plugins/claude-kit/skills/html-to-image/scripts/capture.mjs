#!/usr/bin/env node
// html-to-image: HTML(파일·URL·문자열)을 지정 비율로 정확히 캡처 → PNG/JPEG.
// 본질은 HTML→이미지(playwright 브라우저 기본·satori 무브라우저 옵션), 가치는 정확한 크기·배율·렌더 완료 대기·batch.
// 컴포지션(HTML 만들기)은 호출자 책임. 모션/영상은 범위 밖(Remotion/hyperframes).

import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

function parseArgs(argv) {
  const a = { delay: 0, quality: 90, freeze: true, fullPage: false };
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
      case '--engine': a.engine = next(i); i++; break;
      case '--font': (a.fonts ??= []).push(next(i)); i++; break;
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
  // networkidle은 Playwright 공식 DISCOURAGED(analytics·ws·SW가 영영 busy). 'load'로 navigation만 끝내고,
  // 렌더 완료는 아래 waitForRender(폰트 status + 이미지 decode)로 명시 보강한다.
  if (job.url) {
    await page.goto(job.url, { waitUntil: 'load' });
  } else if (job.html) {
    await page.goto(pathToFileURL(resolve(job.html)).href, { waitUntil: 'load' });
  } else if (job.htmlString != null) {
    await page.setContent(job.htmlString, { waitUntil: 'load' });
  } else {
    throw new Error('소스 미지정: --html | --url | --html-string 중 하나');
  }
}

// networkidle 제거로 사라지는 "리소스 로드 대기"를 명시 대기 2종으로 메운다.
// 폰트: document.fonts.status 폴링(레이아웃 후 늦게 요청된 폰트도 잡음). 이미지: 전체 img decode 완료.
// 2연속 프레임 폴링은 채택 안 함 — 로딩 스켈레톤에 오수렴할 수 있다.
async function waitForRender(page) {
  await page.evaluate(async () => {
    const deadline = Date.now() + 2000;
    while (document.fonts.status !== 'loaded' && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 100));
    }
    await document.fonts.ready;
    const imgs = Array.from(document.images);
    await Promise.all(imgs.map((i) => (i.complete ? null : i.decode().catch(() => {}))));
  });
}

const ctxKey = (width, height, scale) => `${width}x${height}@${scale}`;

async function capture(ctx, job) {
  if (!job.out) throw new Error('출력 경로 미지정: --out (manifest는 각 항목의 out)');
  const { width, height } = resolveSize(job);
  const page = await ctx.newPage();
  try {
    await loadSource(page, job);
    await waitForRender(page);
    if (job.waitSelector) await page.waitForSelector(job.waitSelector, { state: 'visible' });
    // 추가 안정화 여유 — 보통 불필요(기본 0), 잔여 비결정 요소가 있을 때만 명시.
    if (job.delay) await page.waitForTimeout(job.delay);

    const format = inferFormat(job.out, job.format);
    // animations:'disabled'는 유한 애니메이션/트랜지션을 끝 상태로 완료, 무한은 초기 상태로 고정(캡처 순간만, JS Web Animations 포함).
    // 수동 *{animation:none} 주입(시작-상태 고정)보다 정교. --no-freeze는 'allow'로 매핑.
    const opts = {
      path: job.out,
      type: format,
      caret: 'hide',
      animations: job.freeze ? 'disabled' : 'allow',
    };
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
    await page.close();
  }
}

// satori 엔진: 브라우저 미사용. 무의미한 옵션은 무시가 아니라 명확한 에러로 알린다(playwright 엔진으로 안내).
async function captureSatori(job) {
  if (!job.out) throw new Error('출력 경로 미지정: --out (manifest는 각 항목의 out)');
  const bad = [];
  if (job.url) bad.push('--url');
  if (job.selector) bad.push('--selector');
  if (job.fullPage) bad.push('--full-page');
  if (job.waitSelector) bad.push('--wait-selector');
  if (inferFormat(job.out, job.format) === 'jpeg') bad.push('jpeg(--format/.jpg 확장자)');
  if (job.freeze === false) bad.push('--no-freeze');
  if (bad.length) {
    throw new Error(
      `satori 엔진 미지원 옵션: ${bad.join(', ')}. satori는 --html/--html-string + PNG만 — url·selector·full-page·jpeg가 필요하면 --engine playwright(기본)를 쓴다.`,
    );
  }
  const src =
    job.htmlString != null ? job.htmlString : job.html ? readFileSync(resolve(job.html), 'utf8') : null;
  if (src == null) throw new Error('satori 엔진 소스 미지정: --html | --html-string');
  const { width, height, scale } = resolveSize(job);
  const { renderSatori } = await import('./engines/satori.mjs');
  return renderSatori(src, { width, height, scale, fonts: job.fonts, out: job.out });
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

  // satori-only batch면 브라우저를 아예 안 띄운다(무브라우저 렌더).
  const needsBrowser = jobs.some((j) => (j.engine ?? 'playwright') !== 'satori');
  // --force-color-profile=srgb·--font-render-hinting=none: 색·텍스트 래스터 변동을 줄여 결정성 향상.
  const browser = needsBrowser
    ? await chromium.launch({ args: ['--force-color-profile=srgb', '--font-render-hinting=none'] })
    : null;
  // viewport·deviceScaleFactor가 같은 연속 job은 context를 재사용(생성 100~200ms 절약). 50장마다 재생성으로 누수 방지.
  const cache = new Map();
  const counts = new Map();
  try {
    for (const job of jobs) {
      if ((job.engine ?? 'playwright') === 'satori') {
        console.log(`✓ ${await captureSatori(job)}`);
        continue;
      }
      const { width, height, scale } = resolveSize(job);
      const key = ctxKey(width, height, scale);
      let ctx = cache.get(key);
      const n = (counts.get(key) ?? 0) + 1;
      if (ctx && n % 50 === 0) {
        await ctx.close();
        ctx = undefined;
      }
      if (!ctx) {
        ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: scale });
        cache.set(key, ctx);
      }
      counts.set(key, n);
      const saved = await capture(ctx, job);
      console.log(`✓ ${saved}`);
    }
  } finally {
    for (const ctx of cache.values()) await ctx.close();
    if (browser) await browser.close();
  }
}

main().catch((e) => {
  console.error(`html-to-image 실패: ${e.message}`);
  process.exit(1);
});
