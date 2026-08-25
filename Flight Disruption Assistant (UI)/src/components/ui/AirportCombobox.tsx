import { useEffect, useMemo, useRef, useState } from 'react'
import type { AirportInfo } from '../../types'

interface Props {
  id: string
  label: string
  airports: AirportInfo[]
  value: string // selected IATA code; '' when nothing valid is chosen
  onChange: (code: string) => void
}

function formatAirport(a: AirportInfo) {
  return `${a.code} — ${a.city} (${a.name})`
}

/** Lower rank = better match: exact IATA code, then code prefix, then city prefix, then anything else. */
function matchRank(a: AirportInfo, q: string) {
  const code = a.code.toLowerCase()
  if (code === q) return 0
  if (code.startsWith(q)) return 1
  if (a.city.toLowerCase().startsWith(q)) return 2
  return 3
}

/**
 * Searchable airport picker: type a city, airport name or IATA code to filter,
 * pick with mouse or keyboard (arrows + Enter, Escape to revert). On blur, an
 * exactly-typed IATA code is accepted; anything else reverts to the last valid
 * selection so the form never holds a half-typed airport.
 */
export function AirportCombobox({ id, label, airports, value, onChange }: Props) {
  const selected = airports.find(a => a.code === value) ?? null
  // query === null means "not editing" - the input shows the selected airport's label.
  const [query, setQuery] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  // Whether the mouse or the keyboard is currently driving the highlight - keeps
  // a resting cursor from silently stealing the arrow-key position.
  const navRef = useRef<'mouse' | 'keyboard'>('mouse')

  const text = query ?? (selected ? formatAirport(selected) : value)

  const matches = useMemo(() => {
    const q = (query ?? '').trim().toLowerCase()
    const pool = q
      ? airports.filter(a =>
          a.code.toLowerCase().includes(q)
          || a.city.toLowerCase().includes(q)
          || a.name.toLowerCase().includes(q),
        )
      : airports
    return [...pool].sort((a, b) => matchRank(a, q) - matchRank(b, q) || a.city.localeCompare(b.city))
  }, [airports, query])

  const typedCode = (query ?? '').trim().toUpperCase()
  // Any 3-letter code the curated list doesn't know is still offered: Atlas
  // live inventory covers effectively every commercial airport worldwide.
  const synthetic: AirportInfo | null = /^[A-Z]{3}$/.test(typedCode) && !airports.some(a => a.code === typedCode)
    ? { code: typedCode, city: typedCode, name: 'Custom IATA code' }
    : null
  const rows: AirportInfo[] = matches.length > 0 ? matches : synthetic ? [synthetic] : []

  useEffect(() => {
    if (!open) return
    listRef.current?.children[highlight]?.scrollIntoView({ block: 'nearest' })
  }, [highlight, open])

  function choose(a: AirportInfo) {
    onChange(a.code)
    setQuery(null)
    setOpen(false)
    // Move focus out of the input: the selection is committed, and leaving focus
    // in place would append the next keystrokes into the committed label text.
    inputRef.current?.blur()
  }

  function closeAndCommit() {
    const q = (query ?? '').trim()
    if (q) {
      const exact = airports.find(a => a.code.toLowerCase() === q.toLowerCase())
      if (exact) onChange(exact.code)
    }
    setQuery(null)
    setOpen(false)
  }

  function handleBlur(event: React.FocusEvent<HTMLDivElement>) {
    // Focus moving within the combobox (input -> option) isn't a real blur.
    if (rootRef.current?.contains(event.relatedTarget as Node)) return
    closeAndCommit()
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) {
        setOpen(true)
        return
      }
      navRef.current = 'keyboard'
      const delta = event.key === 'ArrowDown' ? 1 : -1
      setHighlight(h => Math.min(matches.length - 1, Math.max(0, h + delta)))
      return
    }
    if (event.key === 'Enter' && open && rows.length > 0) {
      event.preventDefault()
      choose(rows[Math.min(highlight, rows.length - 1)])
      return
    }
    if (event.key === 'Escape') {
      setQuery(null)
      setOpen(false)
    }
  }

  function clear() {
    onChange('')
    setQuery('')
    setOpen(true)
    inputRef.current?.focus()
  }

  return (
    <div
      ref={rootRef}
      className="flex flex-col gap-1"
      style={{ flex: 1, position: 'relative', minWidth: 200 }}
      onBlur={handleBlur}
    >
      <label
        htmlFor={id}
        className="font-mono"
        style={{ fontSize: 10, color: '#5B6B84', letterSpacing: '0.06em', textTransform: 'uppercase' }}
      >
        {label}
      </label>

      <div style={{ position: 'relative' }}>
        <input
          ref={inputRef}
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-listbox`}
          aria-autocomplete="list"
          autoComplete="off"
          spellCheck={false}
          value={text}
          placeholder="Type a city or code, e.g. Tokyo or NRT"
          onFocus={() => { setOpen(true); setHighlight(0); inputRef.current?.select() }}
          onClick={() => {
            // Clicking an already-focused field doesn't re-fire onFocus - reopen
            // and select-all so typing replaces the committed label instead of
            // inserting characters into it.
            if (query === null) {
              setOpen(true)
              inputRef.current?.select()
            }
          }}
          onChange={event => { setQuery(event.target.value); setOpen(true); setHighlight(0) }}
          onKeyDown={handleKeyDown}
          aria-activedescendant={open && rows.length > 0 ? `${id}-option-${rows[Math.min(highlight, rows.length - 1)].code}` : undefined}
          className="font-body"
          style={{
            width: '100%', padding: '11px 32px 11px 13px', borderRadius: 10,
            border: '1px solid rgba(47,143,224,0.18)', background: '#fff',
            color: '#1B2A41', outline: 'none', fontSize: 13,
          }}
        />
        {text && (
          <button
            type="button"
            onClick={clear}
            aria-label={`Clear ${label}`}
            style={{
              position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
              border: 0, background: 'none', color: '#8A9BB5', cursor: 'pointer',
              fontSize: 13, padding: 4, lineHeight: 1,
            }}
          >
            ✕
          </button>
        )}
      </div>

      {open && (
        <ul
          ref={listRef}
          id={`${id}-listbox`}
          role="listbox"
          aria-label={label}
          style={{
            position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, zIndex: 30,
            background: '#fff', border: '1px solid rgba(47,143,224,0.18)', borderRadius: 12,
            boxShadow: '0 12px 30px rgba(27,42,65,0.14)', maxHeight: 240, overflowY: 'auto',
            padding: 4, margin: 0, listStyle: 'none',
          }}
          onMouseMove={() => { navRef.current = 'mouse' }}
        >
          {rows.length === 0 ? (
            <li className="font-body" style={{ padding: '10px 12px', fontSize: 12, color: '#8A9BB5' }}>
              No airports match &ldquo;{(query ?? '').trim()}&rdquo;.
            </li>
          ) : (
            rows.map((a, i) => {
              const isCustom = a === synthetic
              return (
              <li
                key={a.code}
                id={`${id}-option-${a.code}`}
                role="option"
                aria-selected={a.code === value}
                onMouseDown={event => { event.preventDefault(); choose(a) }}
                onMouseEnter={() => { if (navRef.current === 'mouse') setHighlight(i) }}
                style={{
                  display: 'flex', alignItems: 'baseline', gap: 8, padding: '8px 10px',
                  borderRadius: 8, cursor: 'pointer',
                  background: i === highlight ? 'rgba(47,143,224,0.10)' : 'transparent',
                }}
              >
                <span className="font-mono font-bold" style={{ fontSize: 12, color: '#1B6FC2', width: 34, flexShrink: 0 }}>
                  {a.code}
                </span>
                <span className="font-body" style={{ fontSize: 12, color: '#1B2A41', flexShrink: 0 }}>
                  {isCustom ? 'Use this code' : a.city}
                </span>
                <span
                  className="font-body"
                  style={{ fontSize: 11, color: '#8A9BB5', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                >
                  {isCustom ? 'not in the quick list - searched via Atlas live inventory' : a.name}
                </span>
              </li>
              )
            })
          )}
        </ul>
      )}
    </div>
  )
}
