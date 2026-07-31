import { createServer } from 'node:http';
import { mkdir, readFile, stat } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { chromium } from 'playwright';

const root = new URL('../app/static/', import.meta.url);
const output = new URL('../artifacts/landing-redesign/', import.meta.url);
const viewports = [
  ['desktop-1440x1000', 1440, 1000],
  ['desktop-1280x800', 1280, 800],
  ['tablet-768x1024', 768, 1024],
  ['mobile-390x844', 390, 844],
];
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml' };

const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
    const relative = normalize(pathname).replace(/^([/\\])+/, '');
    const fileUrl = new URL(relative || 'preview-design.html', root);
    const file = await readFile(fileUrl);
    await stat(fileUrl);
    response.writeHead(200, { 'Content-Type': types[extname(fileUrl.pathname)] || 'application/octet-stream' });
    response.end(file);
  } catch {
    response.writeHead(404); response.end('Not found');
  }
});

await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
await mkdir(output, { recursive: true });
const { port } = server.address();
const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  for (const [name, width, height] of viewports) {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${port}/preview-design.html`, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: new URL(`${name}.png`, output).pathname.slice(1), fullPage: false });
    const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    if (hasOverflow) throw new Error(`Horizontal overflow at ${width}x${height}`);
    if (width <= 820) {
      await page.click('.menu-button');
      if (await page.getAttribute('.menu-button', 'aria-expanded') !== 'true') throw new Error(`Mobile menu did not open at ${width}px`);
      await page.click('.menu-button');
    } else {
      await page.click('#feature-tab-financeiro');
      if (!(await page.locator('#feature-financeiro').evaluate(element => element.classList.contains('active')))) throw new Error('Product tabs did not switch');
    }
    await page.locator('[data-open-signup]:visible').first().click();
    await page.check('[name="team_size"][value="team"]');
    if (!(await page.textContent('#instant-plan')).includes('Premium')) throw new Error('Team recommendation did not select Premium');
    await page.click('#signup-next');
    if (await page.locator('[data-step="2"]').isHidden()) throw new Error('Signup did not advance to step 2');
    await page.keyboard.press('Escape');
    if (!(await page.locator('#signup-modal').isHidden())) throw new Error('Escape did not close signup modal');
    if (errors.length) throw new Error(`Browser errors at ${width}x${height}: ${errors.join('; ')}`);
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}
