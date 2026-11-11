import { host, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, useQuery, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useState } from 'react'

const ID = 'design-discovery'
const PANE_ID = ID + ':pane'
const LAUNCHER_PANE_ID = ID + ':launcher'
const DISPLAY_WEIGHTS = { low: 500, medium: 600, high: 700, inverted: 300 }
const FALLBACKS = {
  Inter: 'system-ui, sans-serif',
  Fraunces: 'Georgia, serif',
  'IBM Plex Sans': 'system-ui, sans-serif',
  'Hanken Grotesk': 'system-ui, sans-serif',
  'Cormorant Garamond': 'Georgia, serif',
  Newsreader: 'Georgia, serif',
  'Libre Franklin': 'system-ui, sans-serif',
  'Bricolage Grotesque': 'system-ui, sans-serif',
  Figtree: 'system-ui, sans-serif'
}
const DENSITY = {
  compact: [8, 16, 44, 32, 14, 1.55],
  comfortable: [12, 16, 48, 32, 16, 1.55],
  spacious: [16, 20, 56, 36, 16, 1.5],
  reading: [16, 24, 64, 40, 19, 1.7]
}
const RADII = {
  none: [0, 0],
  slight: [3, 2],
  subtle: [8, 6],
  soft: [14, 12],
  round: [20, 14]
}
const FONT_WEIGHTS = {"Inter":[100,200,300,400,500,600,700,800,900],"Fraunces":[100,200,300,400,500,600,700,800,900],"JetBrains Mono":[100,200,300,400,500,600,700,800],"IBM Plex Sans":[100,200,300,400,500,600,700],"IBM Plex Mono":[100,200,300,400,500,600,700],"Hanken Grotesk":[100,200,300,400,500,600,700,800,900],"Cormorant Garamond":[300,400,500,600,700],"Newsreader":[200,300,400,500,600,700,800],"Libre Franklin":[100,200,300,400,500,600,700,800,900],"Bricolage Grotesque":[200,300,400,500,600,700,800],"Figtree":[300,400,500,600,700,800,900],"Geist":[100,200,300,400,500,600,700,800,900],"Schibsted Grotesk":[400,500,600,700,800,900],"Outfit":[100,200,300,400,500,600,700,800,900],"Jost":[100,200,300,400,500,600,700,800,900],"Source Sans 3":[200,300,400,500,600,700,800,900],"Alegreya Sans":[100,300,400,500,700,800,900],"Nunito":[200,300,400,500,600,700,800,900,1000],"Quicksand":[300,400,500,600,700],"Space Grotesk":[300,400,500,600,700],"Syne":[400,500,600,700,800],"Source Serif 4":[200,300,400,500,600,700,800,900],"Libre Baskerville":[400,500,600,700],"EB Garamond":[400,500,600,700,800],"Crimson Pro":[200,300,400,500,600,700,800,900],"Playfair Display":[400,500,600,700,800,900],"Bodoni Moda":[400,500,600,700,800,900],"Young Serif":[400],"Lora":[400,500,600,700],"Zilla Slab":[300,400,500,600,700],"Roboto Slab":[100,200,300,400,500,600,700,800,900]}
export function googleFontUrl(families) {
  return 'https://fonts.googleapis.com/css2?' + families.map(family => { const available = FONT_WEIGHTS[family] || [400]; const weights = [...new Set([400,500,600,700].map(weight => available.reduce((best, candidate) => Math.abs(candidate - weight) < Math.abs(best - weight) || (Math.abs(candidate - weight) === Math.abs(best - weight) && candidate < best) ? candidate : best, available[0])))].sort((a, b) => a - b); return 'family=' + encodeURIComponent(family).replace(/%20/g, '+') + ':wght@' + weights.join(';') }).join('&') + '&display=swap'
}
export function canonicalFamilies(tokens, fontFamilies) {
  return [...new Set(tokens.flatMap(item => [item.tokens.typography.display_font, item.tokens.typography.body_font]).map(id => fontFamilies?.[id] || id))]
}
function useFontStatus(families) {
  const [status, setStatus] = useState('loading')
  useEffect(() => {
    let live = true
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = googleFontUrl(families)
    link.onload = () => Promise.all(families.map(family => document.fonts.load('16px "' + family + '"'))).then(
      () => {
        if (live && families.every(family => document.fonts.check('16px "' + family + '"'))) setStatus('loaded')
      },
      () => live && setStatus('fallback')
    )
    link.onerror = () => live && setStatus('fallback')
    const existing = document.head.querySelector?.('link[data-design-discovery-fonts="' + families.join('|') + '"]')
    if (existing) { link.remove(); return () => { live = false } }
    link.dataset.designDiscoveryFonts = families.join('|')
    document.head.append(link)
    const timer = window.setTimeout(() => {
      if (live) setStatus(v => v === 'loading' ? 'fallback' : v)
    }, 3500)
    return () => {
      live = false
      window.clearTimeout(timer)
      link.remove()
    }
  }, [families.join('|')])
  return status
}

function FontNotice({ families }) {
  const status = useFontStatus(families)
  return status === 'fallback'
    ? jsx('div', {
        style: {
          marginTop: 6,
          fontSize: 11,
          fontFamily: '"' + families[0] + '", ' + (FALLBACKS[families[0]] || 'sans-serif'),
          color: 'inherit',
          opacity: .75
        },
        children: families.join(', ') + ' unavailable — showing fallback'
      })
    : null
}

function Palette({ color, gap }) {
  const items = [
    ['background', color.background],
    ['surface', color.surface],
    ['text', color.text],
    ['muted', color.muted],
    ['accent', color.accent]
  ]
  return jsxs('div', {
    style: {
      borderTop: '1px solid ' + color.border,
      marginTop: gap,
      paddingTop: gap
    },
    children: [
      jsx('div', {
        style: {
          fontSize: 11,
          marginBottom: 8,
          color: color.muted
        },
        children: 'Palette'
      }),
      jsx('div', {
        style: {
          display: 'flex',
          gap: 8
        },
        children: items.map(([name, value]) =>
          jsxs('div', {
            style: {
              display: 'grid',
              gap: 4,
              fontSize: 10,
              color: color.muted
            },
            children: [
              jsx('span', {
                style: {
                  width: 24,
                  height: 24,
                  borderRadius: 4,
                  background: value,
                  border: '1px solid ' + color.border_strong
                }
              }),
              jsx('span', { children: name })
            ]
          }, name)
        )
      })
    ]
  })
}

function SpecimenCard({ item, working, fontFamilies, option }) {
  const { tokens, contrast, label, rationale } = item
  const { color, typography, layout, geometry } = tokens
  const [related, group, section, inset, body, line] = DENSITY[layout.density] || DENSITY.comfortable
  const [componentRadius, buttonRadius] = RADII[geometry.radius] || RADII.subtle
  const border = geometry.border === 'none' ? 0 : 1
  const borderColor = geometry.border === 'rule' ? color.border_strong : color.border
  const shadow = geometry.elevation === 'layered'
    ? '0 12px 28px ' + color.text + '24'
    : geometry.elevation === 'soft'
      ? '0 5px 15px ' + color.text + '1c'
      : 'none'
  const displayName = fontFamilies?.[typography.display_font] || typography.display_font
  const bodyName = fontFamilies?.[typography.body_font] || typography.body_font
  const display = '"' + displayName + '", ' + (FALLBACKS[displayName] || 'serif')
  const bodyFamily = '"' + bodyName + '", ' + (FALLBACKS[bodyName] || 'sans-serif')
  const failures = Object.values(contrast || {}).filter(result => !result.passes)
  const sample = item.sample || { title: label, body: rationale, items: [{ label: 'Example item', status: 'success', status_label: 'Done' }, { label: 'Second item', status: 'warning', status_label: 'Needs attention' }], primary: 'Primary action', secondary: 'Secondary action' }
  return jsxs('div', {
    children: [
      !working ? jsx('div', { style: { marginBottom: 8, fontSize: 12, fontWeight: 600, color: 'var(--ui-text-primary)' }, children: 'Option ' + option + ': ' + label }) : null,
      working
        ? jsx('div', {
            style: {
              marginBottom: 8,
              fontSize: 12,
              color: 'var(--ui-text-secondary)'
            },
            children: 'Your direction'
          })
        : null,
      working && item.dimensions
        ? jsx('div', {
            style: {
              margin: '0 0 8px',
              display: 'grid',
              gap: 3,
              color: 'var(--ui-text-secondary)',
              fontSize: 11
            },
            children: item.dimensions.map(entry => jsx('div', {
              children: entry.described
                ? entry.dimension[0].toUpperCase() + entry.dimension.slice(1) + ': ' + entry.label + (entry.contrast_adjusted ? ', ' + entry.contrast_adjusted + ' for readability' : '') + ', ' + entry.status
                : entry.dimension[0].toUpperCase() + entry.dimension.slice(1) + ' ' + 'fr' + 'om' + ' ' + entry.label + ', ' + entry.status
            }, entry.dimension))
          })
        : null,
      jsxs('article', {
        style: {
          background: color.background,
          color: color.text,
          padding: inset,
          border: border + 'px solid ' + borderColor,
          borderRadius: componentRadius,
          boxShadow: shadow
        },
        children: [
          jsx('h3', {
            style: {
              margin: 0,
              fontFamily: display,
              fontWeight: DISPLAY_WEIGHTS[typography.weight_contrast] || 600,
              letterSpacing: typography.tracking_display,
              fontSize: 30,
              lineHeight: 1.05
            },
            children: sample.title
          }),
          jsx('p', {
            style: {
              margin: related + 'px 0 0',
              fontFamily: bodyFamily,
              fontSize: body,
              lineHeight: line,
              color: color.muted
            },
            children: sample.body
          }),
          jsxs('div', {
            style: {
              marginTop: section,
              background: color.surface,
              border: border + 'px solid ' + borderColor,
              borderRadius: componentRadius,
              overflow: 'hidden',
              fontFamily: bodyFamily
            },
            children: [
              jsxs('div', {
                style: {
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: related
                },
                children: [
                  jsx('span', { children: sample.items[0].label }),
                  jsx('span', {
                    style: {
                      color: sample.items[0].status === 'warning' ? color.warning : sample.items[0].status === 'neutral' ? color.muted : color.success,
                      fontWeight: 600
                    },
                    children: sample.items[0].status_label
                  })
                ]
              }),
              jsxs('div', {
                style: {
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: related,
                  borderTop: '1px solid ' + color.border
                },
                children: [
                  jsx('span', { children: sample.items[1].label }),
                  jsx('span', {
                    style: {
                      color: sample.items[1].status === 'warning' ? color.warning : sample.items[1].status === 'neutral' ? color.muted : color.success,
                      fontWeight: 600
                    },
                    children: sample.items[1].status_label
                  })
                ]
              })
            ]
          }),
          jsxs('div', {
            style: {
              display: 'flex',
              flexWrap: 'wrap',
              gap: related,
              marginTop: group,
              fontFamily: bodyFamily
            },
            children: [
              jsx('button', {
                type: 'button',
                style: {
                  border: 0,
                  borderRadius: buttonRadius,
                  padding: '9px 13px',
                  background: color.accent,
                  color: color.accent_text,
                  font: 'inherit',
                  fontWeight: 600
                },
                children: sample.primary
              }),
              jsx('button', {
                type: 'button',
                style: {
                  border: '1px solid ' + color.border_strong,
                  borderRadius: buttonRadius,
                  padding: '8px 12px',
                  background: 'transparent',
                  color: color.text,
                  font: 'inherit',
                  fontWeight: 600
                },
                children: sample.secondary
              })
            ]
          }),
          jsx(Palette, { color, gap: section }),
        ]
      }),
      jsx('div', {
        style: {
          margin: '7px 0 22px',
          color: 'var(--ui-text-tertiary)',
          fontSize: 11
        },
        children: failures.length
          ? failures.map(result => result.label).join('; ')
          : 'Contrast checks passed'
      })
    ]
  })
}

function StatePane({ ctx }) {
  const focusedStoredSessionId = useValue(host.state.focusedStoredSessionId)
  const cwd = useValue(host.state.cwd)
  const [copyState, setCopyState] = useState('')
  const query = useQuery({
    queryKey: [ID, 'state', focusedStoredSessionId],
    queryFn: () => ctx.rest('/state?session_id=' + encodeURIComponent(focusedStoredSessionId || '')),
    refetchInterval: 1500
  })
  const data = query.data
  const directions = data?.resolved_directions || []
  const invalidDirections = directions.length && (directions.length !== 3 || new Set(directions.map(item => item.direction_id)).size !== directions.length || directions.some(item => !item.direction_id || !item.tokens || !item.label))
  const paneError = query.error
    ? 'Could not load design directions. Check the console for details.'
    : data?.ok === false
      ? data.error
      : invalidDirections
        ? 'Design directions could not be rendered. Check the console for details.'
        : null
  useEffect(() => {
    if (paneError) console.error('design-discovery pane: ' + JSON.stringify({ error: paneError, sessionId: focusedStoredSessionId, data }))
  }, [paneError, focusedStoredSessionId, data])
  useEffect(() => {
    if (focusedStoredSessionId && cwd) ctx.rest('/workspace', { method: 'POST', body: { session_id: focusedStoredSessionId, cwd } }).catch(() => {})
  }, [ctx, focusedStoredSessionId, cwd])
  if (paneError) {
    return jsx('div', {
      style: { height: '100%', padding: 14, color: 'var(--ui-text-secondary)', background: 'var(--ui-bg-base)', fontSize: 13 },
      children: paneError
    })
  }
  if (!directions.length) {
    return jsx('div', {
      style: {
        height: '100%',
        padding: 14,
        color: 'var(--ui-text-secondary)',
        background: 'var(--ui-bg-base)',
        fontSize: 13
      },
      children: 'Tell Hermes what you’re making and how it should feel.'
    })
  }
  const working = data?.resolved_working
    ? {
        ...data.resolved_working,
        label: 'Working direction',
        rationale: 'A live combination of the directions you are trying.'
      }
    : null
  const copyDesign = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(data.design_md)
      setCopyState('Copied')
    } catch (_) {
      setCopyState('Clipboard is unavailable. Copy the DESIGN.md text from the chat.')
    }
  }
  const copyPath = async () => {
    try { await navigator.clipboard.writeText(data.design_md_path); setCopyState('Path copied') } catch (_) { setCopyState('Clipboard is unavailable.') }
  }
  const openFolder = () => ctx.os?.revealPath?.(data.design_md_path)
  return jsxs('div', {
    style: {
      height: '100%',
      overflow: 'auto',
      padding: 14,
      color: 'var(--ui-text-secondary)',
      background: 'var(--ui-bg-base)'
    },
    children: [
      jsx(FontNotice, { families: canonicalFamilies([...directions, ...(working ? [working] : [])], data?.font_families) }),
      data?.phase === 'final' && data?.design_md ? jsxs('div', {
        style: { margin: '8px 0 12px', padding: 10, border: '1px solid var(--ui-border)', borderRadius: 6, background: 'var(--ui-bg-raised)', color: 'var(--ui-text-primary)' },
        children: [
          jsx('div', { style: { marginBottom: 8, fontSize: 12, fontWeight: 600 }, children: 'DESIGN.md is ready' }),
          jsx('button', { type: 'button', onClick: copyDesign, style: { padding: '6px 9px', border: '1px solid var(--ui-border)', borderRadius: 4, background: 'var(--ui-bg-base)', color: 'var(--ui-text-primary)', cursor: 'pointer', font: 'inherit' }, children: 'Copy DESIGN.md' }),
          data.design_md_path ? jsx('button', { type: 'button', onClick: copyPath, style: { marginLeft: 6, padding: '6px 9px', border: '1px solid var(--ui-border)', borderRadius: 4, background: 'var(--ui-bg-base)', color: 'var(--ui-text-primary)', cursor: 'pointer', font: 'inherit' }, children: 'Copy path' }) : null,
          data.design_md_path && ctx.os?.revealPath ? jsx('button', { type: 'button', onClick: openFolder, style: { marginLeft: 6, padding: '6px 9px', border: '1px solid var(--ui-border)', borderRadius: 4, background: 'var(--ui-bg-base)', color: 'var(--ui-text-primary)', cursor: 'pointer', font: 'inherit' }, children: 'Open folder' }) : null,
          data.design_md_path ? jsx('div', { style: { marginTop: 6, fontSize: 11 }, children: data.design_md_path }) : null,
          copyState ? jsx('div', { style: { marginTop: 6, fontSize: 12, color: 'var(--ui-text-secondary)' }, children: copyState }) : null
        ]
      }) : null,
      working ? jsx(SpecimenCard, { item: working, working: true, fontFamilies: data?.font_families }) : null,
      directions.slice(0, 3).map((item, index) => jsx(SpecimenCard, { item, working: false, option: index + 1, fontFamilies: data?.font_families }, item.direction_id))
    ]
  })
}

function OpenPaneRoute({ openPane }) {
  useEffect(() => {
    openPane()
  }, [openPane])
  return jsx('div', {
    style: {
      padding: 16,
      color: 'var(--ui-text-secondary)'
    },
    children: 'Design Discovery is open in the right pane.'
  })
}

function LauncherPane({ openPane }) {
  return jsxs('div', {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      height: '100%',
      padding: '0 10px',
      color: 'var(--ui-text-secondary)',
      fontSize: 12
    },
    children: [
      jsx('span', { children: 'Design discovery' }),
      jsx('span', {
        style: { color: 'var(--ui-text-tertiary)' },
        children: '·'
      }),
      jsx('button', {
        type: 'button',
        onClick: openPane,
        style: {
          padding: 0,
          border: 0,
          background: 'transparent',
          color: 'var(--ui-text-primary)',
          cursor: 'pointer',
          textDecoration: 'underline'
        },
        children: 'Open workbench'
      })
    ]
  })
}

export default {
  id: ID,
  name: 'Design Discovery',
  defaultEnabled: true,
  register(ctx) {
    const openPane = () => {
      host.undismissPane?.(PANE_ID)
      if (typeof host.revealPane === 'function') {
        host.revealPane(PANE_ID)
        return
      }
      if (typeof host.openWorkspace === 'function') {
        host.openWorkspace(ID, {
          title: 'Design Discovery',
          dock: {
            pane: 'workspace',
            pos: 'right'
          },
          minWidth: '20rem',
          render: () => jsx(StatePane, { ctx })
        })
      }
    }
    ctx.registerMany([
      {
        id: 'pane',
        area: 'panes',
        title: 'Design discovery',
        data: {
          placement: 'right',
          dock: {
            pane: 'workspace',
            pos: 'right'
          },
          width: '320px'
        },
        render: () => jsx(StatePane, { ctx })
      },
      {
        id: 'launcher',
        area: 'panes',
        title: 'Design Discovery launcher',
        data: {
          placement: 'bottom',
          dock: {
            pane: 'workspace',
            pos: 'bottom'
          },
          height: '36px'
        },
        render: () => jsx(LauncherPane, { openPane })
      },
      {
        id: 'route',
        area: ROUTES_AREA,
        data: { path: '/design-discovery' },
        render: () => jsx(OpenPaneRoute, { openPane })
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 60,
        data: {
          path: '/design-discovery',
          label: 'Design discovery',
          codicon: 'symbol-color'
        }
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'design-discovery.open',
          label: 'Open design discovery',
          keywords: ['design', 'discovery', 'workbench'],
          run: openPane
        }
      }
    ])
    if (!ctx.storage.get('firstLoadRevealComplete', false)) {
      host.revealPane?.(PANE_ID)
      ctx.storage.set('firstLoadRevealComplete', true)
    }
    if (!ctx.storage.get('launcherRevealV2', false)) {
      host.undismissPane?.(LAUNCHER_PANE_ID)
      host.revealPane?.(LAUNCHER_PANE_ID)
      ctx.storage.set('launcherRevealV2', true)
    }
  }
}

