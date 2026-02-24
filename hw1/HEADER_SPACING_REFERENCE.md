# Header spacing – code reference

All code that affects the "ICE & Demographics Dashboard" header spacing is in **`app.py`**. Below are the exact locations and snippets so you can edit them.

---

## 1. Global CSS (header and wrappers)

**File:** `5381-activities/hw1/app.py`  
**Block:** `ui.tags.style(""" ... """)` — roughly **lines 46–115**

Relevant rules:

```css
/* Strip padding from layout so nothing adds space above/below header */
html, body { height: 100vh; overflow: hidden; margin: 0; padding: 0; }
body > div { flex: 1; min-height: 0; display: flex; overflow: hidden; padding: 0 !important; margin: 0; }
body > div > div { flex: 1; min-height: 0; display: flex; overflow: hidden; padding: 0 !important; margin: 0; }
body .container-fluid, body .bslib-gap-spacing { padding: 0 !important; margin: 0 !important; }
div:has(> .main-content-wrap) { padding: 0 !important; margin: 0 !important; }

.main-content-wrap {
    flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column;
    padding: 0 !important;
    margin: 0 !important;
}

.main_container, #ice-main-container {
    display: flex; flex-direction: column; height: 100%; min-height: 0; flex: 1;
    padding: 0 !important;
}

/* Direct child of main container (Shiny output wrapper) – no padding */
#ice-main-container > * { margin: 0 !important; padding: 0 !important; }

/* One level deeper, but not the header itself */
#ice-main-container > * > *:not(#ice-dashboard-header) { margin: 0 !important; padding: 0 !important; }

/* Header bar – only flex/box-sizing here; actual spacing is inline + script */
#ice-dashboard-header {
    flex-shrink: 0;
    box-sizing: border-box;
}
```

**What to try:** Add explicit spacing here, e.g.:

```css
#ice-dashboard-header {
    flex-shrink: 0;
    box-sizing: border-box;
    margin: 0 !important;
    padding: 0 12px !important;   /* adjust top/bottom if needed, e.g. 4px 12px */
    min-height: 0 !important;
}
```

---

## 2. Header HTML and inline styles

**File:** `5381-activities/hw1/app.py`  
**Function:** `header_row()` inside `with ui.div(class_="main_container", id="ice-main-container"):` — **lines 209–268**

This builds the header div and its children. Spacing is set via the **`style`** strings.

**Outer header div (`#ice-dashboard-header`):**

```python
"style": (
    "margin:0;padding:0 12px;width:100%;box-sizing:border-box;"
    "display:flex;justify-content:center;align-items:center;"
    "position:relative;line-height:1.2;"
    "border-bottom:1px solid " + border_color + ";"
),
```

- `padding:0 12px` → no top/bottom padding; 12px left/right.  
  To add a bit of vertical padding, change to e.g. `"padding:4px 12px;..."` or `"padding:0.25rem 12px;..."`.

**Title span:**

```python
ui.tags.span(
    "ICE & Demographics Dashboard",
    style=(
        "margin:0;padding:0;display:block;width:100%;"
        "text-align:center;font-size:1.1rem;line-height:1.2;font-weight:600;"
    ),
),
```

- `line-height:1.2` and `font-size:1.1rem` control how tall the line of text is.  
  Changing these will change the visual height of the header bar.

**What to try:** In the outer div `style`, set explicit vertical padding, e.g.:

- `"padding: 4px 12px; ..."` for a small band, or  
- `"padding: 0.25rem 12px; ..."` if you prefer rem.

---

## 3. JavaScript that forces spacing (and injects CSS)

**File:** `5381-activities/hw1/app.py`  
**Same block as above:** inside `header_row()`, the `ui.tags.script(""" ... """)` — **lines 242–267**

This script:

1. Finds `#ice-dashboard-header` and sets `padding: 0 12px`, `margin: 0`, `min-height: 0` with `!important`.
2. Walks from the header’s parent up to `body` and sets `padding: 0` and `margin: 0` on each.
3. Injects a `<style>` tag with the same header and wrapper rules.

If the header still has extra space, either:

- The script is not running (e.g. wrong environment or script blocked), or  
- Another stylesheet or inline style is overriding this (e.g. more specific selector or later load).

**What to try:**

- In the injected `sheet.textContent`, add a very specific rule, e.g.  
  `#ice-main-container #ice-dashboard-header { padding: 4px 12px !important; }`  
  and adjust the `4px` to match your wireframe.
- Or remove/comment out the script and rely only on CSS + inline styles to see if the script is fighting with something.

---

## 4. Theme (background) – does not control spacing

**File:** `5381-activities/hw1/app.py`  
**Function:** `dynamic_theme_style()` — **lines 117–148**

Only sets background/text color for `#ice-dashboard-header` in light/dark mode. No padding or margin.

---

## Summary: where to edit

| Goal                         | Where to edit |
|-----------------------------|---------------|
| Remove space above/below header | (1) CSS `#ice-dashboard-header` and `#ice-main-container > *`; (2) inline `style` on the header div; (3) script that strips parent padding and sets header padding. |
| Header bar vertical padding    | (2) In `header_row()`, change `padding:0 12px` to e.g. `padding:4px 12px` in the header div’s `style`. |
| Title centering                | (2) Already `justify-content:center` and `text-align:center` on the header div and span. |
| Wrapper adding space           | (1) Add or adjust selectors for the main column (e.g. `div:has(> .main-content-wrap)`, `#ice-main-container > *`). (3) Script clears all ancestors; if layout breaks, limit the `while (p && p !== document.body)` loop to fewer levels. |

**Suggested order when fixing yourself:**  
Edit the **inline style** in (2) first (e.g. set `padding: 4px 12px`). If nothing changes, inspect the live page (DevTools → Elements) and see which element has the extra padding/margin (often the parent of `#ice-dashboard-header` or the main column). Then add a CSS rule in (1) that targets that element by its class or structure, or adjust (3) so the script only clears the wrappers you want.
