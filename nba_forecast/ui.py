"""Small native controls that cannot accept editable text."""

import streamlit as st


def _select_component():
    return st.components.v2.component(
        "nba_native_select",
        html='<label for="choice"></label><select id="choice"></select>',
        css="""
        label { display: block; margin-bottom: 0.45rem; color: var(--st-text-color); font: inherit; font-size: 0.875rem; }
        select { box-sizing: border-box; width: 100%; min-height: 2.6rem; padding: 0.5rem 0.75rem;
                 border: 1px solid var(--st-border-color, #8792a2); border-radius: 0.5rem;
                 color: var(--st-text-color); background: var(--st-secondary-background-color);
                 font: inherit; cursor: pointer; }
        select:focus-visible { outline: 2px solid var(--st-primary-color); outline-offset: 2px; }
        """,
        js="""
        export default function(component) {
            const { parentElement, data, setStateValue } = component;
            parentElement.querySelector('label').textContent = data.label;
            const select = parentElement.querySelector('select');
            select.setAttribute('aria-label', data.label);
            select.replaceChildren(...data.options.map(item => {
                const option = document.createElement('option');
                option.value = item.value;
                option.textContent = item.label;
                return option;
            }));
            select.value = data.value;
            select.onchange = () => setStateValue('value', select.value);
        }
        """,
    )



def native_select(label, options, *, key, index=0, format_func=str):
    options = list(options)
    lookup = {str(o): o for o in options}
    if not options or len(lookup) != len(options):
        raise ValueError("Select options must be nonempty and uniquely named")
    previous = st.session_state.get(key, {})
    value = previous.get("value", str(options[index]))
    if value not in lookup:
        value = str(options[index])
    select = _select_component()
    result = select(data={"label": label, "value": value,
                           "options": [{"value": str(o), "label": format_func(o)} for o in options]},
                     default={"value": value}, key=key, on_value_change=lambda: None)
    return lookup[result.value]
