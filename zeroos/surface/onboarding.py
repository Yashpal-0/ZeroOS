"""First run: get an API key. Spec section 7.

This screen has to do real work — the target user does not know what an API
key is, so telling them to "enter your API key" is not onboarding.
"""

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

from zeroos.agent import credentials  # noqa: E402

CONSOLE_URL = "https://openrouter.ai/settings/keys"

EXPLANATION = (
    "ZeroOS does its thinking with an AI model it reaches over the internet. To "
    "do that it needs a key — a long password that lets it ask questions on your "
    "behalf.\n\n"
    "You create one on OpenRouter's website, who handle the billing. It is very "
    "cheap: a typical request costs well under a penny, and you can set a "
    "spending limit on their site.\n\n"
    "Your key is stored in your system keyring, the same place your other "
    "passwords live. It never leaves this computer except to ask the model a "
    "question."
)


def build(on_accepted) -> Gtk.Box:
    """The onboarding page. Calls on_accepted(key) once a key validates.

    Returns the content Box directly rather than wrapping it in an
    Adw.NavigationPage: this app has no navigation stack, and a NavigationPage
    parents its child immediately, which makes the box unusable as a second
    widget's content (GTK4 refuses to reparent a widget that still has one).
    """
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24,
                  margin_bottom=24, margin_start=24, margin_end=24)

    title = Gtk.Label(label="Welcome to ZeroOS")
    title.add_css_class("title-1")
    box.append(title)

    explanation = Gtk.Label(label=EXPLANATION, wrap=True, xalign=0)
    box.append(explanation)

    link = Gtk.LinkButton(uri=CONSOLE_URL, label="Create a key on OpenRouter's website")
    box.append(link)

    entry = Adw.PasswordEntryRow(title="Paste your key here")
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    listbox.add_css_class("boxed-list")
    listbox.append(entry)
    box.append(listbox)

    status = Gtk.Label(label="", wrap=True, xalign=0)
    box.append(status)

    button = Gtk.Button(label="Continue")
    button.add_css_class("suggested-action")
    box.append(button)

    def submit(_button) -> None:
        key = entry.get_text().strip()
        if not key:
            status.set_label("Paste the key you copied from OpenRouter's website.")
            return
        status.set_label("Checking…")
        try:
            valid = credentials.validate(key)
        except Exception:
            status.set_label("Couldn't reach OpenRouter. Check your internet connection.")
            return
        if not valid:
            status.set_label("That key didn't work. Copy it again from the website.")
            return
        try:
            credentials.store(key)
        except OSError:
            status.set_label("Couldn't save your key to the system keyring. Try again.")
            return
        on_accepted(key)

    button.connect("clicked", submit)
    return box
