# WebKit leaves a <button> out of the tab sequence unless full keyboard ac

_2026-09-23 03:05 · persistent_

WebKit leaves a <button> out of the tab sequence unless full keyboard access is on OR the button's tabindex is written down: HTMLFormControlElement::isKeyboardFocusable short-circuits to Element::isKeyboardFocusable when tabIndexSetExplicitly() (WebKit r263447, 2023-04-29, Safari 17 / WebKitGTK 2.42). So tabIndex={0} is the structural fix for an unreachable button in a Tauri/WebKit window - not a key handler. Radix RadioGroup.Item and Checkbox.Root are <button>s, not <input>s; radios get a tabindex from roving focus, checkboxes do not.
