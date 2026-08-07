/**
 * Generate realm logo and welcome background images.
 *
 * Uses deterministic procedural art in the browser (no API key required).
 * Optionally calls VITE_BRANDING_AI_URL when configured for true AI generation.
 */

function hashSeed(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let s = seed;
  return () => {
    s += 0x6d2b79f5;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hslColor(h, s, l) {
  return `hsl(${h % 360}, ${s}%, ${l}%)`;
}

function pickPalette(seedText) {
  const rand = mulberry32(hashSeed(seedText));
  const baseHue = Math.floor(rand() * 360);
  return {
    primary: hslColor(baseHue, 62 + rand() * 18, 42 + rand() * 12),
    secondary: hslColor(baseHue + 40 + rand() * 50, 55 + rand() * 20, 55 + rand() * 15),
    accent: hslColor(baseHue + 120 + rand() * 40, 70 + rand() * 20, 58 + rand() * 10),
    bg: hslColor(baseHue + 200, 35 + rand() * 15, 92 + rand() * 6),
    rand,
  };
}

function realmInitials(name) {
  const words = (name || 'Realm')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] || 'R').slice(0, 2).toUpperCase();
}

function canvasToPngFile(canvas, filename) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error('Failed to render image'));
          return;
        }
        resolve(new File([blob], filename, { type: 'image/png' }));
      },
      'image/png',
      0.92,
    );
  });
}

function drawLogoCanvas(ctx, width, height, realmName, seedSuffix = '') {
  const palette = pickPalette(`${realmName}:${seedSuffix}:logo`);
  const { rand } = palette;

  const grad = ctx.createLinearGradient(0, 0, width, height);
  grad.addColorStop(0, palette.primary);
  grad.addColorStop(1, palette.secondary);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, width, height);

  ctx.globalAlpha = 0.22;
  for (let i = 0; i < 6; i++) {
    const r = 40 + rand() * 120;
    ctx.beginPath();
    ctx.fillStyle = palette.accent;
    ctx.arc(rand() * width, rand() * height, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  ctx.fillStyle = 'rgba(255,255,255,0.14)';
  ctx.beginPath();
  const rx = width * 0.12;
  const ry = height * 0.12;
  const rw = width * 0.76;
  const rh = height * 0.76;
  const rad = width * 0.14;
  ctx.moveTo(rx + rad, ry);
  ctx.lineTo(rx + rw - rad, ry);
  ctx.quadraticCurveTo(rx + rw, ry, rx + rw, ry + rad);
  ctx.lineTo(rx + rw, ry + rh - rad);
  ctx.quadraticCurveTo(rx + rw, ry + rh, rx + rw - rad, ry + rh);
  ctx.lineTo(rx + rad, ry + rh);
  ctx.quadraticCurveTo(rx, ry + rh, rx, ry + rh - rad);
  ctx.lineTo(rx, ry + rad);
  ctx.quadraticCurveTo(rx, ry, rx + rad, ry);
  ctx.closePath();
  ctx.fill();

  const initials = realmInitials(realmName);
  ctx.fillStyle = '#ffffff';
  ctx.font = `700 ${Math.floor(width * 0.34)}px system-ui, -apple-system, Segoe UI, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(initials, width / 2, height / 2 + height * 0.02);
}

function drawBackgroundCanvas(ctx, width, height, realmName, seedSuffix = '') {
  const palette = pickPalette(`${realmName}:${seedSuffix}:bg`);
  const { rand } = palette;

  const grad = ctx.createLinearGradient(0, 0, width, height);
  grad.addColorStop(0, palette.primary);
  grad.addColorStop(0.55, palette.secondary);
  grad.addColorStop(1, palette.accent);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, width, height);

  ctx.globalCompositeOperation = 'soft-light';
  for (let i = 0; i < 10; i++) {
    const x = rand() * width;
    const y = rand() * height;
    const r = 80 + rand() * 260;
    const g = ctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, 'rgba(255,255,255,0.35)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalCompositeOperation = 'source-over';

  ctx.fillStyle = 'rgba(0,0,0,0.12)';
  ctx.fillRect(0, height * 0.72, width, height * 0.28);
}

async function renderToFile(drawFn, width, height, realmName, filename, seedSuffix) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  drawFn(ctx, width, height, realmName, seedSuffix);
  return canvasToPngFile(canvas, filename);
}

async function tryRemoteAiImage(prompt, { width, height, seed }) {
  const base =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_BRANDING_AI_URL) || '';
  if (!base) return null;

  const url = new URL(base.replace(/\/$/, ''));
  url.searchParams.set('prompt', prompt);
  url.searchParams.set('width', String(width));
  url.searchParams.set('height', String(height));
  if (seed != null) url.searchParams.set('seed', String(seed));

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(url.toString(), { signal: controller.signal });
    if (!res.ok) return null;
    const blob = await res.blob();
    if (!blob.type.startsWith('image/')) return null;
    return blob;
  } catch (e) {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * @param {string} realmName
 * @param {{ seed?: string, useAi?: boolean }} [options]
 * @returns {Promise<File>}
 */
export async function generateRealmLogo(realmName, options = {}) {
  const name = (realmName || 'Realm').trim() || 'Realm';
  const seed = hashSeed(`${name}:${options.seed || ''}:logo`);

  if (options.useAi !== false) {
    try {
      const blob = await tryRemoteAiImage(
        `Minimal modern emblem logo for a community realm named "${name}", flat vector, centered symbol, no text, transparent-friendly`,
        { width: 512, height: 512, seed },
      );
      if (blob) return new File([blob], 'logo.png', { type: blob.type || 'image/png' });
    } catch {
      /* fall through to procedural */
    }
  }

  return renderToFile(drawLogoCanvas, 512, 512, name, 'logo.png', options.seed || '');
}

/**
 * @param {string} realmName
 * @param {{ seed?: string, useAi?: boolean }} [options]
 * @returns {Promise<File>}
 */
export async function generateRealmBackground(realmName, options = {}) {
  const name = (realmName || 'Realm').trim() || 'Realm';
  const seed = hashSeed(`${name}:${options.seed || ''}:background`);

  if (options.useAi !== false) {
    try {
      const blob = await tryRemoteAiImage(
        `Wide cinematic abstract landscape banner background for a digital community realm named "${name}", atmospheric, no text, no logos`,
        { width: 1600, height: 480, seed },
      );
      if (blob) return new File([blob], 'background.png', { type: blob.type || 'image/png' });
    } catch {
      /* fall through */
    }
  }

  return renderToFile(drawBackgroundCanvas, 1600, 480, name, 'background.png', options.seed || '');
}

/** Fill missing logo/background for deploy without mutating wizard form state. */
export async function resolveDeployBranding(formData, options = {}) {
  const name = (formData?.name || 'Realm').trim() || 'Realm';
  const seed = options.seed || String(Date.now());

  let logo = formData?.logo || null;
  let background = formData?.background || null;

  if (!logo && formData?.logoPreview) {
    logo = await previewDataUrlToFile(formData.logoPreview, 'logo.png');
  }
  if (!background && formData?.backgroundPreview) {
    background = await previewDataUrlToFile(formData.backgroundPreview, 'background.png');
  }

  if (!logo) {
    logo = await generateRealmLogo(name, { seed, useAi: options.useAi });
  }
  if (!background) {
    background = await generateRealmBackground(name, { seed, useAi: options.useAi });
  }

  return { logo, background };
}

/** Restore a wizard preview (data URL or blob URL) to a File for deploy upload. */
export async function previewDataUrlToFile(preview, filename) {
  const src = String(preview || '').trim();
  if (!src) return null;
  try {
    const res = await fetch(src);
    const blob = await res.blob();
    if (!blob.size) return null;
    const type = blob.type || 'image/png';
    return new File([blob], filename, { type });
  } catch {
    return null;
  }
}

/** Fill missing logo/background on formData before deploy. */
export async function ensureDefaultBranding(formData, options = {}) {
  const { logo, background } = await resolveDeployBranding(formData, options);
  formData.logo = logo;
  formData.background = background;
  if (!formData.logoPreview && logo) {
    formData.logoPreview = URL.createObjectURL(logo);
  }
  if (!formData.backgroundPreview && background) {
    formData.backgroundPreview = URL.createObjectURL(background);
  }
  return formData;
}
