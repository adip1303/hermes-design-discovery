import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const input = process.argv[2] || 'desktop/plugin.js'
const sourcePath = input === '--stdin' ? 'stdin' : path.resolve(input)
const source = input === '--stdin' ? fs.readFileSync(0, 'utf8') : fs.readFileSync(sourcePath, 'utf8')
const allowed = new Set(['@hermes/plugin-sdk', 'react', 'react/jsx-runtime', 'react/jsx-dev-runtime'])
const imports = /(?:from\s*|import\s*\(\s*|import\s+)(['"])([^'"]+)\1/g
const unsupported = [...source.matchAll(imports)].map(match => match[2]).filter(specifier => !allowed.has(specifier))
if (unsupported.length) throw new Error('unsupported import: ' + unsupported.join(', '))

// Hermes rewrites approved imports to blob URLs, then dynamically imports ESM.
const shimPath = path.resolve('scripts/.desktop-plugin-shim.mjs')
fs.writeFileSync(shimPath, 'export default {}; export const host={state:{focusedStoredSessionId:{}}}; export const jsx=()=>{}; export const jsxs=()=>{}; export const useEffect=()=>{}; export const useState=()=>{}; export const useQuery=()=>({}); export const useValue=()=>null; export const PALETTE_AREA=""; export const ROUTES_AREA=""; export const SIDEBAR_NAV_AREA="";\n')
const shimUrl = pathToFileURL(shimPath).href
const rewritten = source.replace(imports, (match, quote, specifier) => match.replace(specifier, shimUrl))
const runtimePath = path.resolve('scripts/.desktop-plugin-runtime-check.mjs')
fs.writeFileSync(runtimePath, rewritten)
try {
  const plugin = await import(pathToFileURL(runtimePath).href + '?check=' + Date.now())
  const fonts = JSON.parse(fs.readFileSync(path.resolve('data/fonts.json'), 'utf8'))
  for (const font of fonts) {
    const url = plugin.googleFontUrl([font.family])
    const family = encodeURIComponent(font.family).replace(/%20/g, '+')
    const expectedWeights = [...new Set([400, 500, 600, 700].map(weight => font.weights.reduce((best, candidate) => Math.abs(candidate - weight) < Math.abs(best - weight) || (Math.abs(candidate - weight) === Math.abs(best - weight) && candidate < best) ? candidate : best, font.weights[0])))] .sort((a, b) => a - b).join(';')
    if (!url.includes('family=' + family + ':wght@' + expectedWeights)) throw new Error('invalid Google Fonts URL for ' + font.family)
  }
  if (!source.includes("data?.phase === 'final'") || !source.includes("Copy DESIGN.md") || !source.includes("navigator.clipboard?.writeText")) {
    throw new Error('final pane must include a clipboard copy control')
  }
  console.log('desktop_plugin_runtime_check: passed ' + sourcePath)
} finally {
  fs.rmSync(runtimePath, { force: true })
  fs.rmSync(shimPath, { force: true })
}
