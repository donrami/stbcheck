# STBcheck — Technical Quality Fix Specification

**Document Type**: Frontend Technical Audit — Fix Specification  
**Generated**: 2026-04-05  
**Baseline Score**: 12/20 (Acceptable)  
**Target Score**: 18/20 (Excellent)  
**Audit Scope**: Frontend implementation only (`index.html` — 2908 lines)  
**Excluded**: Backend Python code, security posture, testing infrastructure

---

## Executive Summary

The STBcheck frontend has a solid foundation: CSS custom property system, responsive breakpoints, `prefers-reduced-motion` support, skip link, IndexedDB for state persistence, and input sanitization. However, it has critical accessibility gaps (non-interactive `<div>` elements), a memory leak in `IntersectionObserver`, hard-coded colors bypassing the token system, and visual design patterns that converge on the "AI-generated dashboard" aesthetic.

This specification documents every finding from the audit with exact file locations, impact analysis, and acceptance criteria for resolution.

---

## 1. Accessibility — Keyboard & Semantic HTML (P0)

### 1.1 Portal Items — Non-interactive `<div>` with `onclick`

**Files**: `index.html` lines 2189-2209 (JS rendering via `renderPortalList`), lines 370-401 (CSS)

**Problem**: Portal items are rendered as `<div class="portal-item">` with `onclick="selectPortal(index)"`. They are invisible to keyboard navigation and screen readers.

**Impact**: Keyboard users cannot tab to or activate portal items. Screen readers do not announce them as interactive. WCAG 2.1 Level A violation.

**WCAG**: SC 2.1.1 (Keyboard), SC 4.1.2 (Name, Role, Value)

**Fix**:
1. Change rendered portal items to `<button class="portal-item">` elements, OR add `role="button" tabindex="0"` to each `<div>`.
2. Add `keydown` listener for Enter (key code 13) and Space (key code 32) that triggers `selectPortal(index)`.
3. Add `aria-label` describing the action: `"Select portal: {url}, {count} channels"`.
4. If using `<button>`, update CSS: `.portal-item` needs `appearance: none; background: none; text-align: left; cursor: pointer; font: inherit; color: inherit; border: none;` to reset button defaults.
5. Ensure `:focus-visible` styles (line 1122) are visible on the card background — the current 2px solid `var(--accent)` outline should suffice.

**Acceptance criteria**:
- [ ] Tab navigates through all portal items in DOM order
- [ ] Enter/Space activates a portal item
- [ ] Screen reader announces each item as a button with descriptive label
- [ ] Focus ring visible on keyboard focus, not on mouse hover
- [ ] Visual appearance unchanged

---

### 1.2 Category Items — Non-interactive `<div>` with `onclick`

**Files**: `index.html` lines 2217-2240 (JS rendering via `renderCategories`), lines 714-737 (CSS)

**Problem**: Same as portal items — category items use `<div class="category-item">` with `onclick`.

**Impact**: Keyboard users cannot navigate categories. Screen readers do not announce interactive state.

**WCAG**: SC 2.1.1 (Keyboard), SC 4.1.2 (Name, Role, Value)

**Fix**:
1. Use `<button class="category-item">` or `role="button" tabindex="0"`.
2. Add `aria-pressed="true"` on the active category, `aria-pressed="false"` on inactive ones.
3. Add `keydown` listener for Enter/Space.
4. If using `<button>`, reset button defaults in CSS as in 1.1.

**Acceptance criteria**:
- [ ] Tab navigates through all category items
- [ ] Enter/Space selects a category
- [ ] Active category has `aria-pressed="true"`
- [ ] Screen reader announces press state

---

### 1.3 Resizer — Mouse-only interaction

**Files**: `index.html` lines 753-790 (CSS), lines 2832-2878 (JS)

**Problem**: The player resizer only responds to `mousedown`/`mousemove`/`mouseup`. No keyboard alternative exists.

**Impact**: Users who cannot use a mouse cannot resize the player.

**WCAG**: SC 2.1.1 (Keyboard)

**Fix**:
1. Add to the resizer element: `tabindex="0"`, `role="separator"`, `aria-orientation="horizontal"`, `aria-label="Resize video player"`.
2. Add `keydown` handler:
   - Arrow Up: increase height by 20px
   - Arrow Down: decrease height by 20px
   - Shift+Arrow: 50px steps
3. Announce new height via `aria-valuenow` / `aria-valuemin` / `aria-valuemax` or an `aria-live` status message.
4. Verify the global `*:focus-visible` outline is visible on the resizer's `rgba(255, 255, 255, 0.05)` background.

**Acceptance criteria**:
- [ ] Tab reaches the resizer
- [ ] Arrow keys resize the player up/down
- [ ] Shift+Arrow resizes in larger increments
- [ ] New height is announced to screen readers

---

### 1.4 Dynamic Content — No `aria-live` announcements

**Files**: `index.html` lines 1523 (`#portalList`), 1562 (`#channelsGrid`), 1505-1508 (`#loader`)

**Problem**: When portals are discovered, channels load, or errors occur, screen reader users receive no notification.

**Impact**: Screen reader users have no way to know when async operations complete or fail.

**WCAG**: SC 4.1.3 (Status Messages, Level AA)

**Fix**:
1. Add a dedicated status region:
   ```html
   <div id="a11y-status" aria-live="polite" aria-atomic="true" class="visually-hidden"></div>
   ```
2. Create a helper function:
   ```js
   function announceStatus(message) {
       const el = document.getElementById('a11y-status');
       el.textContent = '';
       setTimeout(() => { el.textContent = message; }, 100);
   }
   ```
3. Call `announceStatus()` at key moments:
   - `"Found {n} portals"` after discovery completes
   - `"Loading channels for {portal}"` when selecting a portal
   - `"{n} channels loaded"` when rendering finishes
   - Error messages when playback fails
   - `"Server added to verified list"` after verification
4. Add `aria-busy="true"` to `#channelsGrid` during channel loading, remove when done.

**Acceptance criteria**:
- [ ] Screen reader announces portal discovery results
- [ ] Screen reader announces channel loading completion
- [ ] Screen reader announces errors
- [ ] `aria-busy` toggles correctly during loading

---

### 1.5 Modal Focus Trapping

**Files**: `index.html` lines 509-580 (verified modal), 1604-1613 (alert modal), 1616-1628 (confirm modal)

**Problem**: When a modal is open, Tab can move focus to elements behind the overlay. Focus is not restored to the triggering element on close.

**Impact**: Keyboard users can lose their place when modals open/close. Focus can land on obscured elements.

**WCAG**: SC 2.4.3 (Focus Order)

**Fix**:
1. Create a `focusTrap(modalId)` function that:
   - Stores the currently focused element before opening the modal.
   - On `Tab` key, cycles focus between the first and last focusable elements within the modal.
   - On modal close, restores focus to the stored element.
2. Apply to all three modals: `#verifiedModal`, `#alertModal`, `#confirmModal`.
3. Add Escape key handler to close modals (verify if one exists — `closeModal` function exists but may not have a global Escape listener).
4. Ensure the close button is the first focusable element in each modal.

**Acceptance criteria**:
- [ ] Tab cycles within the modal only
- [ ] Shift+Tab cycles backward within the modal
- [ ] Focus returns to the trigger element on close
- [ ] Escape key closes the modal

---

## 2. Color & Contrast (P1)

### 2.1 `--text-muted` fails WCAG AA

**File**: `index.html` line 154

**Problem**: `--text-muted: #7986cb` on `--bg-base: #0a0a1a` produces a contrast ratio of ~3.8:1. WCAG AA requires 4.5:1 for normal text.

**Impact**: Any text using `var(--text-muted)` is unreadable for users with low vision.

**WCAG**: SC 1.4.3 (Contrast Minimum, Level AA)

**Fix**:
- Change `--text-muted` to `#8899aa` (~5.4:1) for better margin.
- Audit all usages of `var(--text-muted)` to ensure the new value doesn't break visual hierarchy. If some usages need to remain subtle, create a separate `--text-subtle` token for those cases.

**Acceptance criteria**:
- [ ] `--text-muted` contrast ratio >= 4.5:1 against `--bg-base`
- [ ] No visual regressions in elements using this token

---

### 2.2 Hard-coded colors bypass token system

**Locations**:
- `index.html:517` — `background: rgba(0, 0, 0, 0.8)` (modal overlay)
- `index.html:745` — `background: black` (player container)
- `index.html:884` — `background: black` (video element)
- `index.html:891` — `background: rgba(0, 0, 0, 0.7)` (player error overlay)
- `index.html:976` — `background: rgba(0, 0, 0, 0.3)` (channel logo placeholder)
- `index.html:1442` — `background: rgba(0, 0, 0, 0.7)` (sidebar backdrop)

**Impact**: Inconsistent with the token system. If background tokens change, these areas won't match.

**Fix**:
- Replace `background: black` with `background: var(--bg-player)` or create `--bg-player: #000` token.
- Replace `rgba(0, 0, 0, 0.8)` with `var(--bg-modal-backdrop)` or create `--bg-modal-backdrop: rgba(0, 0, 0, 0.8)` token.
- Replace `rgba(0, 0, 0, 0.7)` with `var(--bg-sidebar-backdrop)` or create `--bg-sidebar-backdrop: rgba(0, 0, 0, 0.7)` token.
- Replace `rgba(0, 0, 0, 0.3)` with `var(--bg-logo-placeholder)` or create `--bg-logo-placeholder: rgba(0, 0, 0, 0.3)` token.

**Acceptance criteria**:
- [ ] No hard-coded color values in CSS (except the `:root` token definitions themselves)
- [ ] Player background matches the design system

---

## 3. Performance (P1)

### 3.1 IntersectionObserver Memory Leak

**File**: `index.html` lines 2279-2306 (inside `renderChannelsGrid`)

**Problem**: `renderChannelsGrid()` creates a new `IntersectionObserver` on every call. Previous observers are never `disconnect()`ed. On portals with many channels and frequent re-renders (search, category switch, load more), observers accumulate.

**Impact**: Memory growth over time. Degraded performance on large channel lists.

**Fix**:
```js
// Create once at module scope (near other module-level variables)
let logoObserver = null;

function getLogoObserver() {
    if (!logoObserver) {
        logoObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const placeholder = entry.target;
                    const imgSrc = placeholder.getAttribute('data-src');
                    if (imgSrc) {
                        const img = document.createElement('img');
                        img.src = imgSrc;
                        img.className = 'channel-logo';
                        img.alt = placeholder.getAttribute('alt') || '';
                        img.onerror = () => {
                            placeholder.innerHTML = '<i class="fas fa-tv"></i>';
                        };
                        img.onload = () => {
                            placeholder.innerHTML = '';
                            placeholder.appendChild(img);
                        };
                        placeholder.removeAttribute('data-src');
                    }
                    logoObserver.unobserve(placeholder);
                }
            });
        }, { rootMargin: '100px' });
    }
    return logoObserver;
}
```
- Replace the inline observer creation in `renderChannelsGrid()` with `getLogoObserver().observe(el)`.
- No need to disconnect between renders since each element is `unobserve`d after loading.

**Acceptance criteria**:
- [ ] Only one `IntersectionObserver` instance exists regardless of re-render count
- [ ] Logos still lazy-load correctly
- [ ] No memory growth on repeated category switches

---

### 3.2 CDN Dependencies — No SRI, Using `@latest`

**Files**: `index.html` lines 124-126, 1630

**Problem**:
- `hls.js@latest` — unpinned version, no integrity hash
- `mpegts.js@latest` — unpinned version, no integrity hash
- `DOMPurify@3.0.6` — pinned but no integrity hash
- `Font Awesome 6.0.0` — no integrity hash

**Impact**: A compromised CDN could inject malicious code. `@latest` means no cache benefit across visits if the version changes.

**Fix**:
- Pin all CDN scripts to specific versions.
- Add `integrity` and `crossorigin="anonymous"` attributes.
- Generate SRI hashes using `openssl dgst -sha384 -binary file.js | openssl base64 -A` or https://www.srihash.org/.

Example format:
```html
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.7/dist/hls.min.js"
        integrity="sha384-<hash>" crossorigin="anonymous"></script>
```

**Acceptance criteria**:
- [ ] All external scripts have pinned versions
- [ ] All external scripts have `integrity` and `crossorigin` attributes
- [ ] App loads and functions correctly with pinned versions

---

## 4. Theming Consistency (P2)

### 4.1 Inline Styles Bypass Token System

**Locations**:
- `index.html:1518` — `style="margin-bottom: 0; font-size: 1.2rem;"` (mobile header logo)
- `index.html:1551-1558` — Categories sidebar label and search container with inline styles
- `index.html:1584-1587` — Empty state inline styles
- `index.html:1604` — Alert modal `style="display: none; z-index: 3000;"`
- `index.html:1616` — Confirm modal inline styles
- `index.html:2106-2111` — Loading state inline styles in JS
- `index.html:2127-2133` — No-results state inline styles in JS
- `index.html:2317-2320` — Load More button inline styles in JS
- `index.html:2331-2335` — Search no-results inline styles in JS

**Impact**: Inline styles won't respond to theme changes and create maintenance debt.

**Fix**:
- Create CSS classes for each unique inline style pattern:
  ```css
  .empty-state-centered { grid-column: 1/-1; text-align: center; margin-top: var(--space-12); }
  .modal-hidden { display: none; z-index: 3000; }
  .load-more-btn { grid-column: 1 / -1; margin: var(--space-5) auto; width: 200px; }
  .text-error { color: var(--color-error); }
  .mobile-header-logo { margin-bottom: 0; font-size: 1.2rem; }
  .categories-header { font-size: 0.8rem; font-weight: 600; color: var(--accent); margin-bottom: 15px; padding-left: 15px; }
  .search-container { padding: 0 var(--space-4) var(--space-4) var(--space-4); }
  .search-wrapper { position: relative; }
  .search-icon { position: absolute; left: var(--space-3); top: 50%; transform: translateY(-50%); color: var(--text-secondary); font-size: var(--font-size-base); pointer-events: none; }
  ```
- For JS-generated inline styles, use class names instead of style strings.

**Acceptance criteria**:
- [ ] Zero inline `style` attributes in static HTML (except `display: none` for modals, which is acceptable)
- [ ] JS-generated content uses class names instead of inline styles
- [ ] All styling goes through CSS custom properties

---

### 4.2 Duplicate CSS Rule Blocks

**Locations**:
- `.portal-name`: lines 356-362 and 1048-1055
- `.category-item`: lines 714-737 and 1032-1046
- `textarea`: lines 270-287 and 1067-1084

**Problem**: These selectors are defined twice. The second block overrides the first for overlapping properties, making it unclear which properties are intentional.

**Fix**:
- Merge each pair of duplicate blocks into a single definition.
- If the second block adds properties (like `min-width: 0` on `.portal-name`), include them in the merged block.

**Acceptance criteria**:
- [ ] No duplicate CSS selectors in the stylesheet
- [ ] No visual regressions after consolidation

---

### 4.3 Unused CSS Custom Properties

**File**: `index.html` lines 219-221

**Problem**: `--ease-in-out` and potentially `--ease-spring` may be defined but never used.

**Fix**:
- Search for `var(--ease-in-out)` and `var(--ease-spring)` usage.
- If zero usages, remove the variables.
- Audit all `:root` variables for unused definitions.

**Acceptance criteria**:
- [ ] All defined CSS custom properties are used at least once

---

### 4.4 Duplicate `@keyframes fadeIn`

**File**: `index.html` lines 930-938 and 948-956

**Problem**: Same animation defined twice.

**Fix**:
- Remove duplicate block (lines 948-956).

**Acceptance criteria**:
- [ ] No duplicate `@keyframes` blocks
- [ ] Animations still work correctly

---

## 5. Anti-Patterns & Visual Design (P2)

### 5.1 Uniform Channel Card Grid

**File**: `index.html` lines 914-944 (CSS), lines 2255-2276 (JS rendering)

**Problem**: Every channel card is identical — centered logo, name below, same padding, same hover effect. This is the "identical card grid" anti-pattern.

**Impact**: Interface looks templated and AI-generated. No visual hierarchy.

**Fix** (choose one approach):
- **Option A — List view with category headers**: Replace the card grid with a list layout. Group channels by category with section headers. Use a compact row layout: logo (left, 32px), name (center, left-aligned), category badge (right).
- **Option B — Varied grid**: Keep the grid but introduce visual hierarchy. First channel in each category gets a wider card (span 2 columns). Category names appear as section breaks within the grid.
- **Option C — Dense compact grid**: Reduce card chrome. Remove the card border/background. Show only logo + name in a tighter grid. Add category filter pills at the top instead of a sidebar.

**Acceptance criteria**:
- [ ] Channel display is no longer a uniform grid of identical cards
- [ ] Visual hierarchy distinguishes categories or featured content
- [ ] Performance is not degraded (pagination still works)

---

### 5.2 Redundant Hover Lift Effects

**Locations**: `index.html` lines 319, 345, 440, 473, 1229, 1255, 1273

**Problem**: `transform: translateY(-2px)` appears on hover for nearly every interactive element: primary buttons, back-compat buttons, icon buttons, copy buttons, delete buttons, alert buttons, confirm buttons.

**Impact**: Makes the interface feel generic and templated.

**Fix**:
- Keep `translateY(-2px)` only on `.btn-primary` (the main CTA).
- For secondary buttons (`.btn-icon`, `.btn-copy`, `.btn-delete`, `.btn-view-verified`, `.btn-action`, `.btn-verify`), use only color/border changes on hover.
- For modal buttons (`.btn-alert-ok`, `.btn-confirm-cancel`, `.btn-confirm-delete`), use scale or color changes instead of lift.

**Acceptance criteria**:
- [ ] Only the primary action button has a lift effect on hover
- [ ] Secondary buttons use color/border transitions only
- [ ] Interface feels more intentional, less templated

---

### 5.3 Spring/Bounce Easing

**File**: `index.html` line 221

**Problem**: `--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1)` overshoots (1.56 > 1), creating a bounce effect. The frontend-design guidelines explicitly advise against bounce easing.

**Impact**: Animations feel dated and tacky.

**Fix**:
- Audit all usages of `var(--ease-spring)`. If none exist, remove the variable entirely.
- If any usage exists, replace with `--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1)` for natural deceleration.

**Acceptance criteria**:
- [ ] No bounce/overshoot easing in the codebase
- [ ] All animations use natural deceleration curves

---

### 5.4 Glow Effects Overuse

**Locations**: `index.html` lines 270 (logo icon), 400 (active portal), 1203 (alert icon), and `--shadow-glow` usage on buttons

**Problem**: Glow effects (`drop-shadow`, `box-shadow` with `--accent-glow`) appear on the logo, active portal, alert modal icon, and primary button hover. Combined with glassmorphism, this reinforces the AI-generated aesthetic.

**Impact**: Visual noise. Interface feels like a generic AI template.

**Fix**:
- Keep glow only on the primary CTA button hover (`.btn-primary:hover`).
- Remove `filter: drop-shadow(0 0 8px var(--accent-glow))` from `.logo i` (line 270).
- Replace the active portal's `box-shadow: 0 0 20px var(--accent-glow)` (line 400) with a solid border-color change or a subtle background tint.
- Remove `filter: drop-shadow(0 0 15px var(--accent-glow))` from `.alert-icon` (line 1203).

**Acceptance criteria**:
- [ ] Glow effect appears on at most 1-2 focal elements
- [ ] Active state uses border/background changes, not glow
- [ ] Visual design feels more restrained and intentional

---

## Execution Priority

| Order | Priority | Section | Task | Effort |
|-------|----------|---------|------|--------|
| 1 | P0 | 1.1-1.3 | Keyboard accessibility for portal items, categories, resizer | Medium |
| 2 | P0 | 1.4-1.5 | aria-live regions and modal focus trapping | Medium |
| 3 | P1 | 2.1 | Color contrast fixes | Small |
| 4 | P1 | 3.1 | IntersectionObserver memory leak fix | Small |
| 5 | P1 | 3.2 | CDN SRI pinning | Small |
| 6 | P2 | 4.1 | Theming consistency (inline styles) | Medium |
| 7 | P2 | 4.2-4.4 | Duplicate CSS, unused variables | Small |
| 8 | P2 | 5.1 | Channel card grid redesign | Large |
| 9 | P2 | 5.2-5.4 | Anti-pattern cleanup (hover lifts, easing, glows) | Small |

---

## Definition of Done

The audit is considered resolved when:

1. **Accessibility**: All interactive elements are keyboard-accessible. Screen reader users can navigate and operate the full app. WCAG 2.1 AA level is met.
2. **Performance**: No memory leaks. All external resources are pinned and integrity-checked.
3. **Theming**: Zero hard-coded colors outside `:root`. All text meets WCAG AA contrast.
4. **Responsive**: No regressions at any breakpoint. Touch targets remain >= 44px.
5. **Anti-Patterns**: AI tells reduced to 0-1. Interface has a distinctive, intentional visual identity.
6. **Score**: Audit Health Score >= 18/20.

---

## Recommended Command Sequence

After fixes are applied, re-run `/audit` to verify score improvement.

1. **`/harden`** — Fix P0 keyboard accessibility (sections 1.1-1.5): portal items, categories, resizer, aria-live regions, modal focus trapping.
2. **`/colorize`** — Fix P1 contrast issues (section 2): `--text-muted` ratio, hard-coded colors.
3. **`/optimize`** — Fix P1 performance (section 3): IntersectionObserver leak, CDN SRI pinning.
4. **`/normalize`** — Fix P2 theming (section 4): extract inline styles to CSS classes, consolidate duplicate CSS, remove unused variables.
5. **`/arrange`** — Fix P2 card grid (section 5.1): redesign channel display to break uniform card pattern.
6. **`/quieter`** — Fix P2 anti-patterns (sections 5.2-5.4): remove redundant hover lifts, replace bounce easing, reduce glow effects.
7. **`/polish`** — Final pass on alignment, spacing, and micro-details.
