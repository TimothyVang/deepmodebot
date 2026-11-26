# Choosing a target adapter

Use the highest-level interface the app supports **and the user has authorized**. Keep one connection; rebuild only the addressed window or view when it changes. These are porting recipes, not bundled native drivers or latency measurements.

| Target | Observe | Act and wait |
|---|---|---|
| Plugin-enabled creative app or engine | Use the supported plugin API to read the active scene, selection and available operators. Map domain objects to revision-scoped IDs. | Queue named operations on the app thread, use its undo facility, and wait for the documented completion signal. Use the app's batch mode only for operators it supports. |
| Electron / WebView | Use a documented test hook or a debugging interface explicitly enabled in a **separate, owned test profile**. Read the accessibility tree for the selected view. | Resolve the live control immediately before input. Wait for navigation or a UI event. If attaching is disabled, use a supported accessibility interface or report the limitation. |
| Windows desktop | Scope UI Automation to the selected window. Batch `Name`, control type, enabled state, value and bounds with `IUIAutomationCacheRequest` and `FindAllBuildCache`. | Use supported Invoke, Value, Toggle and SelectionItem patterns. Use structure/property events. Background access depends on the provider and desktop session; do not assume a locked desktop works. |
| macOS desktop | With Accessibility consent, walk the selected app's `AXUIElement` children for role, title, value and enabled state. | Use supported AX actions or settable attributes. Subscribe with `AXObserver`; discard destroyed elements. |
| Linux desktop | Read roles and states through AT-SPI2 on the selected session bus. | Use the provider's Action/EditableText interfaces and object-change events. Check the toolkit exposes the same tree on a virtual display before assuming headless parity. |
| Terminal UI | Prefer an existing machine-readable command; otherwise use an owned PTY and terminal cell grid. Anchor IDs to visible controls, not offsets into raw escape sequences. | Send the documented keys to that PTY and wait for parsed output to reach the predicate. Test resize and redraw before relying on cell positions. |
| Android | Use the selected, authorized test device or emulator and a supported UI Automator or accessibility API. Read labels, resource IDs, bounds and enabled state. | Scope accessibility actions to the selected app/window. Wait for a content-change event and re-observe; do not tap old coordinates after rotation or navigation. |

For an opaque canvas, use a target-owned screenshot and visible hit regions only as a last resort. Confirm focus, geometry, target identity and outcome. If those checks are unavailable, stop rather than sending input to another window.
